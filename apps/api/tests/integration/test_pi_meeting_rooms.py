"""pi's own video rooms: off until the workspace and the service allow it, consent first, staff and
guests each get a token for their own id and this one call, the provider's callbacks only when
signed, the transcript becomes lines (once each, redacted, labelled by who the room says spoke), and
the call's end hands the meeting to analysis."""

import hashlib
import hmac
import json

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import room_routes
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingParticipant,
    PiMeetingRoom,
    PiMeetingSegment,
)
from app.modules.pi_meetings.room_provider import RoomProviderError

pytestmark = pytest.mark.integration
HOOK = "/api/v1/public/stream/webhook"
JOIN = "/api/v1/public/meeting-join"
ROOM_TOKEN = "/api/v1/public/meeting-room/token"
SECRET = "integration-test-stream-secret"
CDN = "https://us-east.stream-io-cdn.com/1/video/transcription/t.jsonl"


class Provider:
    name = "stream"

    def __init__(self):
        self.created = []
        self.ended = []
        self.tokens = []
        self.fail = None
        self.rows = None  # what `transcript` returns (None = not ready)
        self.asked = []
        self.blocked = []
        self.fail_block = None
        self.muted = []
        self.fail_mute = None

    async def create_call(self, call_id, *, language, audio=False):
        if self.fail:
            raise self.fail
        self.created.append((call_id, language))
        self.audio = audio

    def user_token(self, user_id, call_id, *, ttl_s):
        self.tokens.append((user_id, call_id, ttl_s))
        return f"tok-{user_id}"

    async def end_call(self, call_id):
        self.ended.append(call_id)

    async def block_user(self, call_id, user_id):
        if self.fail_block:
            raise self.fail_block
        self.blocked.append((call_id, user_id))

    async def mute_user(self, call_id, user_id, muted):
        if self.fail_mute:
            raise self.fail_mute
        self.muted.append((call_id, user_id, muted))

    async def transcript(self, call_id, url=""):
        self.asked.append((call_id, url))
        return self.rows

    async def delete_call(self, call_id):
        pass


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: SECRET)
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def switch(api, room=True, guests=False):
    brain = {"meeting_intel": True, "meeting_room": room, "meeting_guests": guests}
    r = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert r.status_code == 200, r.text


def open_room(api, **kw):
    return api.post(f"{BASE}/rooms", json={"title": "Tiles call", "consent": True, **kw})


def signed(payload, secret=SECRET):
    raw = json.dumps(payload).encode()
    mac = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"x-signature": mac, "content-type": "application/json"}


def hook(api, payload, **kw):
    raw, headers = signed(payload, **kw)
    return api.post(HOOK, content=raw, headers=headers)


def event(room, kind, **extra):
    return {"type": kind, "call_cid": f"pi_room:{room.call_id}", **extra}


def speech(user, text, start, stop):
    return {"speaker_id": user, "type": "speech", "text": text, "start_ts": start, "stop_ts": stop}


async def the_room(db, mid):
    db.expire_all()
    return await db.scalar(select(PiMeetingRoom).where(PiMeetingRoom.meeting_id == mid))


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
    pi, conv, scope = await workspace(api, business_db, "369100001")
    await switch(api, room=False)
    off = await open_room(api)
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_ROOM_OFF"
    await switch(api)
    monkeypatch.setattr(room_routes, "provider_for", lambda request: None)
    none = await open_room(api)
    assert none.status_code == 503 and none.json()["error"]["code"] == "MEETING_ROOM_UNCONFIGURED"
    assert provider.created == []
    await pi.close()


async def test_consent_comes_first_and_the_call_id_names_nothing(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369100002")
    await switch(api)
    no = await api.post(f"{BASE}/rooms", json={"title": "x", "consent": False})
    assert no.status_code == 422 and no.json()["error"]["code"] == "MEETING_CONSENT_REQUIRED"
    assert provider.created == []
    bad = await open_room(api, language="not a language")
    assert bad.status_code == 422
    made = await open_room(api, language="en")
    assert made.status_code == 201, made.text
    mid = made.json()["meeting"]["id"]
    assert made.json()["meeting"]["source"] == "native"
    call_id = provider.created[0][0]
    assert provider.created[0][1] == "en"
    assert mid not in call_id and mid.replace("-", "") not in call_id and len(call_id) >= 30
    room = await the_room(business_db, mid)
    assert room.call_id == call_id and room.state == "created"
    audit = await business_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "pi.meeting_room_opened")
    )
    assert audit is not None
    await pi.close()


async def test_a_provider_failure_marks_the_meeting_failed_and_keeps_the_message_safe(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100003")
    await switch(api)
    provider.fail = RoomProviderError("ROOM_PROVIDER_BUSY", "busy", 429)
    r = await open_room(api)
    assert r.status_code == 429 and r.json()["error"]["code"] == "ROOM_PROVIDER_BUSY"
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.source == "native"))
    await business_db.refresh(meeting)
    assert meeting.status == "failed" and meeting.failure_reason == "busy"
    await pi.close()


async def test_a_staff_token_is_for_their_own_id_and_this_call_and_closes_with_the_room(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100004")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    call_id = provider.created[0][0]
    out = await api.post(f"{BASE}/{mid}/room/token")
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["api_key"] == "pk_test" and body["call_id"] == call_id
    assert body["user_id"].startswith("s_") and body["token"] == f"tok-{body['user_id']}"
    assert provider.tokens[-1][1] == call_id and provider.tokens[-1][2] <= 7200
    business_db.expire_all()
    staff = await business_db.scalar(
        select(PiMeetingParticipant).where(PiMeetingParticipant.stream_user_id == body["user_id"])
    )
    assert staff.role == "staff" and staff.mapped_user_id is not None
    again = await api.post(f"{BASE}/{mid}/room/token")
    assert again.json()["user_id"] == body["user_id"]  # the same person, not a second speaker
    ended = await api.post(f"{BASE}/{mid}/room/end")
    assert ended.status_code == 200 and ended.json()["room"]["state"] == "ended"
    assert provider.ended == [call_id]
    late = await api.post(f"{BASE}/{mid}/room/token")
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    twice = await api.post(f"{BASE}/{mid}/room/end")
    assert twice.status_code == 409
    await pi.close()


async def test_a_guest_enters_only_after_consent_with_a_token_for_their_own_id(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100005")
    await switch(api, guests=True)
    mid = (await open_room(api)).json()["meeting"]["id"]
    token = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    seen = await api.get(f"{JOIN}/{token}")
    assert seen.status_code == 200 and seen.json()["room"] is True
    nobody = await api.post(ROOM_TOKEN, headers={"X-Guest-Token": "x" * 43})
    assert nobody.status_code == 404
    assert (await api.post(f"{JOIN}/{token}", json={"consent": False})).status_code == 422
    joined = await api.post(f"{JOIN}/{token}", json={"name": "Ayesha", "consent": True})
    guest_token = joined.json()["guest_token"]
    out = await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest_token})
    assert out.status_code == 200, out.text
    body = out.json()
    call_id = provider.created[0][0]
    assert body["call_id"] == call_id and body["user_id"].startswith("g_")
    assert body["name"] == "Ayesha" and provider.tokens[-1][0] == body["user_id"]
    business_db.expire_all()
    person = await business_db.scalar(
        select(PiMeetingParticipant).where(PiMeetingParticipant.stream_user_id == body["user_id"])
    )
    assert person.role == "unknown"  # a guest is never assumed to be the customer
    await switch(api, room=False, guests=True)
    off = await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest_token})
    assert off.status_code == 404
    await pi.close()


async def test_a_guest_cannot_enter_a_room_that_has_ended(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369100006")
    await switch(api, guests=True)
    mid = (await open_room(api)).json()["meeting"]["id"]
    token = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    guest = (await api.post(f"{JOIN}/{token}", json={"consent": True})).json()["guest_token"]
    await api.post(f"{BASE}/{mid}/room/end")
    late = await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest})
    assert late.status_code == 409 and late.json()["error"]["code"] == "MEETING_ROOM_CLOSED"
    await pi.close()


async def test_the_callback_needs_a_valid_signature_and_a_secret(
    api, business_db, provider, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "369100007")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    payload = event(room, "call.session_ended")
    raw = json.dumps(payload).encode()
    unsigned = await api.post(HOOK, content=raw, headers={"content-type": "application/json"})
    assert unsigned.status_code == 401
    wrong = await hook(api, payload, secret="another")
    assert wrong.status_code == 401
    assert (await the_room(business_db, mid)).state == "created"
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: None)
    none = await hook(api, payload)
    assert none.status_code == 503
    await pi.close()


async def test_the_transcript_becomes_lines_once_redacted_and_labelled_by_who_spoke(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100008")
    await switch(api, guests=True)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    token = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    guest = (await api.post(f"{JOIN}/{token}", json={"name": "Ayesha", "consent": True})).json()
    gid = (await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest["guest_token"]})).json()[
        "user_id"
    ]
    assert (await hook(api, event(room, "call.session_started"))).status_code == 200
    assert (await the_room(business_db, mid)).state == "live"
    provider.rows = [
        speech(gid, "Our stock runs out and orders get late.", 6000, 9000),
        speech(staff, "How often does that happen?", 1000, 3000),
        speech(gid, "Call me on 0300 1234567 please.", 10000, 12000),
        speech("pi_server", "I should not be a speaker.", 13000, 14000),
        {"speaker_id": staff, "type": "something_else", "text": "x", "start_ts": 1, "stop_ts": 2},
    ]
    await hook(api, event(room, "call.session_ended"))
    done = await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    assert done.status_code == 200
    assert provider.asked[-1] == (room.call_id, CDN)
    got = await lines(business_db, mid)
    assert [(label, text.split()[0]) for _, label, text in got] == [
        ("Staff", "How"),
        ("Ayesha", "Our"),
        ("Ayesha", "Call"),
    ]
    assert "1234567" not in got[2][2] and [o for o, _, _ in got] == [0, 1, 2]
    room = await the_room(business_db, mid)
    assert room.state == "ended" and room.transcript_state == "done" and room.lines == 3
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    await business_db.refresh(meeting)
    assert meeting.status == "analysing" and meeting.duration_ms == 12000
    # the provider retries: nothing is stored twice
    await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    assert len(await lines(business_db, mid)) == 3
    await pi.close()


async def test_an_empty_transcript_is_a_failed_meeting_not_an_empty_review(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100009")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    provider.rows = []
    await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    await business_db.refresh(meeting)
    assert meeting.status == "failed" and "No speech" in meeting.failure_reason
    await pi.close()


async def test_when_the_callback_never_comes_the_status_page_fetches_the_transcript(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100010")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    await api.post(f"{BASE}/{mid}/room/end")
    waiting = await api.get(f"{BASE}/{mid}/room")
    assert waiting.json()["room"]["state"] == "ended"
    assert waiting.json()["room"]["transcript_state"] == "pending"
    provider.rows = [speech(staff, "We agreed to send the quote on Monday.", 1000, 4000)]
    ready = await api.get(f"{BASE}/{mid}/room")
    assert ready.json()["room"]["transcript_state"] == "done" and ready.json()["room"]["lines"] == 1
    assert ready.json()["meeting_status"] == "analysing"
    await pi.close()


async def test_a_callback_for_a_call_that_is_not_ours_changes_nothing(api, business_db, provider):
    pi, conv, scope = await workspace(api, business_db, "369100011")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    other = await hook(api, {"type": "call.session_ended", "call_cid": "pi_room:nosuchcall"})
    wrong_type = await hook(
        api, {"type": "call.session_ended", "call_cid": f"default:{room.call_id}"}
    )
    junk = await hook(api, {"type": 5})
    assert other.status_code == wrong_type.status_code == junk.status_code == 200
    assert (await the_room(business_db, mid)).state == "created"
    await pi.close()


async def test_deleting_a_meeting_removes_its_call_at_the_provider_or_refuses(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "369100012")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    call_id = provider.created[0][0]
    removed = []

    async def gone(call):
        removed.append(call)

    async def broken(call):
        raise RoomProviderError("ROOM_PROVIDER_UNREACHABLE", "down")

    provider.delete_call = broken
    refused = await api.delete(f"{BASE}/{mid}")
    assert (
        refused.status_code == 409 and refused.json()["error"]["code"] == "ROOM_DELETE_UNAVAILABLE"
    )
    assert (await the_room(business_db, mid)) is not None  # nothing was erased
    provider.delete_call = gone
    done = await api.delete(f"{BASE}/{mid}")
    assert done.status_code == 200, done.text
    assert removed == [call_id] and (await the_room(business_db, mid)) is None
    await pi.close()


async def test_a_gzipped_callback_is_accepted_when_signed_over_the_unzipped_body(
    api, business_db, provider
):
    import gzip

    pi, conv, scope = await workspace(api, business_db, "369100013")
    await switch(api)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    plain = json.dumps(event(room, "call.session_ended")).encode()
    sig = hmac.new(SECRET.encode(), plain, hashlib.sha256).hexdigest()
    headers = {"x-signature": sig, "content-encoding": "gzip", "content-type": "application/json"}
    ok = await api.post(HOOK, content=gzip.compress(plain), headers=headers)
    assert ok.status_code == 200
    assert (await the_room(business_db, mid)).state == "ended"
    bad = await api.post(
        HOOK, content=gzip.compress(plain), headers={**headers, "x-signature": "0" * 64}
    )
    assert bad.status_code == 401
    await pi.close()
