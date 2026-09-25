"""Outbound HTTP policy: SSRF matrix, redirects, size caps, propagation, redaction."""

import gzip
import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.integrations.errors import IntegrationError, OutboundUrlRejected
from app.integrations.http import (
    CallContext,
    OutboundClient,
    parse_retry_after,
    validate_outbound_url,
)
from app.integrations.redaction import redact_data, redact_headers, redact_text, redact_url

PUBLIC = "93.184.216.34"


def make_settings(**overrides):
    values = {
        "app_env": "test",
        "database_url": "postgresql+asyncpg://t:t@127.0.0.1:1/t",
        "redis_url": "redis://127.0.0.1:1/0",
    }
    values.update(overrides)
    return Settings(**values)


def resolver_for(*answers):
    async def resolve(host, port):
        return list(answers)

    return resolve


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://localhost/x", "internal host name"),
        ("https://127.0.0.1/", "loopback"),
        ("https://127.1.2.3/", "loopback"),
        ("https://10.0.0.5/", "private"),
        ("https://172.16.4.4/", "private"),
        ("https://192.168.1.1/", "private"),
        ("https://169.254.169.254/latest/meta-data", "metadata"),
        ("https://[::1]/", "loopback"),
        ("https://[fd00::1]/", "private"),
        ("https://[fd00:ec2::254]/", "metadata"),
        ("https://[::ffff:127.0.0.1]/", "loopback"),
        ("https://100.64.0.1/", "shared address"),
        ("https://224.0.0.1/", "multicast"),
        ("https://0.0.0.0/", "unspecified"),
        ("https://2130706433/", "numeric host"),  # decimal 127.0.0.1
        ("https://0x7f000001/", "numeric host"),  # hex 127.0.0.1
        ("https://0177.0.0.1/", "numeric host"),  # octal
        ("https://127.1/", "numeric host"),  # short form
        ("https://user:pass@example.com/", "credentials"),
        ("https://example.com@evil.test/", "credentials"),
        ("http://example.com/", "https is required"),
        ("ftp://example.com/", "https is required"),
        ("https://example.com:8080/", "non-standard port"),
        ("https://metadata.google.internal/", "internal host name"),
        ("https://svc.localhost/", "internal host name"),
        ("https://exa mple.com/", "invalid characters"),
    ],
)
async def test_ssrf_rejection_matrix(url, reason):
    with pytest.raises(OutboundUrlRejected) as caught:
        await validate_outbound_url(url, make_settings(), resolver=resolver_for(PUBLIC))
    assert reason in caught.value.reason


@pytest.mark.parametrize(
    "answers",
    [
        ["10.1.2.3"],
        ["127.0.0.1"],
        [PUBLIC, "192.168.0.10"],
        ["fd12::1"],
        ["169.254.169.254"],
        ["::ffff:10.0.0.1"],
        ["64:ff9b::a00:1"],
    ],
)
async def test_dns_answers_must_all_be_public(answers):
    with pytest.raises(OutboundUrlRejected) as caught:
        await validate_outbound_url(
            "https://rebind.example.com/", make_settings(), resolver=resolver_for(*answers)
        )
    assert "resolves to" in caught.value.reason


async def test_unresolvable_host_rejected():
    async def failing(host, port):
        raise OSError("nxdomain")

    with pytest.raises(OutboundUrlRejected):
        await validate_outbound_url("https://nope.example.com/", make_settings(), resolver=failing)


async def test_public_https_accepted_and_ports_policy():
    ok = await validate_outbound_url(
        "https://hooks.example.com/abc?x=1", make_settings(), resolver=resolver_for(PUBLIC)
    )
    assert ok.host == "hooks.example.com" and ok.port == 443 and ok.addresses == (PUBLIC,)
    allowed = make_settings(outbound_allowed_ports=[8443])
    ok = await validate_outbound_url(
        "https://hooks.example.com:8443/", allowed, resolver=resolver_for(PUBLIC)
    )
    assert ok.port == 8443


async def test_http_only_for_dev_allowlist_and_never_in_production():
    dev = make_settings(outbound_http_allowlist=["mock.local"])
    ok = await validate_outbound_url("http://mock.local/x", dev, resolver=resolver_for("10.0.0.1"))
    assert ok.scheme == "http"
    with pytest.raises(OutboundUrlRejected):
        await validate_outbound_url("http://other.local/x", dev, resolver=resolver_for(PUBLIC))


PROD = {
    "app_env": "production",
    "database_url": "postgresql+asyncpg://t:t@h/t",
    "redis_url": "redis://h/0",
    "cors_origins": ["https://app.example.com"],
    "job_queue_mode": "arq",
    "cookie_secure": True,
}


def test_production_requires_encryption_key_when_integrations_enabled():
    with pytest.raises(ValueError, match="SECRETS_ENCRYPTION_KEY"):
        Settings(**PROD)
    Settings(**PROD, integrations_enabled=False)
    Settings(**PROD, secrets_encryption_key="k")
    with pytest.raises(ValueError, match="Plain-http"):
        Settings(**PROD, secrets_encryption_key="k", outbound_http_allowlist=["mock.local"])
    with pytest.raises(ValueError, match="TLS"):
        Settings(**PROD, secrets_encryption_key="k", outbound_verify_tls=False)


def client(handler, **settings):
    return OutboundClient(
        make_settings(**settings),
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=resolver_for(PUBLIC),
    )


async def test_redirects_are_not_followed_and_are_errors():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://169.254.169.254/"})

    response = await client(handler).request("GET", "https://api.example.com/x")
    assert response.status_code == 302 and len(calls) == 1
    with pytest.raises(IntegrationError) as caught:
        response.ensure_success()
    assert caught.value.code == "UNEXPECTED_REDIRECT"


async def test_response_size_cap_and_gzip_bomb():
    big = client(lambda r: httpx.Response(200, content=b"x" * 5000))
    with pytest.raises(IntegrationError) as caught:
        await big.request("GET", "https://api.example.com/", max_bytes=1024)
    assert caught.value.code == "RESPONSE_TOO_LARGE"
    bomb = gzip.compress(b"0" * 200_000)
    compressed = client(
        lambda r: httpx.Response(200, content=bomb, headers={"content-encoding": "gzip"})
    )
    with pytest.raises(IntegrationError) as caught:
        await compressed.request("GET", "https://api.example.com/", max_bytes=10_000)
    assert caught.value.code == "RESPONSE_TOO_LARGE"
    small = client(
        lambda r: httpx.Response(
            200, content=gzip.compress(b'{"a":1}'), headers={"content-encoding": "gzip"}
        )
    )
    assert (await small.request("GET", "https://api.example.com/")).json() == {"a": 1}


async def test_request_id_and_traceparent_propagation():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={})

    parent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    await client(handler).request(
        "GET",
        "https://api.example.com/",
        context=CallContext(request_id="req-1", correlation_id="corr-1", traceparent=parent),
    )
    assert seen["x-request-id"] == "req-1" and seen["x-correlation-id"] == "corr-1"
    assert seen["traceparent"].startswith("00-" + "a" * 32 + "-")
    assert seen["traceparent"] != parent  # new span id


async def test_timeouts_classified_by_idempotency():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(IntegrationError) as caught:
        await client(timeout).request("GET", "https://api.example.com/")
    assert caught.value.kind == "retryable"
    with pytest.raises(IntegrationError) as caught:
        await client(timeout).request("POST", "https://api.example.com/")
    assert caught.value.kind == "ambiguous"

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(IntegrationError) as caught:
        await client(refused).request("POST", "https://api.example.com/")
    assert caught.value.kind == "retryable"


async def test_url_revalidated_on_every_request():
    answers = [PUBLIC]

    async def resolve(host, port):
        return list(answers)

    outbound = OutboundClient(
        make_settings(),
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
        resolver=resolve,
    )
    await outbound.request("GET", "https://flip.example.com/")
    answers[:] = ["10.0.0.7"]  # DNS now points inside
    with pytest.raises(OutboundUrlRejected):
        await outbound.request("GET", "https://flip.example.com/")


def test_retry_after_parsing():
    assert parse_retry_after("30") == 30
    assert parse_retry_after("999999") == 3600
    assert parse_retry_after(None) is None
    assert parse_retry_after("garbage") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0


def test_redaction_masks_secrets():
    headers = redact_headers(
        {
            "Authorization": "Bearer abc",
            "X-Api-Key": "k",
            "Accept": "json",
            "Stripe-Signature": "t=1,v1=2",
        }
    )
    assert headers["authorization"] == headers["x-api-key"] == "[redacted]"
    assert headers["stripe-signature"] == "[redacted]" and headers["accept"] == "json"
    assert "sk_live_" not in redact_text("key sk_live_abcdefghijklmnop leaked")
    assert "Bearer" not in redact_text("header Bearer eyJhbGciOi.xxxxxxxxxx.yyyyyyyyyy")
    url = redact_url("https://user:pw@api.example.com/p?access_token=abc&page=2")
    assert "pw" not in url and "abc" not in url and "page=2" in url
    assert "T000" not in redact_url("https://hooks.slack.com/services/T000/B000/XXXX")
    data = redact_data(
        {"password": "p", "nested": {"client_secret": "s", "ok": "v"}, "items": [{"token": "t"}]}
    )
    assert data == {
        "password": "[redacted]",
        "nested": {"client_secret": "[redacted]", "ok": "v"},
        "items": [{"token": "[redacted]"}],
    }


async def test_logs_never_contain_secrets(caplog):
    logger = logging.getLogger("platform")
    logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="platform"):
            await client(lambda r: httpx.Response(200, json={"ok": True})).request(
                "GET",
                "https://api.example.com/v1?api_key=SECRETVALUE",
                headers={"authorization": "Bearer SECRETTOKEN"},
            )
    finally:
        logger.propagate = False
    from app.core.logging import JsonFormatter

    text = json.dumps([JsonFormatter().format(r) for r in caplog.records])
    assert "SECRETVALUE" not in text and "SECRETTOKEN" not in text
    assert "api.example.com" in text
