"""Keeping the recording of a room (video and audio of the whole call) for staff.

Only a room whose host ticked "record the call" when opening it is recorded, and only after everyone
in it was told: the guest's join page says the call is recorded and asks for an agreement, and the
meeting carries the host's media consent. When the call has ended the worker asks the video service
for the recording, copies it into the workspace's own storage bucket as the meeting's video part,
and only then removes the call at the service (the copy must come first: removing the call removes
its recording). The meeting page then shows the usual recording player, behind the same permission
and with the same retention date as any recording of a meeting.

Copying is bounded: a recording over `room_provider.MAX_VIDEO_BYTES`, one the storage refuses (a
workspace with no bucket, or a bucket limit smaller than the file) or one that never appears is
given up after a few tries, the room says `failed` and the meeting keeps its transcript. Audit
entries carry ids and sizes, never anything that was said.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from app.modules.pi.configuration import settings_row
from app.modules.pi_meetings import media, native_stt
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom
from app.modules.pi_meetings.room_provider import RoomProvider, RoomProviderError

logger = logging.getLogger(__name__)

WAIT_S = 45  # the service writes the file a little after the call ends
GIVE_UP_S = 25 * 60  # no recording after this long: given up
MAX_TRIES = 12
MIME = "video/mp4"


def pending(room: PiMeetingRoom) -> bool:
    """True while the call must be kept at the service because its recording is still to come."""
    return bool(room.record_video and room.recording_state == "pending")


async def copy(
    session: Any,
    scope: Any,
    meeting: PiMeeting,
    room: PiMeetingRoom,
    provider: RoomProvider,
    request: Any,
    *,
    now: datetime | None = None,
) -> str:
    """One attempt. Returns 'saved', 'waiting' (try again later) or 'failed' (given up)."""
    now = now or datetime.now(UTC)
    room.recording_tries += 1
    age = (now - (room.ended_at or now)).total_seconds()
    expired = age >= GIVE_UP_S or room.recording_tries >= MAX_TRIES
    try:
        found = await provider.video_recordings(room.call_id)
    except RoomProviderError:
        found = []
    if not found:
        return await _give_up(provider, room) if expired else "waiting"
    best = max(
        found,
        key=lambda r: (r.end - r.start).total_seconds() if r.start and r.end else 0.0,
    )
    try:
        data = await provider.download_video(best.url)
    except RoomProviderError:
        data = None
    if data is None:
        # missing, still being written, or too big: tried again until the time is up
        return await _give_up(provider, room) if expired else "waiting"
    duration_ms = (
        int((best.end - best.start).total_seconds() * 1000) if best.start and best.end else 0
    )
    rules = (await settings_row(session, scope)).response_rules
    try:
        await media.save_part(
            session,
            scope,
            request,
            meeting,
            kind="video",
            ordinal=0,
            data=data,
            mime=MIME,
            offset_ms=0,
            duration_ms=max(0, duration_ms),
            days=media.retention_days(rules),
        )
    except (
        media.StorageFailed,
        media.NeedsBucket,
        media.NoMediaConsent,
        media.MeetingFull,
    ) as error:
        # the file is fine but we cannot keep it (no bucket, bucket limit, no consent): no point
        # in trying again with the same file
        logger.warning("room_recording_not_saved reason=%s", type(error).__name__)
        return await _give_up(provider, room)
    room.recording_state = "saved"
    await _forget(provider, room)
    return "saved"


async def _give_up(provider: RoomProvider, room: PiMeetingRoom) -> str:
    room.recording_state = "failed"
    await _forget(provider, room)
    return "failed"


async def _forget(provider: RoomProvider, room: PiMeetingRoom) -> None:
    """The recording is ours now (or given up): the call may go, once the transcript is done too."""
    if room.transcript_state != "pending":
        await native_stt.forget_call(provider, room)


async def waiting_rooms(session: Any, limit: int = 5) -> list[Any]:
    """Ended rooms whose recording has still to be copied, oldest first."""
    from sqlalchemy import select

    rows = await session.scalars(
        select(PiMeetingRoom.id)
        .where(
            PiMeetingRoom.record_video.is_(True),
            PiMeetingRoom.recording_state == "pending",
            PiMeetingRoom.state == "ended",
        )
        .order_by(PiMeetingRoom.ended_at)
        .limit(limit)
    )
    return list(rows.all())
