"""pi talks with the person on a meeting link: off until the workspace and the meeting both allow
it, an opening that says pi is an AI, a reply for each thing the person says, a reply the code
refuses becomes the safe line, muting is instant, and every line lands in the transcript."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import guest_routes, voice, voice_routes
from app.modules.pi_meetings.models import PiMeetingSegment

pytestmark = pytest.mark.integration
JOIN = "/api/v1/public/meeting-join"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64


class Brain:
    """Speech-to-text and the model, as the test wants them."""

    def __init__(self):
        self.heard = "our stock runs out every week"
        self.reply = "How often does that happen?"
        self.stt_down = False

    async def transcribe(self, scope, audio, mime, **kw):
        from app.ai.errors import GatewayUnavailable

        if self.stt_down:
            raise GatewayUnavailable()
        return SimpleNamespace(text=self.heard, language="en")

    async def complete_structured(self, scope, output, **kw):
        return SimpleNamespace(value=output(reply=self.reply))


@pytest.fixture
def brain(monkeypatch):
    b = Brain()
    monkeypatch.setattr(voice_routes, "build_llm_manager", lambda *a, **k: b)
    return b


async def switch(api, voice_on=True):
    rules = {"meeting_intel": True, "meeting_guests": True, "meeting_voice": voice_on}
    r = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": rules}},
    )
    assert r.status_code == 200, r.text


async def ready(api, speak=True):
    """A meeting with a link and one guest; pi set to speak unless told otherwise."""
    mid = (await api.post(BASE, json=body())).json()["id"]
    invite = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    joined = await api.post(f"{JOIN}/{invite}", json={"name": "Owner", "consent": True})
    guest = joined.json()["guest_token"]
    if speak:
        r = await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "speak"})
        assert r.status_code == 200, r.text
    return mid, invite, guest


def turn(api, token, audio=None):
    kwargs = {"headers": {"X-Guest-Token": token}}
    if audio is not None:
        kwargs["files"] = {"file": ("c.webm", audio, "audio/webm;codecs=opus")}
        kwargs["data"] = {"duration_ms": "3000"}
    return api.post(f"{JOIN}/guest/pi-turn", **kwargs)


async def lines(db, mid):
    db.expire_all()
    rows = await db.execute(
        select(PiMeetingSegment.ordinal, PiMeetingSegment.text)
        .where(PiMeetingSegment.meeting_id == mid)
        .order_by(PiMeetingSegment.ordinal)
    )
    return [t for _, t in rows.all()]


async def test_pi_does_not_talk_until_the_workspace_and_the_meeting_allow_it(
    api, business_db, brain
):
    pi, conv, scope = await workspace(api, business_db, "367100001")
    await switch(api, voice_on=False)
    mid, invite, guest = await ready(api, speak=False)
    refuse = await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "speak"})
    assert refuse.status_code == 403 and refuse.json()["error"]["code"] == "MEETING_VOICE_OFF"
    off = await turn(api, guest)
    assert off.status_code == 409 and off.json()["error"]["code"] == "PI_NOT_SPEAKING"
    assert (await api.get(f"{JOIN}/{invite}")).json()["pi_voice"] is False

    await switch(api)  # the workspace allows it, the meeting is still 'off'
    assert (await turn(api, guest)).status_code == 409
    assert (await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "loud"})).status_code == 422
    assert (await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "listen"})).status_code == 200
    assert (await turn(api, guest)).status_code == 409  # listening is not speaking
    assert (await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "speak"})).status_code == 200
    assert (await api.get(f"{JOIN}/{invite}")).json()["pi_voice"] is True
    await pi.close()


async def test_pi_opens_by_saying_it_is_an_ai_and_asking_one_question(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100002")
    await switch(api)
    mid, invite, guest = await ready(api)
    opening = await turn(api, guest)
    assert opening.status_code == 200, opening.text
    words = opening.json()["reply"]
    assert "AI" in words and words.count("?") == 1 and words.endswith("?")
    assert await lines(business_db, mid) == [words]
    again = await turn(api, guest)  # a reload: the same words, nothing doubled
    assert again.json()["reply"] == words and again.json()["again"] is True
    assert len(await lines(business_db, mid)) == 1
    await pi.close()


async def test_a_turn_stores_what_was_said_and_what_pi_answered_in_order(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100003")
    await switch(api)
    mid, invite, guest = await ready(api)
    opening = (await turn(api, guest)).json()["reply"]
    got = await turn(api, guest, WEBM)
    assert got.status_code == 200, got.text
    out = got.json()
    assert out["heard"] is True and out["reply"] == "How often does that happen?"
    assert out["fallback"] is False
    assert await lines(business_db, mid) == [
        opening,
        "our stock runs out every week",
        "How often does that happen?",
    ]
    detail = (await api.get(f"{BASE}/{mid}")).json()
    speakers = [s["speaker"] for s in detail["segments"]]
    assert speakers == [voice.PI_LABEL, "Owner", voice.PI_LABEL]
    roles = {s["label"]: s["role"] for s in detail["speakers"]}
    assert roles[voice.PI_LABEL] == "staff" and roles["Owner"] == "unknown"
    business_db.expire_all()
    events = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_pi_turn")
        )
    )
    assert len(events) == 2 and all("stock" not in str(e.details) for e in events)
    await pi.close()


async def test_a_reply_that_sells_is_replaced_by_the_safe_line(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100004")
    await switch(api)
    mid, invite, guest = await ready(api)
    await turn(api, guest)
    brain.reply = "I can fix that for Rs 5000. Want it?"
    out = (await turn(api, guest, WEBM)).json()
    assert out["fallback"] is True and "5000" not in out["reply"] and out["reply"].endswith("?")
    assert not any("5000" in t for t in await lines(business_db, mid))
    await pi.close()


async def test_silence_costs_nothing_and_a_card_number_is_not_stored(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100005")
    await switch(api)
    mid, invite, guest = await ready(api)
    await turn(api, guest)
    brain.heard = ""
    quiet = (await turn(api, guest, WEBM)).json()
    assert quiet == {"heard": False, "reply": ""}
    brain.heard = "my card is 4111 1111 1111 1111 and it keeps failing"
    await turn(api, guest, WEBM)
    said = " ".join(await lines(business_db, mid))
    assert "4111" not in said and "failing" in said
    await pi.close()


async def test_muting_is_instant_and_the_guest_cannot_bypass_it(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100006")
    await switch(api)
    mid, invite, guest = await ready(api)
    await turn(api, guest)
    assert (await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "off"})).status_code == 200
    muted = await turn(api, guest, WEBM)
    assert muted.status_code == 409 and muted.json()["error"]["code"] == "PI_NOT_SPEAKING"
    assert len(await lines(business_db, mid)) == 1  # nothing more was written
    await pi.close()


async def test_bad_tokens_clips_and_a_provider_that_is_down(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100007")
    await switch(api)
    mid, invite, guest = await ready(api)
    await turn(api, guest)
    assert (await turn(api, "x" * 43)).status_code == 404
    bad = await api.post(
        f"{JOIN}/guest/pi-turn",
        headers={"X-Guest-Token": guest},
        files={"file": ("c.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "MEETING_AUDIO_INVALID"
    brain.stt_down = True
    down = await turn(api, guest, WEBM)
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_TRANSCRIBE_FAILED"
    await pi.close()


async def test_a_guest_cannot_take_pis_name(api, business_db, brain):
    pi, conv, scope = await workspace(api, business_db, "367100008")
    await switch(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    invite = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    got = await api.post(f"{JOIN}/{invite}", json={"name": "pi (AI)", "consent": True})
    assert got.json()["label"] != voice.PI_LABEL
    assert "pi (ai)" in guest_routes.RESERVED_LABELS
    await pi.close()
