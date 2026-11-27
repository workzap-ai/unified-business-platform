"""A video room that records each voice briefly: the transcript is written from the audio by our own
speech-to-text (Urdu and others), placed under who the room says spoke, with the provider's captions
as the fallback, and the call is removed at the provider afterwards. All of it only when the
workspace has switched on `meeting_room_audio`."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import (
    CDN,
    JOIN,
    ROOM_TOKEN,
    event,
    hook,
    lines,
    open_room,
    speech,
    the_room,
)
from test_pi_meeting_rooms import (
    Provider as BaseProvider,
)
from test_pi_meeting_routes import BASE

from app.ai.errors import GatewayUnavailable
from app.ai.types import Word
from app.modules.pi_meetings import native_stt, roman_urdu, room_routes
from app.modules.pi_meetings.guest_routes import system_scope
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom
from app.modules.pi_meetings.room_provider import RoomRecording

pytestmark = pytest.mark.integration
BEGIN = datetime(2026, 11, 24, 14, 0, 0, tzinfo=UTC)


class Provider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.files = []  # RoomRecording
        self.bytes = {}  # url -> audio bytes (None = too large)
        self.deleted = []
        self.audio = None

    async def recordings(self, call_id):
        return list(self.files)

    async def download(self, url):
        return self.bytes.get(url)

    async def delete_call(self, call_id):
        self.deleted.append(call_id)


class Manager:
    """Stands in for the speech-to-text service: what the audio 'says' is decided by its bytes."""

    def __init__(self):
        self.said = {}  # audio bytes -> [Word]
        self.broken = set()
        self.calls = []

    async def transcribe(self, scope, audio, mime, **kw):
        self.calls.append({"mime": mime, **kw})
        if audio in self.broken:
            raise GatewayUnavailable()
        return SimpleNamespace(words=self.said[audio], text="x")


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(
        room_routes, "webhook_secret", lambda request: "integration-test-stream-secret"
    )
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


async def switch(api, audio=True, guests=False):
    brain = {
        "meeting_intel": True,
        "meeting_room": True,
        "meeting_room_audio": audio,
        "meeting_guests": guests,
    }
    r = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert r.status_code == 200, r.text


def said(*pairs):
    """Words with times: ('text', start_s)."""
    return [Word(t, s, s + 0.4) for t, s in pairs]


async def ready(api, business_db, phone, **kw):
    pi, conv, scope = await workspace(api, business_db, phone)
    await switch(api, **kw)
    mid = (await open_room(api)).json()["meeting"]["id"]
    room = await the_room(business_db, mid)
    return pi, mid, room


async def end_it(api, business_db, mid, minutes_ago=2):
    await api.post(f"{BASE}/{mid}/room/end")
    room = await the_room(business_db, mid)
    room.ended_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    await business_db.commit()
    return await the_room(business_db, mid)


async def run(business_db, room, provider, manager):
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    scope = system_scope(room.tenant_id, room.environment_id)
    out = await native_stt.finalize(business_db, scope, meeting, room, provider, manager)
    await business_db.commit()
    business_db.expire_all()
    await business_db.refresh(meeting)
    await business_db.refresh(room)
    return out, meeting


async def test_a_room_records_voices_only_when_the_workspace_switched_it_on_and_says_so(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200001", audio=False)
    assert room.audio is False and provider.audio is False
    assert (await api.get(f"{BASE}/rooms/options")).json() == {"audio": False}
    await switch(api, audio=True, guests=True)
    assert (await api.get(f"{BASE}/rooms/options")).json() == {"audio": True}
    made = await open_room(api)
    mid2 = made.json()["meeting"]["id"]
    assert made.json()["room"]["audio"] is True and provider.audio is True
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == mid2))
    assert "recorded briefly" in meeting.consent_note
    token = (await api.post(f"{BASE}/{mid2}/invite", json={})).json()["token"]
    assert (await api.get(f"{JOIN}/{token}")).json()["audio"] is True  # said before they agree
    await pi.close()


async def test_the_providers_captions_wait_while_the_audio_is_being_read(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200002")
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    await api.post(f"{BASE}/{mid}/room/end")
    provider.rows = [speech(staff, "Hello from the captions.", 1000, 3000)]
    await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    room = await the_room(business_db, mid)
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    await business_db.refresh(meeting)
    assert room.transcript_state == "pending" and meeting.status != "analysing"
    assert len(await lines(business_db, mid)) == 1  # kept as the fallback
    again = await api.get(f"{BASE}/{mid}/room")  # the page does not finish it by itself
    assert again.json()["room"]["transcript_state"] == "pending"
    await pi.close()


async def test_each_persons_audio_becomes_their_lines_in_the_order_they_were_said(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200003", guests=True)
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    token = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    guest_token = (
        await api.post(f"{JOIN}/{token}", json={"name": "Ayesha", "consent": True})
    ).json()["guest_token"]
    guest = (await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest_token})).json()["user_id"]
    provider.files = [
        RoomRecording(guest, "https://cdn/guest", BEGIN + timedelta(seconds=1)),
        RoomRecording(staff, "https://cdn/staff", BEGIN),
    ]
    provider.bytes = {"https://cdn/guest": b"G", "https://cdn/staff": b"S"}
    manager = Manager()
    manager.said = {
        b"S": said(
            ("آپ", 0.5),
            ("کا", 0.9),
            ("اسٹاک", 1.3),
            ("کب", 1.7),
            ("ختم", 2.1),
            ("ہوتا", 2.5),
            ("ہے؟", 2.9),
        ),
        b"G": said(
            ("ہر", 5.0),
            ("مہینے۔", 5.4),
            ("Call", 9.0),
            ("me", 9.4),
            ("on", 9.8),
            ("0300", 10.2),
            ("1234567.", 10.6),
        ),
    }
    room = await end_it(api, business_db, mid)
    out, meeting = await run(business_db, room, provider, manager)
    assert out == "done"
    status, duration, call_id = meeting.status, meeting.duration_ms, room.call_id
    meeting_id = meeting.id
    got = await lines(business_db, mid)
    # the transcript is Roman Urdu: no Urdu or Hindi letters are stored (the fake model here has
    # no rewrite door, so the plain letter-by-letter rewrite is what is kept)
    assert [(label, text) for _, label, text in got][:2] == [
        ("Staff", "aap ka asatak kab khatam hota he?"),
        ("Ayesha", "har mahine."),
    ]
    assert not any(roman_urdu.needs_roman(text) for _, _, text in got)
    assert [o for o, _, _ in got] == [0, 1, 2]
    assert "1234567" not in got[2][2]  # a phone number never reaches the transcript
    # the guest's file started a second later: their first words are at 1 s + 5 s
    seg = await business_db.scalar(
        select(native_stt.PiMeetingSegment).where(
            native_stt.PiMeetingSegment.meeting_id == meeting_id,
            native_stt.PiMeetingSegment.ordinal == 1,
        )
    )
    assert seg.start_ms == 6000
    assert status == "analysing" and duration >= 11000
    assert provider.deleted == [call_id]  # the call and its recordings are gone at the provider
    assert manager.calls[0]["mime"] == "audio/webm" and manager.calls[0]["timestamps"] is True
    assert (await the_room(business_db, mid)).transcript_state == "done"
    await pi.close()


async def test_a_word_the_speech_service_times_backwards_cannot_break_the_transcript(
    api, business_db, provider
):
    """Found live: Whisper can time a word with an end before its start, so a line ended before it
    began and the database refused it (ck_pi_meeting_segments_span): no transcript was written."""
    pi, mid, room = await ready(api, business_db, "369200013")
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    provider.files = [RoomRecording(staff, "https://cdn/staff", BEGIN)]
    provider.bytes = {"https://cdn/staff": b"S"}
    manager = Manager()
    manager.said = {
        b"S": [
            Word("اسٹاک", 0.0, 0.0),  # a zero-length word at the very start
            Word("ختم", 2.0, 1.5),  # ends before it starts
            Word("ہوتا۔", 3.0, 2.0),  # the line's last word ends before the line's first word
        ]
    }
    room = await end_it(api, business_db, mid)
    out, meeting = await run(business_db, room, provider, manager)
    assert out == "done"
    meeting_id = meeting.id
    business_db.expire_all()
    rows = (
        await business_db.scalars(
            select(native_stt.PiMeetingSegment).where(
                native_stt.PiMeetingSegment.meeting_id == meeting_id
            )
        )
    ).all()
    assert rows and all(0 <= r.start_ms <= r.end_ms for r in rows)
    await pi.close()


async def test_a_person_whose_audio_cannot_be_read_keeps_the_providers_lines(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200004", guests=True)
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    token = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    guest_token = (
        await api.post(f"{JOIN}/{token}", json={"name": "Ayesha", "consent": True})
    ).json()["guest_token"]
    guest = (await api.post(ROOM_TOKEN, headers={"X-Guest-Token": guest_token})).json()["user_id"]
    await api.post(f"{BASE}/{mid}/room/end")
    provider.rows = [
        speech(guest, "stock runs out each month", 4000, 6000),
        speech(staff, "garbled captions", 1000, 3000),
    ]
    await hook(api, event(room, "call.transcription_ready", call_transcription={"url": CDN}))
    provider.files = [
        RoomRecording(staff, "https://cdn/staff", BEGIN),
        RoomRecording(guest, "https://cdn/guest", BEGIN),
    ]
    provider.bytes = {"https://cdn/staff": b"S", "https://cdn/guest": b"G"}
    manager = Manager()
    manager.said = {b"S": said(("Tell", 0.5), ("me", 0.9), ("more.", 1.3))}
    manager.broken = {b"G"}
    room = await the_room(business_db, mid)
    room.ended_at = datetime.now(UTC) - timedelta(minutes=2)
    await business_db.commit()
    room = await the_room(business_db, mid)
    out, _ = await run(business_db, room, provider, manager)
    assert out == "done"
    got = [(label, text) for _, label, text in await lines(business_db, mid)]
    assert got == [("Staff", "Tell me more."), ("Ayesha", "stock runs out each month")]
    await pi.close()


async def test_it_waits_for_the_files_then_falls_back_to_the_providers_transcript(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200005")
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    provider.rows = [speech(staff, "We agreed on Monday.", 1000, 3000)]
    manager = Manager()
    room = await end_it(api, business_db, mid, minutes_ago=2)
    out, meeting = await run(business_db, room, provider, manager)
    assert out == "waiting" and meeting.status != "analysing"  # no files yet, still early
    assert provider.deleted == [] and manager.calls == []
    room = await the_room(business_db, mid)
    room.ended_at = datetime.now(UTC) - timedelta(minutes=20)
    await business_db.commit()
    room = await the_room(business_db, mid)
    out, meeting = await run(business_db, room, provider, manager)
    assert out == "fallback" and meeting.status == "analysing"
    assert provider.deleted == [room.call_id]  # what was promised: nothing is left at the provider
    assert [t for _, _, t in await lines(business_db, mid)] == ["We agreed on Monday."]
    await pi.close()


async def test_silence_and_oversized_files_are_not_a_transcript(api, business_db, provider):
    pi, mid, room = await ready(api, business_db, "369200006")
    staff = (await api.post(f"{BASE}/{mid}/room/token")).json()["user_id"]
    provider.files = [RoomRecording(staff, "https://cdn/big", BEGIN)]
    provider.bytes = {"https://cdn/big": None}  # too large for the speech service
    provider.rows = []
    room = await end_it(api, business_db, mid, minutes_ago=20)
    out, meeting = await run(business_db, room, provider, Manager())
    assert out == "fallback" and meeting.status == "failed"  # no one was heard at all
    await pi.close()


async def test_only_ended_rooms_that_record_and_wait_are_picked_up_by_the_sweep(
    api, business_db, provider
):
    pi, mid, room = await ready(api, business_db, "369200007")
    assert await native_stt.pending_rooms(business_db) == []  # still open
    await api.post(f"{BASE}/{mid}/room/end")
    assert await native_stt.pending_rooms(business_db) == []  # ended a moment ago
    room = await the_room(business_db, mid)
    room.ended_at = datetime.now(UTC) - timedelta(minutes=2)
    await business_db.commit()
    assert await native_stt.pending_rooms(business_db) == [room.id]
    room = await the_room(business_db, mid)
    room.audio = False  # a room that does not record is not for the worker
    await business_db.commit()
    assert await native_stt.pending_rooms(business_db) == []
    await pi.close()


async def test_the_room_model_is_what_the_sweep_reads(api, business_db, provider):
    pi, mid, room = await ready(api, business_db, "369200008")
    assert isinstance(room, PiMeetingRoom) and room.stt_tries == 0
    await pi.close()
