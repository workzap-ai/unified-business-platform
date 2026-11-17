"""pi's bot in a Zoom, Meet or Teams call: off until the workspace and the key allow it, consent
and a real link first, one bot per call, the provider's callbacks only when signed, words become the
transcript (once each), the call's end hands the meeting to analysis, and leaving is instant."""

import base64
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import bot_routes
from app.modules.pi_meetings.bot_provider import BotProviderError
from app.modules.pi_meetings.models import PiMeetingBot, PiMeetingParticipant, PiMeetingSegment

pytestmark = pytest.mark.integration
HOOK = "/api/v1/public/recall/webhook"
KEY = b"integration-test-webhook-secret!"
SECRET = "whsec_" + base64.b64encode(KEY).decode()
ZOOM = "https://us02web.zoom.us/j/81234567890?pwd=abc"


class Provider:
    name = "recall"

    def __init__(self):
        self.joined = []
        self.left = []
        self.fail = None
        self.latest = None

    async def join(self, **kw):
        if self.fail:
            raise self.fail
        self.joined.append(kw)
        return f"bot-{len(self.joined)}"

    async def leave(self, bot_id):
        self.left.append(bot_id)

    async def status(self, bot_id):
        return self.latest


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(bot_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(bot_routes, "public_base", lambda request: "https://api.example.test")
    monkeypatch.setattr(bot_routes, "webhook_secret", lambda request: SECRET)
    return p


async def switch(api, bot=True):
    brain = {"meeting_intel": True, "meeting_bot": bot}
    r = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert r.status_code == 200, r.text


def send(api, url=ZOOM, **kw):
    return api.post(f"{BASE}/bot", json={"meeting_url": url, "consent": True, **kw})


def signed(payload: dict, key=KEY):
    raw = json.dumps(payload).encode()
    mac = hmac.new(key, b"msg_1.1700000000." + raw, hashlib.sha256).digest()
    headers = {
        "webhook-id": "msg_1",
        "webhook-timestamp": "1700000000",
        "webhook-signature": "v1," + base64.b64encode(mac).decode(),
        "content-type": "application/json",
    }
    return raw, headers


def hook(api, payload, **kw):
    raw, headers = signed(payload, **kw)
    return api.post(HOOK, content=raw, headers=headers)


def words(bot, text, who="Ayesha", start=1.0, pid=7):
    return {
        "event": "transcript.data",
        "data": {
            "data": {
                "words": [
                    {
                        "text": w,
                        "start_timestamp": {"relative": start + i * 0.3},
                        "end_timestamp": {"relative": start + i * 0.3 + 0.2},
                    }
                    for i, w in enumerate(text.split())
                ],
                "participant": {"id": pid, "name": who},
            },
            "bot": {"id": bot},
        },
    }


def status(bot, code, sub=None):
    return {
        "event": f"bot.{code}",
        "data": {"data": {"code": code, "sub_code": sub}, "bot": {"id": bot}},
    }


async def lines(db, mid):
    db.expire_all()
    rows = await db.execute(
        select(PiMeetingSegment.ordinal, PiMeetingParticipant.label, PiMeetingSegment.text)
        .join(PiMeetingParticipant, PiMeetingParticipant.id == PiMeetingSegment.participant_id)
        .where(PiMeetingSegment.meeting_id == mid)
        .order_by(PiMeetingSegment.ordinal)
    )
    return rows.all()


async def test_it_is_off_until_the_workspace_and_the_service_allow_it(
    api, business_db, provider, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "368100001")
    await switch(api, bot=False)
    off = await send(api)
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_BOT_OFF"
    await switch(api)
    monkeypatch.setattr(bot_routes, "provider_for", lambda request: None)
    none = await send(api)
    assert none.status_code == 503 and none.json()["error"]["code"] == "MEETING_BOT_UNCONFIGURED"
    assert provider.joined == []
    await pi.close()


async def test_consent_and_a_real_link_come_first(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "368100002")
    await switch(api)
    no = await api.post(f"{BASE}/bot", json={"meeting_url": ZOOM, "consent": False})
    assert no.status_code == 422 and no.json()["error"]["code"] == "MEETING_CONSENT_REQUIRED"
    for url in ("https://evil.example.com/j/81234567890", "http://zoom.us/j/81234567890"):
        bad = await send(api, url)
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "MEETING_LINK_INVALID"
    unknown = await send(api, customer_id="00000000-0000-0000-0000-000000000001")
    assert unknown.status_code == 404
    assert provider.joined == []
    await pi.close()


async def test_the_bot_joins_as_an_ai_and_the_link_is_not_stored(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "368100003")
    await switch(api)
    r = await send(api, title="Call with Ayesha")
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["meeting"]["source"] == "zoom" and out["bot"]["status"] == "requested"
    sent = provider.joined[0]
    assert "AI" in sent["bot_name"] and sent["meeting_url"] == ZOOM
    assert sent["webhook_url"] == "https://api.example.test/api/v1/public/recall/webhook"
    business_db.expire_all()
    row = await business_db.scalar(select(PiMeetingBot))
    assert row.external_id == "bot-1" and row.host == "us02web.zoom.us"
    assert "81234567890" not in repr(vars(row)) and "pwd" not in repr(vars(row))
    again = await send(api)  # the same call: pi is already on its way
    assert again.status_code == 409 and again.json()["error"]["code"] == "MEETING_BOT_ALREADY_IN"
    events = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_bot_requested")
        )
    )
    assert len(events) == 1 and "81234567890" not in str(events[0].details)
    await pi.close()


async def test_a_provider_that_refuses_fails_the_meeting_not_the_page(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "368100004")
    await switch(api)
    provider.fail = BotProviderError("BOT_PROVIDER_KEY_REJECTED", "not accepted", 503)
    r = await send(api)
    assert r.status_code == 503 and r.json()["error"]["code"] == "BOT_PROVIDER_KEY_REJECTED"
    business_db.expire_all()
    row = await business_db.scalar(select(PiMeetingBot))
    assert row.status == "failed" and row.external_id is None
    provider.fail = None
    retry = await send(api)  # a failed bot does not block the next try
    assert retry.status_code == 201
    await pi.close()


async def test_callbacks_need_the_providers_signature(api, business_db, provider, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "368100005")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    raw, headers = signed(words("bot-1", "we sell tiles"), key=b"some-other-secret-0123456789ab")
    wrong = await api.post(HOOK, content=raw, headers=headers)
    assert wrong.status_code == 401
    assert await api.post(HOOK, content=raw) is not None  # no headers at all
    assert (await api.post(HOOK, content=raw)).status_code == 401
    assert await lines(business_db, mid) == []
    monkeypatch.setattr(bot_routes, "webhook_secret", lambda request: None)
    closed = await hook(api, words("bot-1", "we sell tiles"))
    assert closed.status_code == 503  # no secret configured: everything is refused
    await pi.close()


async def test_words_become_transcript_lines_once_each_with_the_name_the_call_shows(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "368100006")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    assert (await hook(api, status("bot-1", "in_call_recording"))).status_code == 200
    first = words("bot-1", "our stock runs out every week")
    assert (await hook(api, first)).status_code == 200
    assert (await hook(api, first)).status_code == 200  # a retry: stored once
    await hook(api, words("bot-1", "call me on 0300 1234567 please", who="Bilal", start=9.0, pid=8))
    await hook(api, words("bot-1", "I am pi", who="pi (AI)", start=12.0, pid=9))
    got = await lines(business_db, mid)
    assert [(o, label) for o, label, _ in got] == [
        (0, "Ayesha"),
        (1, "Bilal"),
        (2, "pi (AI) (call)"),  # nobody in a call can take pi's name
    ]
    assert got[0][2] == "our stock runs out every week"
    assert "1234567" not in got[1][2]  # a phone number is taken out before it is stored
    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert {s["label"]: s["role"] for s in detail["speakers"]} == {
        "Ayesha": "unknown",
        "Bilal": "unknown",
        "pi (AI) (call)": "unknown",
    }
    assert detail["status"] == "transcribing"
    await pi.close()


async def test_a_callback_for_an_unknown_bot_or_a_workspace_that_switched_off_changes_nothing(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "368100007")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    assert (await hook(api, words("someone-elses-bot", "hello there"))).status_code == 200
    await switch(api, bot=False)
    assert (await hook(api, words("bot-1", "hello there"))).status_code == 200
    assert await lines(business_db, mid) == []
    await pi.close()


async def test_the_end_of_the_call_hands_the_meeting_to_analysis_and_a_late_word_cannot_undo_it(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "368100008")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    await hook(api, status("bot-1", "joining_call"))
    await hook(api, status("bot-1", "in_waiting_room"))
    await hook(api, status("bot-1", "in_call_recording"))
    await hook(api, words("bot-1", "our stock runs out every week"))
    await hook(api, status("bot-1", "joining_call"))  # late and out of order: ignored
    got = (await api.get(f"{BASE}/{mid}/bot")).json()
    assert got["bot"]["status"] == "recording" and got["bot"]["active"] is True
    await hook(api, status("bot-1", "call_ended"))
    await hook(api, status("bot-1", "done"))
    got = (await api.get(f"{BASE}/{mid}/bot")).json()
    assert got["bot"]["status"] == "done" and got["bot"]["active"] is False
    assert got["meeting_status"] == "analysing"
    await pi.close()


async def test_a_call_with_no_speech_fails_clearly_and_a_refused_bot_says_why(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "368100009")
    await switch(api)
    quiet = (await send(api)).json()["meeting"]["id"]
    await hook(api, status("bot-1", "done"))
    meeting = (await api.get(f"{BASE}/{quiet}")).json()
    assert meeting["status"] == "failed" and "No speech" in meeting["failure_reason"]
    other = (await send(api, "https://meet.google.com/abc-defg-hij")).json()["meeting"]["id"]
    await hook(api, status("bot-2", "recording_permission_denied"))
    meeting = (await api.get(f"{BASE}/{other}")).json()
    assert meeting["status"] == "failed" and "did not allow" in meeting["failure_reason"]
    await pi.close()


async def test_the_page_asks_the_provider_when_status_callbacks_are_not_set_up(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "368100010")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    provider.latest = ("in_waiting_room", "")
    got = (await api.get(f"{BASE}/{mid}/bot")).json()
    assert got["bot"]["status"] == "waiting"
    await pi.close()


async def test_leaving_is_instant_and_only_while_the_bot_is_in_the_call(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "368100011")
    await switch(api)
    mid = (await send(api)).json()["meeting"]["id"]
    out = await api.post(f"{BASE}/{mid}/bot/leave")
    assert out.status_code == 200 and out.json()["bot"]["status"] == "ended"
    assert provider.left == ["bot-1"]
    again = await api.post(f"{BASE}/{mid}/bot/leave")
    assert again.status_code == 409 and again.json()["error"]["code"] == "MEETING_BOT_NOT_ACTIVE"
    assert (await send(api)).status_code == 201  # and pi can be sent back for a new visit
    await pi.close()
