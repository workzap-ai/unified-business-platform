"""nori credits bridge: the parts that need no database (gates, signing, breaker, client, content
rules, capture library). A fake nori on an httpx MockTransport; no network."""

import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.modules.pi_saas.nori_credits import capture, hook, signing
from app.modules.pi_saas.nori_credits.client import NoriClient
from app.modules.pi_saas.nori_credits.config import (
    WorkspaceBridge,
    read_env,
    validate_workspace_section,
    workspace_bridge,
)
from app.modules.pi_saas.nori_credits.resilience import (
    IDENTIFY_CACHE,
    METRICS,
    Breaker,
    mask_number,
    reset_breakers,
)
from app.modules.pi_saas.nori_credits.send_door import check_content, foreign_urls, parse_ts
from app.shared.errors import BusinessRuleViolation
from tests.support.fake_nori import BASE, MEMBER, SECRET, STRANGER, FakeNori


@pytest.fixture(autouse=True)
def clean():
    reset_breakers()
    IDENTIFY_CACHE.clear()
    METRICS.reset()
    yield
    reset_breakers()
    IDENTIFY_CACHE.clear()


def settings(**over):
    base = {
        "workzap_bridge_secret": SecretStr(SECRET),
        "nori_base_url": BASE,
        "nori_bridge_kill": False,
        "nori_bridge_url": "",
        "nori_bridge_secret": None,
        "nori_bridge_phone_number_id": "",
    }
    return SimpleNamespace(**{**base, **over})


def client_for(nori, bridge=None, secret=SECRET):
    http = httpx.AsyncClient(transport=httpx.MockTransport(nori))
    env = read_env(settings(workzap_bridge_secret=SecretStr(secret)))
    return NoriClient(env, http, bridge or WorkspaceBridge())


# --- gates ---


def test_env_needs_both_variables_and_a_sane_url_and_secret():
    assert read_env(settings()) is not None
    assert read_env(settings(nori_base_url="")) is None
    assert read_env(settings(workzap_bridge_secret=None)) is None
    assert read_env(settings(workzap_bridge_secret=SecretStr("short"))) is None
    assert read_env(settings(nori_base_url="http://nori.example")) is None  # https only
    assert read_env(settings(nori_base_url="https://nori.example/some/path")) is None
    assert read_env(settings(nori_base_url="http://localhost:3000")) is not None
    assert read_env(settings(nori_base_url="https://nori.test/")).base_url == "https://nori.test"


def test_workspace_flag_defaults_to_off_and_only_true_turns_it_on():
    from app.modules.pi.configuration import DEFAULTS

    assert DEFAULTS["response_rules"]["nori_bridge"] == {"enabled": False}
    assert workspace_bridge(None) is None
    assert workspace_bridge({}) is None
    assert workspace_bridge({"nori_bridge": {"enabled": False}}) is None
    for truthy in ("true", 1, "yes", None):
        assert workspace_bridge({"nori_bridge": {"enabled": truthy}}) is None
    assert workspace_bridge({"nori_bridge": {"enabled": True}}).timeout == 2.5
    # a malformed section never half-enables the bridge
    assert workspace_bridge({"nori_bridge": {"enabled": True, "timeout_seconds": "x"}}) is None


def test_section_validation_rejects_unknown_keys_and_out_of_range_numbers():
    assert validate_workspace_section({"enabled": True, "timeout_seconds": 1.5})
    assert not validate_workspace_section({"enabled": True, "evil": 1})
    assert not validate_workspace_section({"timeout_seconds": 99})
    assert not validate_workspace_section({"enabled": "true"})
    assert not validate_workspace_section([])


def test_the_settings_validator_runs_the_section_check():
    from app.modules.pi.configuration import DEFAULTS
    from app.modules.pi.policy import validate_section

    good = {**DEFAULTS["response_rules"], "nori_bridge": {"enabled": True}}
    validate_section("response_rules", good)
    with pytest.raises(BusinessRuleViolation):
        validate_section("response_rules", {**good, "nori_bridge": {"enabled": "yes"}})


# --- signing ---


def test_signature_round_trip_and_refusals():
    raw = b'{"to":"923001234567"}'
    header = signing.sign(SECRET, raw)
    assert header.startswith("sha256=")
    assert signing.verify(SECRET, raw, header)
    assert signing.verify(SECRET, raw, header.upper().replace("SHA256=", "sha256="))
    assert not signing.verify(SECRET, raw + b" ", header)
    assert not signing.verify("other-secret-other-secret", raw, header)
    assert not signing.verify(SECRET, raw, None)
    assert not signing.verify(SECRET, raw, "")
    assert not signing.verify(SECRET, raw, header.removeprefix("sha256="))  # prefix required


# --- breaker ---


def test_breaker_closed_open_half_open_probe():
    now = [0.0]
    breaker = Breaker(3, 30, clock=lambda: now[0])
    assert breaker.allow() and breaker.state == "closed"
    breaker.failure()
    breaker.failure()
    assert breaker.allow() and breaker.state == "closed"
    breaker.failure()
    assert breaker.state == "open" and not breaker.allow()
    now[0] = 29
    assert not breaker.allow()
    now[0] = 31
    assert breaker.allow() and breaker.state == "half_open"  # the probe
    assert not breaker.allow()  # only one probe at a time
    breaker.failure()  # the probe failed: open again, cooldown restarts
    assert breaker.state == "open" and not breaker.allow()
    now[0] = 62
    assert breaker.allow()
    breaker.success()
    assert breaker.state == "closed" and breaker.failures == 0 and breaker.allow()


def test_a_success_resets_the_failure_count():
    breaker = Breaker(3, 30)
    breaker.failure()
    breaker.failure()
    breaker.success()
    breaker.failure()
    breaker.failure()
    assert breaker.state == "closed"


# --- client: every error class fails open and is counted ---


@pytest.mark.parametrize(
    ("mode", "reason"),
    [
        ("timeout", "timeout"),
        ("connect", "connect"),
        ("500", "http_5xx"),
        ("401", "bad_signature"),
        ("badjson", "bad_response"),
        ("list", "bad_response"),
    ],
)
async def test_client_returns_a_reason_for_every_error_class(mode, reason):
    nori = FakeNori()
    nori.mode = mode
    result = await client_for(nori).inbound(
        sender=MEMBER, message_id="wamid.1", text="balance", name=None
    )
    assert not result.ok and result.reason == reason
    assert METRICS.snapshot()[f"call:{reason}"] == 1


async def test_wrong_secret_is_refused_by_nori_and_fails_open():
    nori = FakeNori()
    result = await client_for(nori, secret="a-different-secret-0000").identify(MEMBER)
    assert not result.checked and not result.known


async def test_an_unsigned_looking_response_signature_is_refused():
    def handler(request):
        return httpx.Response(
            200, json={"handled": True, "reply": "x"}, headers={"x-workzap-signature": "sha256=00"}
        )

    result = await client_for(handler).inbound(sender=MEMBER, message_id="m", text="t", name=None)
    assert not result.ok and result.reason == "bad_signature"


async def test_a_validation_answer_does_not_open_the_circuit():
    def handler(request):
        return httpx.Response(422, json={"ok": False, "reason": "invalid_title"})

    client = client_for(handler, WorkspaceBridge(breaker_failures=2))
    for _ in range(5):
        result = await client.structured("capture", MEMBER, kind="problem")
        assert result.reason == "http_4xx"
    assert client.breaker.state == "closed"


async def test_circuit_opens_after_n_failures_skips_calls_then_probes():
    nori = FakeNori()
    nori.mode = "500"
    now = [0.0]
    bridge = WorkspaceBridge(breaker_failures=3, breaker_cooldown=30)
    client = client_for(nori, bridge)
    client.breaker.clock = lambda: now[0]
    for _ in range(3):
        await client.inbound(sender=MEMBER, message_id="m", text="t", name=None)
    assert client.breaker.state == "open"
    seen = len(nori.requests)
    result = await client.inbound(sender=MEMBER, message_id="m", text="t", name=None)
    assert result.reason == "circuit_open" and len(nori.requests) == seen
    nori.mode = "ok"
    now[0] = 31
    probe = await client.identify(MEMBER)  # the half-open probe goes through
    assert probe.checked and client.breaker.state == "closed"


async def test_identify_sends_the_number_only_and_is_cached():
    nori = FakeNori()
    client = client_for(nori)
    first = await client.identify("+92 300-2222222")
    again = await client.identify(MEMBER)
    assert first.known and again.known
    sent = nori.calls("/api/credits/pi", "identify")
    assert len(sent) == 1  # the second answer came from the cache
    assert set(sent[0]) == {"action", "from", "ts"} and sent[0]["from"] == MEMBER
    unknown = await client.identify(STRANGER)
    assert unknown.checked and not unknown.known


# --- the hook is inert without its gates ---


class Boom:
    """Any use of the database session or the HTTP client fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"the bridge touched {name} while it should be inert")


def event(text="balance", kind="message", message_type="text"):
    return SimpleNamespace(
        payload={
            "kind": kind,
            "message_type": message_type,
            "sender": MEMBER,
            "message_id": "wamid.1",
            "body": text,
        }
    )


async def test_hook_is_inert_when_the_server_variables_are_missing():
    for cfg in (
        settings(nori_base_url=""),
        settings(workzap_bridge_secret=None),
        settings(nori_base_url="", workzap_bridge_secret=None),
    ):
        outcome = await hook.pre_hook(
            {"settings": cfg, "http": Boom()}, Boom(), Boom(), Boom(), event()
        )
        assert outcome == hook.PASS


async def test_hook_does_nothing_for_other_events_or_when_killed():
    ctx = {"settings": settings(), "http": Boom()}
    assert await hook.pre_hook(ctx, Boom(), Boom(), Boom(), event(kind="status")) == hook.PASS
    assert (
        await hook.pre_hook(ctx, Boom(), Boom(), Boom(), event(message_type="image")) == hook.PASS
    )
    killed = {"settings": settings(nori_bridge_kill=True), "http": Boom()}
    assert await hook.pre_hook(killed, Boom(), Boom(), Boom(), event()) == hook.PASS


def test_clean_reply_strips_control_and_direction_characters_and_caps():
    assert hook.clean_reply("  hi‮ there\x00  ") == "hi there"
    assert hook.clean_reply(None) is None and hook.clean_reply("   ") is None
    assert len(hook.clean_reply("x" * 5000)) == 1000


# --- send-door content rules ---


def test_only_nori_links_are_allowed():
    host = "nori.test"
    assert foreign_urls("Pay at https://nori.test/pay/1 now", host) == []
    assert foreign_urls("see https://acme.nori.test/requests/5.", host) == []
    assert foreign_urls("see www.nori.test/x", host) == []
    assert foreign_urls("go to https://evil.example/login", host) == ["evil.example"]
    assert foreign_urls("go to evil.com/login", host) == ["evil.com"]
    assert foreign_urls("https://nori.test.evil.com/a", host) == ["nori.test.evil.com"]
    assert foreign_urls("https://evilnori.test/a", host) == ["evilnori.test"]
    assert foreign_urls("You have 4,200 credits left. Top up 5.5k.", host) == []


def test_content_check_text_template_and_limits():
    host = "nori.test"
    text, template, why = check_content("Low balance: 4,200 left.", None, host)
    assert (text, template, why) == ("Low balance: 4,200 left.", None, None)
    assert check_content("", None, host)[2] == "empty_text"
    assert check_content(5, None, host)[2] == "bad_text"
    assert check_content("x" * 1001, None, host)[2] == "text_too_long"
    assert check_content("see evil.com", None, host)[2] == "link_not_allowed"
    ok = {"name": "credits_update", "language": "en", "params": ["Low balance"]}
    assert check_content("Low balance", ok, host)[1] == ok
    for bad in (
        {"name": "Bad Name", "language": "en", "params": ["x"]},
        {"name": "ok_name", "language": "english", "params": ["x"]},
        {"name": "ok_name", "language": "en", "params": []},
        {"name": "ok_name", "language": "en", "params": [1]},
        {"name": "ok_name", "language": "en", "params": ["x"] * 11},
        "template",
    ):
        assert check_content("hello", bad, host)[2] == "bad_template"
    link = {"name": "ok_name", "language": "en", "params": ["visit evil.com"]}
    assert check_content("hello", link, host)[2] == "link_not_allowed"


def test_timestamps_in_seconds_milliseconds_and_iso():
    assert parse_ts(1731240001) == 1731240001
    assert parse_ts(1731240001000) == 1731240001
    assert parse_ts("1731240001000") == 1731240001
    assert parse_ts("2024-11-10T12:00:01Z") == 1731240001
    assert parse_ts("2024-11-10T12:00:01") is None  # no zone
    assert parse_ts(True) is None and parse_ts(None) is None and parse_ts("soon") is None


def test_masking_never_shows_a_whole_number():
    assert mask_number("+92 300 1234567") == "92***4567"
    assert "3001234567" not in mask_number("923001234567")
    assert mask_number("123") == "***"


# --- capture library ---


async def test_capture_checks_membership_first_and_sends_nothing_for_a_stranger():
    nori = FakeNori()
    result = await capture.capture_nori_item(
        client_for(nori), STRANGER, kind="problem", title="The logo is blurry"
    )
    assert not result.ok and result.reason == "not_member"
    assert nori.calls("/api/credits/pi", "capture") == []  # nothing about the problem left pi
    assert len(nori.calls("/api/credits/pi", "identify")) == 1


async def test_capture_sends_the_full_item_and_returns_nori_s_reply():
    nori = FakeNori()
    result = await capture.capture_nori_item(
        client_for(nori),
        MEMBER,
        kind="problem",
        title="  Invoice logo   is blurry ",
        description="Printed invoices show a fuzzy logo.",
        expected="A sharp logo",
        what_happened="Blurred",
        page="/finance/invoices",
        module="finance",
        severity="high",
        language="en",
        files=[{"kind": "image", "url": "https://files.example/logo.png", "name": "logo.png"}],
        message_id="wamid.CAP1",
    )
    assert result.ok and result.ref == "R11" and "Noted as R11" in result.reply
    sent = nori.calls("/api/credits/pi", "capture")[0]
    assert sent["kind"] == "problem" and sent["title"] == "Invoice logo is blurry"
    assert sent["expected"] == "A sharp logo" and sent["actual"] == "Blurred"
    assert sent["page"] == "/finance/invoices" and sent["module"] == "finance"
    assert sent["message_id"] == "wamid.CAP1" and sent["files"][0]["kind"] == "image"
    again = await capture.capture_nori_item(
        client_for(nori), MEMBER, kind="problem", title="Invoice logo is blurry",
        message_id="wamid.CAP1",
    )  # fmt: skip
    assert again.ok and again.data.get("duplicate") is True


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"kind": "bug", "title": "abc"}, "invalid_kind"),
        ({"kind": "problem", "title": "a"}, "invalid_title"),
        ({"kind": "problem", "title": "abc", "severity": "huge"}, "invalid_severity"),
        (
            {"kind": "problem", "title": "abc", "files": [{"kind": "image", "url": "http://x/y"}]},
            "bad_file",
        ),
        (
            {"kind": "problem", "title": "abc", "files": [{"kind": "exe", "url": "https://x/y"}]},
            "bad_file",
        ),
    ],
)  # fmt: skip
async def test_capture_validates_before_any_call(kwargs, reason):
    nori = FakeNori()
    result = await capture.capture_nori_item(client_for(nori), MEMBER, **kwargs)
    assert not result.ok and result.reason == reason
    assert nori.requests == []


async def test_capture_fails_soft_when_nori_is_down():
    nori = FakeNori()
    nori.mode = "connect"
    result = await capture.capture_nori_item(
        client_for(nori), MEMBER, kind="feature", title="Dark mode"
    )
    assert not result.ok and result.reason == "nori_unreachable"


async def test_status_followups_and_reply():
    nori = FakeNori()
    client = client_for(nori)
    created = await capture.capture_nori_item(client, MEMBER, kind="feature", title="Dark mode")
    status = await capture.nori_item_status(client, MEMBER, created.ref)
    assert status.ok and status.data["item"]["status"] == "new"
    assert (await capture.nori_item_status(client, MEMBER, "../etc")).reason == "no_such_item"
    assert (await capture.nori_item_followups(client, MEMBER)).data["items"] == []
    nori.team_question = "Which screen?"
    assert (await capture.nori_item_followups(client, MEMBER)).data["items"][0]["question"]
    reply = await capture.nori_item_reply(client, MEMBER, "r11", "The invoice screen")
    assert reply.ok and reply.data["status"] == "reviewing"
    assert (await capture.nori_item_reply(client, MEMBER, "R11", "   ")).reason == "invalid_text"
    assert (await capture.nori_item_status(client, STRANGER)).reason == "not_member"


def test_explicit_request_is_narrow():
    yes = [
        "Please tell the Workzap team the invoice logo is blurry",
        "can you let Workzap know that the report page is broken",
        "pass this on to the workzap team",
        "report it to Workzap",
    ]
    no = [
        "the invoice logo is blurry",
        "my balance is wrong",
        "I want to talk to a person",
        "workzap is a great product",
        "Fix: the logo is blurry",
    ]
    assert all(capture.explicit_request(t) for t in yes)
    assert not any(capture.explicit_request(t) for t in no)


def test_the_replies_in_this_package_contain_no_json_marker_of_a_body():
    # the audit and log code never takes a message body: no field of that name exists
    from app.modules.pi_saas.nori_credits.models import PiNoriBridgeLog

    columns = {c.name for c in PiNoriBridgeLog.__table__.columns}
    assert not columns & {"body", "text", "message", "payload"}
    assert json.dumps(sorted(columns))
