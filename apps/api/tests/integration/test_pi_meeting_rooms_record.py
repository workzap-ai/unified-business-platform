"""A room can be recorded (video and audio) for the team when the host ticks it: guests are told
first, the file is copied into the workspace's storage before the call is removed at the video
service, and a recording that cannot be kept is given up without harming the transcript."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_rooms import JOIN, open_room, the_room
from test_pi_meeting_rooms import Provider as BaseProvider
from test_pi_meeting_rooms_limits import switch, worker
from test_pi_meeting_routes import BASE

from app.modules.pi_meetings import media, native_stt, room_jobs, room_recording, room_routes
from app.modules.pi_meetings.models import PiMeeting, PiMeetingMedia
from app.modules.pi_meetings.room_provider import RoomProviderError, VideoRecording

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


class Provider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.videos = []
        self.video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"v" * 5000
        self.video_fail = None

    async def video_recordings(self, call_id):
        if self.video_fail:
            raise self.video_fail
        return list(self.videos)

    async def download_video(self, url):
        return self.video_bytes


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(room_routes, "provider_for", lambda request: p)
    monkeypatch.setattr(room_routes, "webhook_secret", lambda request: "s")
    monkeypatch.setattr(room_routes, "api_key", lambda request: "pk_test")
    return p


@pytest.fixture
def bucket(monkeypatch):
    """A storage bucket is connected; what would be put there is kept in a dictionary."""
    stored = {}

    async def has_bucket(session, scope):
        return True

    async def put(session, scope, request, key, data, mime):
        stored[key] = (len(data), mime)

    monkeypatch.setattr(media, "has_bucket", has_bucket)
    monkeypatch.setattr(media, "_put", put)
    return stored


async def ended_recorded_room(api, db, phone, provider, monkeypatch, bucket):
    pi, conv, scope = await workspace(api, db, phone)
    await switch(api, meeting_room_record=True)
    opened = await open_room(api, record_video=True)
    assert opened.status_code == 201, opened.text
    mid = opened.json()["meeting"]["id"]
    room = await the_room(db, mid)
    room.state, room.ended_at = "ended", NOW - timedelta(minutes=3)
    room.transcript_state = "done"
    await db.commit()
    meeting = await db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    return pi, scope, meeting, room


async def test_the_host_ticks_it_and_guests_are_told_before_they_agree(
    api, business_db, provider, bucket
):
    pi, conv, scope = await workspace(api, business_db, "369950001")
    await switch(api, meeting_room_record=True)
    plain = await open_room(api)
    plain_mid = plain.json()["meeting"]["id"]
    assert plain.json()["room"]["record"] is False and plain.json()["room"]["recording"] == "none"

    opened = await open_room(api, record_video=True)
    assert opened.status_code == 201
    mid = opened.json()["meeting"]["id"]
    assert opened.json()["room"]["record"] is True
    assert opened.json()["room"]["recording"] == "pending"
    assert provider.record is True  # the call records by itself when its session starts
    room = await the_room(business_db, mid)
    meeting = await business_db.scalar(select(PiMeeting).where(PiMeeting.id == room.meeting_id))
    assert meeting.media_consent_at is not None and "video and audio" in meeting.consent_note

    for meeting_id, expected in ((mid, True), (plain_mid, False)):
        invite = (await api.post(f"{BASE}/{meeting_id}/invite", json={})).json()["token"]
        info = (await api.get(f"{JOIN}/{invite}")).json()
        assert info["recording"] is expected  # said on the page before anyone agrees to join
    await pi.close()


async def test_it_needs_the_flag_and_a_bucket_and_a_failed_start_opens_nothing(
    api, business_db, provider, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "369950002")
    await switch(api)
    off = await open_room(api, record_video=True)
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_ROOM_RECORD_OFF"

    await switch(api, meeting_room_record=True)

    async def no_bucket(session, scope):
        return False

    monkeypatch.setattr(media, "has_bucket", no_bucket)
    nowhere = await open_room(api, record_video=True)
    assert nowhere.status_code == 409
    assert nowhere.json()["error"]["code"] == "MEETING_ROOM_RECORD_NEEDS_BUCKET"
    assert provider.created == []  # nothing was opened at the video service

    async def has_bucket(session, scope):
        return True

    monkeypatch.setattr(media, "has_bucket", has_bucket)

    provider.fail = RoomProviderError("ROOM_PROVIDER_REFUSED", "refused", 502)
    failed = await open_room(api, record_video=True)
    assert failed.status_code == 502  # the host is told; a room that cannot be made is not opened
    assert provider.recording_started == [] if hasattr(provider, "recording_started") else True
    await pi.close()


async def test_the_recording_is_copied_into_storage_and_only_then_the_call_is_removed(
    api, business_db, provider, monkeypatch, bucket
):
    pi, scope, meeting, room = await ended_recorded_room(
        api, business_db, "369950003", provider, monkeypatch, bucket
    )
    provider.videos = [
        VideoRecording("https://cdn/short.mp4", NOW, NOW + timedelta(seconds=30)),
        VideoRecording("https://cdn/call.mp4", NOW, NOW + timedelta(minutes=12)),
    ]
    out = await room_recording.copy(business_db, scope, meeting, room, provider, None, now=NOW)
    assert out == "saved" and room.recording_state == "saved"
    assert list(bucket.values()) == [(len(provider.video_bytes), "video/mp4")]
    row = await business_db.scalar(
        select(PiMeetingMedia).where(PiMeetingMedia.meeting_id == meeting.id)
    )
    assert row.kind == "video" and row.duration_ms == 12 * 60 * 1000  # the whole call, not a clip
    assert meeting.recording_key and meeting.retention_until is not None  # the player will show it
    assert provider.deleted == [room.call_id]  # copied first, removed after
    await pi.close()


async def test_a_call_whose_transcript_is_still_pending_is_kept_after_the_copy(
    api, business_db, provider, monkeypatch, bucket
):
    pi, scope, meeting, room = await ended_recorded_room(
        api, business_db, "369950004", provider, monkeypatch, bucket
    )
    room.transcript_state = "pending"
    provider.videos = [VideoRecording("https://cdn/call.mp4", NOW, NOW + timedelta(minutes=5))]
    assert await room_recording.copy(business_db, scope, meeting, room, provider, None) == "saved"
    assert getattr(provider, "deleted", []) == []  # the transcript still needs the call
    # and while the recording is still to come, the transcript step never removes the call
    room.recording_state = "pending"
    await native_stt.forget_call(provider, room)
    assert getattr(provider, "deleted", []) == []
    await pi.close()


async def test_a_recording_that_is_late_is_waited_for_and_one_that_never_comes_is_given_up(
    api, business_db, provider, monkeypatch, bucket
):
    pi, scope, meeting, room = await ended_recorded_room(
        api, business_db, "369950005", provider, monkeypatch, bucket
    )
    now = room.ended_at + timedelta(minutes=2)
    assert (
        await room_recording.copy(business_db, scope, meeting, room, provider, None, now=now)
        == "waiting"
    )
    assert room.recording_state == "pending" and getattr(provider, "deleted", []) == []
    provider.video_fail = RoomProviderError("ROOM_PROVIDER_BUSY", "busy", 429)
    assert (
        await room_recording.copy(business_db, scope, meeting, room, provider, None, now=now)
        == "waiting"
    )
    late = room.ended_at + timedelta(seconds=room_recording.GIVE_UP_S + 5)
    provider.video_fail = None
    assert (
        await room_recording.copy(business_db, scope, meeting, room, provider, None, now=late)
        == "failed"
    )
    assert room.recording_state == "failed" and provider.deleted == [room.call_id]
    await pi.close()


async def test_a_file_the_storage_refuses_is_given_up_without_harming_the_meeting(
    api, business_db, provider, monkeypatch, bucket
):
    pi, scope, meeting, room = await ended_recorded_room(
        api, business_db, "369950006", provider, monkeypatch, bucket
    )

    async def refuse(session, scope, request, key, data, mime):
        raise media.StorageFailed("OBJECT_TOO_LARGE")

    monkeypatch.setattr(media, "_put", refuse)
    provider.videos = [VideoRecording("https://cdn/call.mp4", NOW, NOW + timedelta(minutes=5))]
    out = await room_recording.copy(business_db, scope, meeting, room, provider, None, now=NOW)
    assert out == "failed" and room.recording_state == "failed"
    assert meeting.recording_key is None  # nothing is claimed that is not there
    assert provider.deleted == [room.call_id]
    await pi.close()


async def test_the_worker_copies_only_old_enough_pending_rooms(
    api, business_db, provider, monkeypatch, bucket
):
    pi, scope, meeting, room = await ended_recorded_room(
        api, business_db, "369950007", provider, monkeypatch, bucket
    )
    mid, room_id = str(room.meeting_id), room.id
    provider.videos = [VideoRecording("https://cdn/call.mp4", NOW, NOW + timedelta(minutes=5))]
    ctx = worker(business_db, monkeypatch, provider)
    ctx["settings"], ctx["http"] = object(), object()
    room.ended_at = datetime.now(UTC) - timedelta(seconds=5)  # ended a moment ago: not yet
    await business_db.commit()
    assert await room_jobs.copy_recordings(ctx) == 0
    room = await the_room(business_db, mid)
    room.ended_at = datetime.now(UTC) - timedelta(minutes=3)
    await business_db.commit()
    assert await room_jobs.copy_recordings(ctx) == 1
    business_db.expire_all()
    assert (await business_db.get(type(room), room_id)).recording_state == "saved"
    assert await room_jobs.copy_recordings(ctx) == 0  # done: nothing left to copy
    await pi.close()
