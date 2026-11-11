"""nori credits bridge on the disposable database: the inbound pre-hook inside pi's real pipeline
and the outbound send door. A fake nori and a fake WhatsApp provider on httpx mock transports:
no network, no real provider. Run only through scripts/pi-test-env.sh."""

import json
import time
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from test_pi_pipeline import pi_workspace

from app.modules.pi.models import PiMessage, WhatsAppConnection, WhatsAppWebhookEvent
from app.modules.pi_saas.nori_credits import hook
from app.modules.pi_saas.nori_credits.models import PiNoriBridgeLog
from app.modules.pi_saas.nori_credits.resilience import (
    IDENTIFY_CACHE,
    METRICS,
    reset_breakers,
)
from tests.support.fake_nori import (
    BASE,
    HEAD,
    MEMBER,
    OWNER,
    SECRET,
    STAFF,
    STRANGER,
    FakeNori,
    signed,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clean_state():
    reset_breakers()
    IDENTIFY_CACHE.clear()
    METRICS.reset()
    yield
    reset_breakers()
    IDENTIFY_CACHE.clear()


class Bridge:
    """A pi workspace wired to a fake nori and a fake WhatsApp provider."""

    def __init__(self, pi, nori, refuse):
        self.pi, self.nori, self.refuse = pi, nori, refuse

    @property
    def sent(self):
        return self.pi.sent

    async def settings(self, **section):
        response = await self.pi.api.patch(
            "/api/v1/pi/settings/response_rules", json={"value": {"nori_bridge": section}}
        )
        assert response.status_code == 200, response.text
        return response

    async def say(self, sender, text, mid):
        await self.pi.process(text, mid, sender=sender)

    async def inbound_rows(self, mid):
        return list(
            await self.pi.db.scalars(select(PiMessage).where(PiMessage.provider_message_id == mid))
        )

    def texts_to(self, number):
        return [
            m["text"]["body"]
            for m in self.sent
            if m.get("to") == number and m.get("type") == "text"
        ]

    async def post(self, payload, *, secret=SECRET, signature=None, raw=None):
        body, sig = signed(secret, payload) if raw is None else (raw, signature)
        return await self.pi.api.post(
            "/api/pi/nori-send",
            content=body,
            headers={"x-workzap-signature": signature or sig, "content-type": "application/json"},
        )

    def send_payload(self, to=MEMBER, text="Your credits are running low: 4,200 left.", **extra):
        return {"to": to, "text": text, "ts": int(time.time() * 1000), **extra}

    async def audit(self):
        return list(
            await self.pi.db.scalars(
                select(PiNoriBridgeLog)
                .where(PiNoriBridgeLog.kind == "send")
                .order_by(PiNoriBridgeLog.created_at)
            )
        )

    async def hook_args(self):
        connection = await self.pi.db.scalar(select(WhatsAppConnection))
        scope = self.pi.scope()
        return connection, scope


async def bridge(api, business_db, *, env=True, flag=True, **section) -> Bridge:
    pi = await pi_workspace(api, business_db, business_type="service_business")
    nori, refuse = FakeNori(), {"code": None}
    inner = pi.http._transport.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nori.test":
            return nori(request)
        if refuse["code"]:
            return httpx.Response(
                400, json={"error": {"code": refuse["code"], "message": "refused"}}
            )
        return inner(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pi.ctx["http"] = http
    app = pi.app
    app.state.http = http
    settings = app.state.settings
    settings.workzap_bridge_secret = SecretStr(SECRET) if env else None
    settings.nori_base_url = BASE if env else ""
    settings.nori_bridge_kill = False
    result = Bridge(pi, nori, refuse)
    if flag:
        await result.settings(enabled=True, **section)
    return result


# --- the hook inside pi's pipeline ---


async def test_flag_off_pi_is_unchanged_and_makes_no_http_call_to_nori(api, business_db):
    b = await bridge(api, business_db, flag=False)
    await b.say(OWNER, "balance", "wamid.off-1")
    assert b.nori.requests == []  # not even `identify`
    assert len(await b.inbound_rows("wamid.off-1")) == 1  # pi's own pipeline took the message
    assert b.texts_to(OWNER) != ["You have 12,000 credits left."]
    assert METRICS.snapshot() == {}
    await b.pi.close()


async def test_default_setting_is_off_and_settable_through_the_settings_api(api, business_db):
    b = await bridge(api, business_db, flag=False)
    view = (await api.get("/api/v1/pi/settings")).json()
    assert view["response_rules"]["nori_bridge"] == {"enabled": False}
    response = await b.settings(enabled=True, timeout_seconds=2.0)
    assert response.json()["response_rules"]["nori_bridge"]["enabled"] is True
    bad = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"nori_bridge": {"enabled": "yes"}}}
    )
    assert bad.status_code == 422
    await b.pi.close()


async def test_missing_environment_makes_the_module_inert_even_with_the_flag_on(api, business_db):
    b = await bridge(api, business_db, env=False, flag=True)
    await b.say(OWNER, "balance", "wamid.env-1")
    assert b.nori.requests == []
    assert len(await b.inbound_rows("wamid.env-1")) == 1
    await b.pi.close()


async def test_kill_switch_passes_every_message_straight_on(api, business_db):
    b = await bridge(api, business_db)
    b.pi.app.state.settings.nori_bridge_kill = True
    await b.say(OWNER, "balance", "wamid.kill-1")
    assert b.nori.requests == []
    assert len(await b.inbound_rows("wamid.kill-1")) == 1
    await b.pi.close()


async def test_a_member_is_answered_by_nori_and_the_brain_does_not_run(api, business_db):
    b = await bridge(api, business_db)
    await b.say(OWNER, "balance", "wamid.bal-1")
    assert b.texts_to(OWNER) == ["You have 12,000 credits left."]  # sent through pi's adapter
    assert await b.inbound_rows("wamid.bal-1") == []  # pi stored and thought about nothing
    paths = [(p, body.get("action")) for p, body in b.nori.requests]
    assert paths == [("/api/credits/pi", "identify"), ("/api/workzap/inbound", None)]
    event = await business_db.scalar(select(WhatsAppWebhookEvent))
    assert event.status == "processed"
    await b.pi.close()


async def test_an_unknown_number_costs_one_identify_and_its_text_never_leaves_pi(api, business_db):
    b = await bridge(api, business_db)
    await b.say(STRANGER, "hello, I need a website", "wamid.str-1")
    assert [(p, body.get("action")) for p, body in b.nori.requests] == [
        ("/api/credits/pi", "identify")
    ]
    assert "website" not in json.dumps(b.nori.requests)
    assert len(await b.inbound_rows("wamid.str-1")) == 1  # pi carried on as before
    await b.pi.close()


async def test_a_member_message_nori_does_not_handle_carries_on_in_pi(api, business_db):
    b = await bridge(api, business_db)
    await b.say(MEMBER, "hello there", "wamid.pass-1")
    assert len(b.nori.calls("/api/workzap/inbound")) == 1
    assert len(await b.inbound_rows("wamid.pass-1")) == 1
    assert "credits" not in " ".join(b.texts_to(MEMBER))
    await b.pi.close()


@pytest.mark.parametrize("mode", ["timeout", "connect", "500", "401", "badjson", "list"])
async def test_every_error_class_fails_open_and_pi_carries_on(api, business_db, mode):
    b = await bridge(api, business_db)
    b.nori.mode = mode
    await b.say(MEMBER, "balance", f"wamid.fo-{mode}")
    assert len(await b.inbound_rows(f"wamid.fo-{mode}")) == 1  # pi processed it as before
    assert b.texts_to(MEMBER) == [] or "credits left" not in b.texts_to(MEMBER)[0]
    await b.pi.close()


async def test_when_identify_works_but_inbound_fails_it_also_fails_open(api, business_db):
    b = await bridge(api, business_db)
    original = b.nori.__class__.inbound

    def broken(self, body):
        raise httpx.ReadTimeout("slow")

    b.nori.__class__.inbound = broken
    try:
        await b.say(MEMBER, "balance", "wamid.fo-in")
    finally:
        b.nori.__class__.inbound = original
    assert len(await b.inbound_rows("wamid.fo-in")) == 1
    outcome = await business_db.scalar(
        select(PiNoriBridgeLog.outcome).where(PiNoriBridgeLog.kind == "inbound")
    )
    assert outcome == "failopen"
    await b.pi.close()


async def test_the_circuit_opens_after_n_failures_and_stops_calling_nori(api, business_db):
    b = await bridge(api, business_db, breaker_failures=2, breaker_cooldown_seconds=600)
    b.nori.mode = "500"
    for index in range(4):
        await b.say(MEMBER, "balance", f"wamid.cb-{index}")
    assert len(b.nori.requests) == 0  # a 500 is never recorded by the fake: count calls instead
    assert METRICS.snapshot()["call:http_5xx"] == 2  # two real attempts opened it
    assert METRICS.snapshot()["call:circuit_open"] >= 2  # then nothing left pi
    for index in range(4):
        assert len(await b.inbound_rows(f"wamid.cb-{index}")) == 1  # pi kept working throughout
    await b.pi.close()


async def test_a_retry_with_the_same_message_id_never_replies_twice(api, business_db):
    b = await bridge(api, business_db)
    connection, scope = await b.hook_args()
    ctx = {"settings": b.pi.app.state.settings, "http": b.pi.ctx["http"]}
    event = SimpleNamespace(
        payload={
            "kind": "message",
            "message_type": "text",
            "sender": OWNER,
            "message_id": "wamid.idem-1",
            "body": "balance",
        }
    )
    first = await hook.pre_hook(ctx, business_db, scope, connection, event)
    second = await hook.pre_hook(ctx, business_db, scope, connection, event)
    assert first.handled and first.reply == "You have 12,000 credits left."
    assert second.handled and second.reply is None and second.reason == "duplicate"
    assert len(b.nori.calls("/api/workzap/inbound")) == 1
    await b.pi.close()


async def test_a_passed_message_retried_is_not_sent_to_nori_again(api, business_db):
    b = await bridge(api, business_db)
    connection, scope = await b.hook_args()
    ctx = {"settings": b.pi.app.state.settings, "http": b.pi.ctx["http"]}
    event = SimpleNamespace(
        payload={
            "kind": "message",
            "message_type": "text",
            "sender": MEMBER,
            "message_id": "wamid.idem-2",
            "body": "hello there",
        }
    )
    assert not (await hook.pre_hook(ctx, business_db, scope, connection, event)).handled
    again = await hook.pre_hook(ctx, business_db, scope, connection, event)
    assert not again.handled and again.reason == "duplicate_passed"
    assert len(b.nori.calls("/api/workzap/inbound")) == 1
    await b.pi.close()


async def test_workzap_connect_number_is_left_to_the_older_bridge(api, business_db):
    b = await bridge(api, business_db)
    connection, scope = await b.hook_args()
    settings = b.pi.app.state.settings
    settings.nori_bridge_url = "https://nori.test/api/workzap/inbound"
    settings.nori_bridge_secret = SecretStr(SECRET)
    settings.nori_bridge_phone_number_id = connection.phone_number_id
    try:
        ctx = {"settings": settings, "http": b.pi.ctx["http"]}
        event = SimpleNamespace(
            payload={
                "kind": "message",
                "message_type": "text",
                "sender": OWNER,
                "message_id": "wamid.legacy",
                "body": "balance",
            }
        )
        assert (await hook.pre_hook(ctx, business_db, scope, connection, event)).reason == "off"
        assert b.nori.requests == []
    finally:
        settings.nori_bridge_url = ""
        settings.nori_bridge_secret = None
        settings.nori_bridge_phone_number_id = ""
    await b.pi.close()


async def test_logs_carry_no_number_and_no_message_text(api, business_db, caplog):
    b = await bridge(api, business_db)
    b.nori.mode = "500"
    with caplog.at_level("DEBUG"):
        await b.say(MEMBER, "my secret request text 424242", "wamid.log-1")
    joined = " | ".join(
        f"{r.getMessage()} {sorted(r.__dict__.items(), key=str)}"
        for r in caplog.records
        if r.name.startswith("app.pi.nori_credits")
    )
    assert "nori_bridge_failopen" in joined or "nori_bridge_metric" in joined
    assert "923002222222" not in joined and "3002222222" not in joined
    assert "my secret request text" not in joined and "424242" not in joined
    await b.pi.close()


# --- the send door ---


async def test_send_door_is_503_until_configured_and_enabled(api, business_db):
    off = await bridge(api, business_db, flag=False)
    response = await off.post(off.send_payload())
    assert response.status_code == 503 and response.json()["reason"] == "disabled"
    assert off.sent == []
    off.pi.app.state.settings.nori_base_url = ""
    response = await off.post(off.send_payload())
    assert response.status_code == 503 and response.json()["reason"] == "not_configured"
    await off.pi.close()


async def test_kill_switch_turns_the_send_door_into_503_at_once(api, business_db):
    b = await bridge(api, business_db)
    assert (await b.post(b.send_payload())).status_code == 200
    b.pi.app.state.settings.nori_bridge_kill = True
    response = await b.post(b.send_payload())
    assert response.status_code == 503 and response.json()["reason"] == "disabled"
    assert len(b.texts_to(MEMBER)) == 1
    await b.pi.close()


async def test_a_signed_text_to_a_nori_member_is_sent_and_audited_without_the_text(
    api, business_db
):
    b = await bridge(api, business_db)
    text = "Your credits are running low: 4,200 left. See https://nori.test/credits"
    response = await b.post(b.send_payload(text=text))
    assert response.status_code == 200 and response.json()["ok"] is True
    assert b.texts_to(MEMBER) == [text]
    [row] = await b.audit()
    assert row.outcome == "sent_text" and row.recipient_mask == "92***2222"
    assert row.tenant_id is not None and row.created_at is not None
    assert "4,200" not in json.dumps([c.name for c in PiNoriBridgeLog.__table__.columns])
    dump = " ".join(
        str(v) for v in (row.outcome, row.reason, row.recipient_mask, row.recipient_hash)
    )
    assert "credits" not in dump and MEMBER not in dump
    await b.pi.close()


async def test_a_template_is_sent_as_a_template_outside_the_window(api, business_db):
    b = await bridge(api, business_db)
    template = {"name": "credits_update", "language": "en", "params": ["Low balance: 4,200 left."]}
    response = await b.post(b.send_payload(text="Low balance: 4,200 left.", template=template))
    assert response.status_code == 200
    [message] = [m for m in b.sent if m.get("type") == "template"]
    assert message["template"]["name"] == "credits_update"
    assert message["template"]["language"] == {"code": "en"}
    assert message["template"]["components"][0]["parameters"][0]["text"].startswith("Low balance")
    assert b.texts_to(MEMBER) == []  # not also sent as free text
    [row] = await b.audit()
    assert row.outcome == "sent_template"
    await b.pi.close()


async def test_signature_timestamp_and_replay_failures(api, business_db):
    b = await bridge(api, business_db)
    payload = b.send_payload()
    wrong = await b.post(payload, secret="not-the-right-secret-000")
    assert wrong.status_code == 401 and wrong.json()["reason"] == "bad_signature"
    raw, sig = signed(SECRET, payload)
    tampered = await b.post(None, raw=raw.replace(b"4,200", b"9,999"), signature=sig)
    assert tampered.status_code == 401
    missing = await b.pi.api.post("/api/pi/nori-send", content=raw)
    assert missing.status_code == 401
    stale = await b.post(b.send_payload(ts=int(time.time() * 1000) - 11 * 60 * 1000))
    assert stale.status_code == 401 and stale.json()["reason"] == "stale"
    future = await b.post(b.send_payload(ts=int(time.time() * 1000) + 11 * 60 * 1000))
    assert future.status_code == 401
    unreadable = await b.post(b.send_payload(ts="soon"))
    assert unreadable.status_code == 401
    assert b.sent == []
    first = await b.post(None, raw=raw, signature=sig)
    again = await b.post(None, raw=raw, signature=sig)
    assert first.status_code == 200
    assert again.status_code == 409 and again.json()["reason"] == "replay"
    assert len(b.texts_to(MEMBER)) == 1
    await b.pi.close()


async def test_body_size_and_shape_limits(api, business_db):
    b = await bridge(api, business_db)
    big = await b.post(b.send_payload(text="x" * 9000))
    assert big.status_code == 413
    raw = b"[1,2,3]"
    from app.modules.pi_saas.nori_credits import signing

    listy = await b.post(None, raw=raw, signature=signing.sign(SECRET, raw))
    assert listy.status_code == 400
    junk = b"not json at all"
    assert (await b.post(None, raw=junk, signature=signing.sign(SECRET, junk))).status_code == 400
    no_to = await b.post({"text": "hi", "ts": int(time.time() * 1000)})
    assert no_to.status_code == 400 and no_to.json()["reason"] == "bad_recipient"
    assert b.sent == []
    await b.pi.close()


async def test_rate_limit_per_minute(api, business_db):
    b = await bridge(api, business_db, send_per_minute=2)
    codes = [(await b.post(b.send_payload(text=f"Low balance {n}"))).status_code for n in range(4)]
    assert codes == [200, 200, 429, 429]
    assert len(b.texts_to(MEMBER)) == 2
    await b.pi.close()


async def test_allowlist_unknown_numbers_are_refused_and_numbers_that_messaged_pi_pass(
    api, business_db
):
    b = await bridge(api, business_db)
    refused = await b.post(b.send_payload(to=STRANGER))
    assert refused.status_code == 403 and refused.json()["reason"] == "recipient_not_allowed"
    assert b.sent == []
    await b.say(STRANGER, "hello, I need a website", "wamid.allow-1")  # pi's brain, not nori
    allowed = await b.post(b.send_payload(to=STRANGER, text="Statement ready."))
    assert allowed.status_code == 200
    assert b.texts_to(STRANGER)[-1] == "Statement ready."
    rows = await b.audit()
    assert [r.outcome for r in rows] == ["rejected", "sent_text"]
    assert rows[0].reason == "recipient_not_allowed"
    await b.pi.close()


async def test_when_nori_cannot_confirm_a_stranger_nothing_is_sent(api, business_db):
    b = await bridge(api, business_db)
    b.nori.mode = "500"
    response = await b.post(b.send_payload(to=HEAD))
    assert response.status_code == 503 and response.json()["reason"] == "cannot_verify"
    assert b.sent == []
    await b.pi.close()


async def test_content_limits_links_and_length(api, business_db):
    b = await bridge(api, business_db)
    link = await b.post(b.send_payload(text="Pay now at https://evil.example/pay"))
    assert link.status_code == 422 and link.json()["reason"] == "link_not_allowed"
    bare = await b.post(b.send_payload(text="Pay now at evil.com"))
    assert bare.status_code == 422
    long = await b.post(b.send_payload(text="x" * 1001))
    assert long.status_code == 422 and long.json()["reason"] == "text_too_long"
    bad_template = await b.post(b.send_payload(template={"name": "A B", "language": "en"}))
    assert bad_template.status_code == 422 and bad_template.json()["reason"] == "bad_template"
    assert b.sent == []
    await b.pi.close()


async def test_a_provider_refusal_is_a_non_2xx_with_a_short_reason_and_an_audit_row(
    api, business_db
):
    b = await bridge(api, business_db)
    b.refuse["code"] = "131047"
    response = await b.post(b.send_payload())
    assert response.status_code == 422 and response.json()["ok"] is False
    assert response.json()["reason"] == "whatsapp_rejected"
    [row] = await b.audit()
    assert row.outcome == "failed" and row.reason == "whatsapp_rejected"
    await b.pi.close()


# --- the contract: scripts/credits-pi-simulator.mjs played against pi's handlers ---


async def test_contract_simulator_scenarios(api, business_db):
    """A port of the steps of nori's credits-pi-simulator.mjs, pi's half, against our handlers."""
    from app.modules.pi_saas.nori_credits import capture
    from app.modules.pi_saas.nori_credits.client import NoriClient
    from app.modules.pi_saas.nori_credits.config import WorkspaceBridge, read_env

    b = await bridge(api, business_db)
    nori = b.nori
    env = read_env(b.pi.app.state.settings)
    client = NoriClient(env, b.pi.ctx["http"], WorkspaceBridge())

    # 1. the front door is signed: a client with a wrong secret is refused by nori and pi fails open
    wrong = NoriClient(
        read_env(SimpleNamespace(workzap_bridge_secret=SecretStr("w" * 20), nori_base_url=BASE)),
        b.pi.ctx["http"],
        WorkspaceBridge(),
    )
    assert (await wrong.identify(MEMBER)).checked is False
    IDENTIFY_CACHE.clear()
    reset_breakers()
    client = NoriClient(env, b.pi.ctx["http"], WorkspaceBridge())

    # 2. who is this number
    member = await client.identify(MEMBER)
    assert member.known and member.member["full_name"] == "Ali Member"
    assert not (await client.identify(STRANGER)).known

    # 3. every message goes to nori first
    await b.say(OWNER, "balance", "wamid.sim-1")
    assert b.texts_to(OWNER)[-1].startswith("You have 12,000 credits left")
    await b.say(MEMBER, "Fix: the logo is blurry on the invoice", "wamid.sim-2")
    reply = b.texts_to(MEMBER)[-1]
    number = int(reply.split("#")[1].split()[0])
    await b.say(MEMBER, f"make #{number} urgent", "wamid.sim-3")
    assert b.texts_to(MEMBER)[-1] == f"Request #{number} is now urgent."
    before = len(nori.requests)
    await b.say(STRANGER, "hello", "wamid.sim-4")
    # the stranger's identify came from the cache; in any case no text went to nori for them
    assert not [p for p, _ in nori.requests[before:] if p == "/api/workzap/inbound"]
    # nori queues the urgent alert for the on-call person and sends it through pi's send door
    alert = await b.post(b.send_payload(to=STAFF, text="Urgent request #12 needs attention."))
    assert alert.status_code == 403  # STAFF is neither a member by identify nor has messaged pi
    nori.members[STAFF] = {"full_name": "On Call", "is_owner": False, "head": True}
    IDENTIFY_CACHE.clear()
    alert = await b.post(b.send_payload(to=STAFF, text="Urgent request #12 needs attention."))
    assert alert.status_code == 200 and b.texts_to(STAFF) == ["Urgent request #12 needs attention."]

    # 4. the structured calls after pi understood a message
    first = await client.structured(
        "request", HEAD, type="Change", title="Move the banner", message_id="wamid.SIM1"
    )
    assert first.data["ok"] is True and isinstance(first.data["number"], int)
    dup = await client.structured(
        "request", HEAD, type="Change", title="Move the banner", message_id="wamid.SIM1"
    )
    assert dup.data["duplicate"] is True
    assert (await client.structured("priority", HEAD, number=number, level="High")).data["ok"]
    attach = await client.structured(
        "attach",
        MEMBER,
        number=number,
        file={"kind": "image", "url": "https://files.example/logo.png", "name": "logo.png"},
        message_id="wamid.SIM2",
    )
    assert attach.data["ok"] is True
    topup = await client.structured("topup", OWNER, credits=5000, message_id="wamid.SIM3")
    assert "Top up of 5,000 credits" in topup.data["reply"]
    refused = await client.structured("topup", MEMBER, credits=5000)
    assert "Only the company owner" in refused.data["reply"]
    build = await client.structured("request", "923004444444", type="New build", title="App")
    assert build.data["reason"] == "new_builds_not_allowed"  # not a member: not_set_up here
    # 5. the send door: {to, text, ts} signed and fresh, and the template outside the window
    sent = await b.post(b.send_payload(to=OWNER, text="Your top up is confirmed."))
    assert sent.status_code == 200
    template = {
        "name": "credits_topup_confirmed",
        "language": "en",
        "params": ["Top up confirmed."],
    }
    tpl = await b.post(b.send_payload(to=OWNER, text="Top up confirmed.", template=template))
    assert tpl.status_code == 200
    b.refuse["code"] = "500"
    failed = await b.post(b.send_payload(to=OWNER, text="Your credits are running low."))
    b.refuse["code"] = None
    assert failed.status_code in (422, 502) and failed.json()["ok"] is False

    # 6. the requirements inbox
    created = await capture.capture_nori_item(
        client,
        MEMBER,
        kind="problem",
        title="Invoice logo is blurry",
        description="Printed invoices show a fuzzy logo.",
        expected="A sharp logo",
        what_happened="Blurred",
        page="/finance/invoices",
        module="finance",
        severity="high",
        language="en",
        message_id="wamid.SIMCAP1",
    )
    assert created.ok and created.ref.startswith("R")
    again = await capture.capture_nori_item(
        client, MEMBER, kind="problem", title="Invoice logo is blurry", message_id="wamid.SIMCAP1"
    )
    assert again.data["duplicate"] is True
    assert (await capture.nori_item_status(client, MEMBER, created.ref)).data["item"][
        "status"
    ] == "new"
    nori.team_question = "Is it only the invoices?"
    followups = await capture.nori_item_followups(client, MEMBER)
    assert followups.data["items"][0]["question"] == "Is it only the invoices?"
    answer = await capture.nori_item_reply(client, MEMBER, created.ref, "Also the delivery notes.")
    assert answer.data["status"] == "reviewing"
    fixed = await client.structured("item_feedback", MEMBER, item=created.ref, outcome="fixed")
    assert fixed.data["status"] == "closed"
    stranger = await capture.capture_nori_item(client, STRANGER, kind="problem", title="who am i")
    assert not stranger.ok and stranger.reason == "not_member"
    await b.pi.close()


async def test_a_system_reply_with_a_foreign_link_is_replaced_not_sent(api, business_db):
    b = await bridge(api, business_db)
    b.nori.credits = 1
    original = b.nori.__class__.inbound
    b.nori.__class__.inbound = lambda self, body: {
        "handled": True,
        "reply": "Pay at https://evil.example/x",
    }
    try:
        await b.say(OWNER, "balance", "wamid.link-1")
    finally:
        b.nori.__class__.inbound = original
    assert b.texts_to(OWNER) == [hook.LINK_FALLBACK]
    await b.pi.close()
