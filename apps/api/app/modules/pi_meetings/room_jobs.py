"""Worker jobs for video rooms: write the transcript of a finished call from its audio.

A sweep (every 30 seconds) finds rooms that have ended and are still waiting for their transcript
(`audio` rooms only), and hands each to `finish_meeting_room`, one job per room, which makes one
attempt (`native_stt.finalize`) and says "try later" simply by leaving the room pending. Everything
durable is in the database, so a lost job is picked up by the next sweep.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.ai.manager import build_llm_manager
from app.modules.audit.service import record
from app.modules.pi_meetings import native_stt
from app.modules.pi_meetings import room_limits as limits
from app.modules.pi_meetings.guest_routes import system_scope
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom
from app.modules.pi_meetings.room_provider import RoomProviderError, build_provider
from app.modules.pi_meetings.room_routes import room_enabled

logger = logging.getLogger(__name__)


async def finish_meeting_room(ctx: dict[str, Any], room_id: str) -> None:
    provider = build_provider(ctx["settings"], ctx["http"])
    if provider is None:
        return
    async with ctx["sessions"]() as session:
        room = await session.scalar(
            select(PiMeetingRoom).where(PiMeetingRoom.id == UUID(room_id)).with_for_update()
        )
        if room is None or room.transcript_state != "pending" or not room.audio:
            return
        scope = system_scope(room.tenant_id, room.environment_id)
        if not await room_enabled(session, scope):
            return
        meeting = await session.scalar(
            select(PiMeeting).where(
                PiMeeting.tenant_id == room.tenant_id,
                PiMeeting.environment_id == room.environment_id,
                PiMeeting.id == room.meeting_id,
            )
        )
        if meeting is None:
            return
        manager = build_llm_manager(ctx["settings"], ctx["http"], ctx["sessions"])
        await native_stt.finalize(session, scope, meeting, room, provider, manager)
        await session.commit()


async def close_rooms(ctx: dict[str, Any]) -> int:
    """End calls that ran past the time limit, and every call of a workspace that paused its rooms.
    The transcript is then written like for any ended call. Returns how many were ended."""
    provider = build_provider(ctx["settings"], ctx["http"])
    if provider is None:
        return 0
    ended = 0
    now = datetime.now(UTC)
    async with ctx["sessions"]() as session:
        for room in await limits.live_rooms(session):
            scope = system_scope(room.tenant_id, room.environment_id)
            why = (
                "paused"
                if await limits.killed(session, scope)
                else "time_limit"
                if limits.overdue(room, now)
                else ""
            )
            if not why:
                continue
            try:
                await provider.end_call(room.call_id)
            except RoomProviderError:
                logger.warning("room_close_failed", extra={"room": str(room.id)})
                continue
            room.state = "ended"
            room.ended_at = room.ended_at or now
            room.transcript_state = "pending"
            await record(
                session,
                "pi.meeting_room_closed",
                scope=scope,
                entity_type="pi_meeting",
                entity_id=room.meeting_id,
                details={"why": why},
            )
            ended += 1
        await session.commit()
    return ended


async def sweep_meeting_rooms(ctx: dict[str, Any]) -> None:
    """Close rooms past their limits, then recover rooms waiting for their transcript (also after a
    lost job)."""
    await close_rooms(ctx)
    async with ctx["sessions"]() as session:
        ids = await native_stt.pending_rooms(session)
    for room_id in ids:
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job(
                "finish_meeting_room", str(room_id), _job_id=f"room-finish:{room_id}"
            )
        else:
            await finish_meeting_room(ctx, str(room_id))
