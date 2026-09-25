"""Adapter contract tests against documented provider APIs via httpx.MockTransport.

Live provider verification is UNVERIFIED; these tests pin request shapes and error
classification: success, 401 invalid credential, timeout, 5xx, 429, malformed JSON.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings
from app.integrations.catalog import REGISTRY
from app.integrations.email import render_template
from app.integrations.errors import IntegrationError, OutboundUrlRejected
from app.integrations.http import CallContext, OutboundClient
from app.integrations.providers import smtp as smtp_module
from app.integrations.providers.generic_webhook import GenericWebhookProvider
from app.integrations.providers.resend import ResendProvider
from app.integrations.providers.s3 import S3Provider, scoped_key
from app.integrations.providers.sendgrid import SendGridProvider
from app.integrations.providers.slack import SlackProvider
from app.integrations.providers.smtp import SmtpProvider, check_smtp_host
from app.integrations.providers.stripe import StripeProvider
from app.integrations.providers.whatsapp_meta import WhatsAppMetaProvider
from app.integrations.registry import (
    ConfigurationInvalid,
    EmailMessage,
    IntegrationDefinition,
    IntegrationRegistry,
    ProviderContext,
    SyncEntityPolicy,
)
from app.integrations.signing import verify_signature_header
from app.shared.errors import BusinessRuleViolation


def settings(**overrides):
    values = {
        "app_env": "test",
        "database_url": "postgresql+asyncpg://t:t@h:1/t",
        "redis_url": "redis://h:1/0",
        "whatsapp_graph_base_url": "https://graph.facebook.com",
        "whatsapp_graph_version": "v21.0",
    }
    values.update(overrides)
    return Settings(**values)


async def public(host, port):
    return ["93.184.216.34"]


def ctx(handler, config=None, credentials=None, mode="production", **extra):
    return ProviderContext(
        settings=settings(**extra),
        http=OutboundClient(
            settings(**extra),
            httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            resolver=public,
        ),
        config=config or {},
        credentials=credentials or {},
        mode=mode,
        call=CallContext(request_id="req-test"),
    )


def responder(status, body=None, headers=None, raw=None):
    def handler(request):
        if raw is not None:
            return httpx.Response(status, content=raw, headers=headers)
        return httpx.Response(status, json=body if body is not None else {}, headers=headers)

    return handler


def timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


async def expect(kind, coro, code=None):
    with pytest.raises(IntegrationError) as caught:
        await coro
    assert caught.value.kind == kind, caught.value.code
    if code:
        assert caught.value.code == code
    return caught.value


# --- WhatsApp (Meta Cloud API) ----------------------------------------------------------

WA_CONFIG = {"phone_number_id": "1234567890"}
WA_CREDS = {"access_token": "EAAG-test-token", "app_secret": "app-secret", "verify_token": "vt"}


async def test_whatsapp_health_success_request_shape():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers["authorization"]
        return httpx.Response(
            200,
            json={
                "id": "1234567890",
                "display_phone_number": "+1 555",
                "verified_name": "Shop",
                "quality_rating": "GREEN",
            },
        )

    result = await WhatsAppMetaProvider().health_check(ctx(handler, WA_CONFIG, WA_CREDS))
    assert result.ok and "+1 555" in result.message
    assert seen["url"].startswith("https://graph.facebook.com/v21.0/1234567890?fields=")
    assert seen["auth"] == "Bearer EAAG-test-token"


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(401, {"error": {"code": 190, "message": "expired"}}), "auth"),
        (responder(400, {"error": {"code": 190, "type": "OAuthException"}}), "auth"),
        (timeout, "retryable"),
        (responder(500, {"error": {"code": 1}}), "retryable"),
        (responder(429, {}, {"retry-after": "12"}), "rate_limited"),
        (responder(400, {"error": {"code": 130429}}), "rate_limited"),
        (responder(200, raw=b"{not json"), "invalid_response"),
    ],
)
async def test_whatsapp_health_failures(handler, kind):
    error = await expect(
        kind, WhatsAppMetaProvider().health_check(ctx(handler, WA_CONFIG, WA_CREDS))
    )
    if kind == "rate_limited" and error.retry_after is not None:
        assert error.retry_after == 12


async def test_whatsapp_send_text_and_media_host_allowlist():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    provider = WhatsAppMetaProvider()
    result = await provider.send_text(ctx(handler, WA_CONFIG, WA_CREDS), "+15551234567", "hi")
    assert result.provider_message_id == "wamid.ABC"
    assert sent == {
        "messaging_product": "whatsapp",
        "to": "15551234567",
        "type": "text",
        "text": {"body": "hi"},
    }
    # A non-idempotent send that times out is ambiguous: never blindly retried.
    await expect(
        "ambiguous", provider.send_text(ctx(timeout, WA_CONFIG, WA_CREDS), "15551234567", "hi")
    )

    def media(request):
        return httpx.Response(
            200,
            json={"url": "https://evil.example.com/x", "mime_type": "image/png", "file_size": 10},
        )

    with pytest.raises(IntegrationError, match="not trusted"):
        await provider.get_media(ctx(media, WA_CONFIG, WA_CREDS), "987654321")


def test_whatsapp_signature_handshake_and_parse():
    provider = WhatsAppMetaProvider()
    body = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "1234567890"},
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "15550001111",
                                        "type": "text",
                                        "text": {"body": "hello"},
                                    }
                                ],
                                "statuses": [{"id": "wamid.0", "status": "delivered"}],
                            }
                        }
                    ]
                }
            ],
        }
    ).encode()
    good = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    s = settings()
    assert provider.verify_webhook({"x-hub-signature-256": good}, body, WA_CREDS, s, time.time())
    assert not provider.verify_webhook({"x-hub-signature-256": "sha256=00"}, body, WA_CREDS, s, 0)
    assert not provider.verify_webhook({}, body, WA_CREDS, s, 0)
    assert not provider.verify_webhook({"x-hub-signature-256": good}, body + b" ", WA_CREDS, s, 0)
    events = provider.parse_webhook(body)
    assert [(e.provider_event_id, e.event_type) for e in events] == [
        ("wamid.1", "message.received"),
        ("wamid.0:delivered", "message.status"),
    ]
    params = {"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "12345"}
    assert provider.handshake(params, WA_CREDS, s) == "12345"
    assert provider.handshake({**params, "hub.verify_token": "no"}, WA_CREDS, s) is None
    assert provider.handshake({**params, "hub.challenge": "<script>"}, WA_CREDS, s) is None


# --- Resend -----------------------------------------------------------------------------

RESEND_CREDS = {"api_key": "re_test_1234567890"}


async def test_resend_health_and_send():
    result = await ResendProvider().health_check(
        ctx(responder(200, {"data": [{"status": "verified"}]}), {}, RESEND_CREDS)
    )
    assert result.ok and "1 verified" in result.message
    restricted = await ResendProvider().health_check(
        ctx(responder(401, {"name": "restricted_api_key"}), {}, RESEND_CREDS)
    )
    assert restricted.ok and "sending-only" in restricted.message
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["idem"] = request.headers.get("idempotency-key")
        return httpx.Response(200, json={"id": "email_1"})

    message = EmailMessage(
        to=["a@example.com"], subject="S", text="T", html="<p>T</p>", idempotency_key="k-1"
    )
    out = await ResendProvider().send_email(
        ctx(handler, {"from_address": "noreply@example.com"}, RESEND_CREDS), message
    )
    assert out.provider_message_id == "email_1" and seen["idem"] == "k-1"
    assert seen["body"]["from"] == "noreply@example.com" and seen["body"]["to"] == ["a@example.com"]


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(401, {"name": "validation_error"}), "auth"),
        (timeout, "retryable"),
        (responder(503), "retryable"),
        (responder(429, {}, {"retry-after": "3"}), "rate_limited"),
        (responder(200, raw=b"<html>"), "invalid_response"),
    ],
)
async def test_resend_failures(handler, kind):
    await expect(kind, ResendProvider().health_check(ctx(handler, {}, RESEND_CREDS)))


# --- SendGrid ---------------------------------------------------------------------------

SG_CREDS = {"api_key": "SG.test-key-123456789"}


async def test_sendgrid_scopes_and_send():
    ok = await SendGridProvider().health_check(
        ctx(responder(200, {"scopes": ["mail.send", "scopes.read"]}), {}, SG_CREDS)
    )
    assert ok.ok
    await expect(
        "auth",
        SendGridProvider().health_check(
            ctx(responder(200, {"scopes": ["stats.read"]}), {}, SG_CREDS)
        ),
        "MISSING_SCOPE",
    )

    def handler(request):
        body = json.loads(request.content)
        assert body["personalizations"][0]["to"] == [{"email": "a@example.com"}]
        return httpx.Response(202, headers={"x-message-id": "sg-1"})

    out = await SendGridProvider().send_email(
        ctx(handler, {"from_address": "noreply@example.com"}, SG_CREDS),
        EmailMessage(to=["a@example.com"], subject="S", text="T"),
    )
    assert out.provider_message_id == "sg-1"


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(401, {"errors": []}), "auth"),
        (timeout, "retryable"),
        (responder(500), "retryable"),
        (responder(429), "rate_limited"),
        (responder(200, raw=b"nope"), "invalid_response"),
    ],
)
async def test_sendgrid_failures(handler, kind):
    await expect(kind, SendGridProvider().health_check(ctx(handler, {}, SG_CREDS)))


# --- Stripe -----------------------------------------------------------------------------

STRIPE_CREDS = {"secret_key": "sk_test_1234567890abcdef", "webhook_secret": "whsec_test"}


async def test_stripe_balance_mode_and_payment_intent():
    ok = await StripeProvider().health_check(
        ctx(
            responder(200, {"object": "balance", "livemode": False}),
            {},
            STRIPE_CREDS,
            mode="sandbox",
        )
    )
    assert ok.ok and "test mode" in ok.message
    with pytest.raises(ConfigurationInvalid):  # test key on a production connection
        await StripeProvider().health_check(ctx(responder(200, {}), {}, STRIPE_CREDS))
    seen = {}

    def handler(request):
        seen["form"] = parse_qs(request.content.decode())
        seen["idem"] = request.headers["idempotency-key"]
        return httpx.Response(
            200,
            json={
                "id": "pi_123456789",
                "status": "requires_payment_method",
                "amount": 1250,
                "currency": "usd",
                "client_secret": "pi_secret_x",
            },
        )

    intent = await StripeProvider().create_payment_intent(
        ctx(handler, {}, STRIPE_CREDS, mode="sandbox"),
        1250,
        "USD",
        "order-1:pay",
        {"order": "ORD-1"},
    )
    assert intent.amount_minor == 1250 and intent.client_secret_available
    assert not hasattr(intent, "client_secret")
    assert seen["form"]["amount"] == ["1250"] and seen["form"]["currency"] == ["usd"]
    assert seen["form"]["metadata[order]"] == ["ORD-1"] and seen["idem"] == "order-1:pay"


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(401, {"error": {"type": "invalid_request_error"}}), "auth"),
        (timeout, "retryable"),
        (responder(502), "retryable"),
        (responder(429, {}, {"retry-after": "1"}), "rate_limited"),
        (responder(200, raw=b"{"), "invalid_response"),
    ],
)
async def test_stripe_failures(handler, kind):
    await expect(
        kind, StripeProvider().health_check(ctx(handler, {}, STRIPE_CREDS, mode="sandbox"))
    )


def test_stripe_webhook_signature_and_replay_window():
    provider = StripeProvider()
    body = json.dumps(
        {
            "id": "evt_1234567",
            "object": "event",
            "type": "payment_intent.succeeded",
            "created": 1700000000,
            "data": {"object": {"id": "pi_123456789", "object": "payment_intent"}},
        }
    ).encode()
    now = time.time()

    def header(ts):
        mac = hmac.new(b"whsec_test", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        return f"t={ts},v1={mac}"

    s = settings(webhook_replay_window_seconds=300)
    assert provider.verify_webhook(
        {"stripe-signature": header(int(now))}, body, STRIPE_CREDS, s, now
    )
    assert not provider.verify_webhook(
        {"stripe-signature": header(int(now) - 301)}, body, STRIPE_CREDS, s, now
    )  # replay outside window
    assert not provider.verify_webhook(
        {"stripe-signature": f"t={int(now)},v1=00"}, body, STRIPE_CREDS, s, now
    )
    assert not provider.verify_webhook({}, body, STRIPE_CREDS, s, now)
    events = provider.parse_webhook(body)
    assert events[0].provider_event_id == "evt_1234567"
    assert events[0].event_type == "payment_intent.succeeded"


async def test_stripe_customer_pagination():
    pages = {
        None: {"data": [{"id": "cus_AAAAAAA1", "email": "A@x.com", "name": "A"}], "has_more": True},
        "cus_AAAAAAA1": {"data": [{"id": "cus_BBBBBBB2", "email": None}], "has_more": False},
    }

    def handler(request):
        return httpx.Response(200, json=pages[request.url.params.get("starting_after")])

    c = ctx(handler, {}, STRIPE_CREDS, mode="sandbox")
    first = await StripeProvider().list_customers(c, None, 100)
    assert first.items[0].email == "a@x.com" and first.next_cursor == "cus_AAAAAAA1"
    second = await StripeProvider().list_customers(c, first.next_cursor, 100)
    assert second.next_cursor is None and second.items[0].email is None


# --- S3-compatible ----------------------------------------------------------------------

S3_CONFIG = {
    "endpoint_url": "https://s3.us-east-1.amazonaws.com",
    "bucket": "tenant-files",
    "region": "us-east-1",
    "addressing": "path",
    "key_prefix": "app",
}
S3_CREDS = {"access_key_id": "AKIAEXAMPLE000000000", "secret_access_key": "secret/example"}


async def test_s3_head_bucket_is_signed_and_upload_hashes_payload():
    seen = {}

    def handler(request):
        seen[request.method] = request
        return httpx.Response(200, headers={"etag": '"abc"'})

    c = ctx(handler, S3_CONFIG, S3_CREDS)
    assert (await S3Provider().health_check(c)).ok
    head = seen["HEAD"]
    assert str(head.url) == "https://s3.us-east-1.amazonaws.com/tenant-files"
    assert head.headers["authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE000000000/"
    )
    meta = await S3Provider().upload(c, "docs/a.txt", b"hello", "text/plain")
    put = seen["PUT"]
    assert str(put.url).endswith("/tenant-files/app/docs/a.txt")
    assert put.headers["x-amz-content-sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert meta.etag == "abc" and meta.size == 5
    url = S3Provider().signed_url(c, "docs/a.txt", 60)
    assert "X-Amz-Signature=" in url and "X-Amz-Expires=60" in url
    with pytest.raises(IntegrationError):
        await S3Provider().upload(c, "../escape", b"x", "text/plain")
    assert scoped_key("t1", "e1", "/a.txt") == "t/t1/e/e1/a.txt"


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(403, raw=b"<Error/>"), "auth"),
        (timeout, "retryable"),
        (responder(503, raw=b""), "retryable"),
        (responder(429, raw=b""), "rate_limited"),
    ],
)
async def test_s3_failures(handler, kind):
    await expect(kind, S3Provider().health_check(ctx(handler, S3_CONFIG, S3_CREDS)))


async def test_s3_missing_bucket_and_malformed_metadata():
    await expect(
        "permanent",
        S3Provider().health_check(ctx(responder(404, raw=b""), S3_CONFIG, S3_CREDS)),
        "BUCKET_NOT_FOUND",
    )
    meta = await S3Provider().metadata(
        ctx(responder(200, raw=b"", headers={"content-length": "abc"}), S3_CONFIG, S3_CREDS), "k"
    )
    assert meta.size == 0  # malformed header does not crash


# --- Generic webhook / Slack -------------------------------------------------------------

GW_CONFIG = {"url": "https://hooks.example.com/in"}
GW_CREDS = {"signing_secret": "0123456789abcdef-secret"}


async def test_generic_webhook_signs_and_health_does_not_send():
    captured = {}

    def handler(request):
        captured["request"] = request
        return httpx.Response(200, content=b"not json at all")  # body ignored

    c = ctx(handler, GW_CONFIG, GW_CREDS)
    assert (await GenericWebhookProvider().health_check(c)).ok
    assert "request" not in captured  # test never sends
    status = await GenericWebhookProvider().deliver(c, "order.confirmed", "evt-1", b'{"a":1}')
    request = captured["request"]
    assert status == 200 and request.headers["idempotency-key"] == "evt-1"
    assert verify_signature_header(
        GW_CREDS["signing_secret"], b'{"a":1}', request.headers["x-platform-signature"]
    )


@pytest.mark.parametrize(
    "handler,kind",
    [
        (responder(401), "auth"),
        (timeout, "ambiguous"),
        (responder(500), "retryable"),
        (responder(429), "rate_limited"),
    ],
)
async def test_generic_webhook_failures(handler, kind):
    await expect(
        kind,
        GenericWebhookProvider().deliver(
            ctx(handler, GW_CONFIG, GW_CREDS), "order.confirmed", "e", b"{}"
        ),
    )


async def test_generic_webhook_rejects_private_destination():
    c = ctx(responder(200), {"url": "https://10.0.0.1/hook"}, GW_CREDS)
    with pytest.raises(OutboundUrlRejected):
        await GenericWebhookProvider().health_check(c)


async def test_slack_validates_without_posting():
    posted = []
    c = ctx(
        lambda r: posted.append(r) or httpx.Response(200, content=b"ok"),
        {},
        {"webhook_url": "https://hooks.slack.com/services/T0/B0/XYZ"},
    )
    assert (await SlackProvider().health_check(c)).ok and not posted
    await SlackProvider().send_text(c, "", "hello")
    assert json.loads(posted[0].content) == {"text": "hello"}
    with pytest.raises(ConfigurationInvalid):
        SlackProvider().validate_configuration(
            {}, {"webhook_url": "https://evil.test/x"}, settings()
        )


# --- SMTP -------------------------------------------------------------------------------


class FakeSMTP:
    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None, context=None):
        self.calls = [("connect", host, port)]
        FakeSMTP.instances.append(self)

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, context=None):
        self.calls.append(("starttls",))

    def login(self, user, password):
        if password != "good":
            import smtplib

            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.calls.append(("login", user))

    def send_message(self, message):
        self.calls.append(("send", message["To"]))

    def quit(self):
        self.calls.append(("quit",))

    def close(self):
        pass


async def test_smtp_health_is_login_only(monkeypatch):
    monkeypatch.setattr(smtp_module.smtplib, "SMTP", FakeSMTP)
    config = {
        "host": "smtp.example.com",
        "port": 587,
        "security": "starttls",
        "username": "u",
        "from_address": "noreply@example.com",
    }
    FakeSMTP.instances.clear()
    assert (await SmtpProvider().health_check(ctx(responder(200), config, {"password": "good"}))).ok
    names = [c[0] for c in FakeSMTP.instances[0].calls]
    assert names == ["connect", "ehlo", "starttls", "ehlo", "login", "quit"]
    await expect(
        "auth", SmtpProvider().health_check(ctx(responder(200), config, {"password": "bad"}))
    )
    with pytest.raises(ConfigurationInvalid):
        SmtpProvider().build(
            ctx(responder(200), config, {}),
            EmailMessage(to=["a@example.com"], subject="x\r\nBcc: b@x.com", text="t"),
        )


async def test_smtp_destination_policy():
    with pytest.raises(OutboundUrlRejected):
        await check_smtp_host("10.0.0.2", 587, settings())
    with pytest.raises(OutboundUrlRejected):
        await check_smtp_host("smtp.example.com", 2526, settings(), public)
    await check_smtp_host("smtp.example.com", 465, settings(), public)


# --- registry, templates -----------------------------------------------------------------


def test_registry_honesty():
    planned = [d for d in REGISTRY.all() if d.availability == "planned"]
    assert {"google_calendar", "quickbooks", "shopify", "microsoft_teams"} <= {
        d.key for d in planned
    }
    assert all(REGISTRY.provider(d.key) is None and not d.connectable for d in planned)
    syncing = [d.key for d in REGISTRY.all() if d.syncs]
    assert syncing == ["stripe"]
    assert all(d.sync_support == ("none",) for d in REGISTRY.all() if d.key != "stripe")
    fake = IntegrationRegistry()
    with pytest.raises(ValueError):  # sync declared without a sync-capable adapter
        fake.register(
            IntegrationDefinition(
                key="slack",
                name="x",
                description="x",
                category="collaboration",
                provider="x",
                auth_type="none",
                sync_support=("pull",),
                sync_entities=(SyncEntityPolicy("customers", "pull", "platform"),),
            ),
            SlackProvider(),
        )


def test_email_templates_escape_and_restrict():
    rendered = render_template(
        "handoff_notification",
        {
            "customer": "<script>alert(1)</script>",
            "reason": "a & b",
            "link": "https://app.example.com/pi/1",
        },
    )
    assert "<script>" not in rendered.html and "&lt;script&gt;" in rendered.html
    assert "a &amp; b" in rendered.html and "<script>" in rendered.text
    with pytest.raises(BusinessRuleViolation):
        render_template("handoff_notification", {"link": "javascript:alert(1)"})
    with pytest.raises(BusinessRuleViolation):
        render_template("invitation", {"html": "<b>x</b>"})
    subject = render_template(
        "system_alert", {"title": "a\r\nBcc: x", "severity": "high", "message": "m"}
    ).subject
    assert "\n" not in subject and "\r" not in subject
