"""Worker jobs for video rooms: write the transcript of a finished call from its audio.

A sweep (every 30 seconds) finds rooms that have ended and are still waiting for their transcript
(`audio` rooms only), and hands each to `finish_meeting_room`, one job per room, which makes one
attempt (`native_stt.finalize`) and says "try later" simply by leaving the room pending. Everything
durable is in the database, so a lost job is picked up by the next sweep.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.ai.manager import build_llm_manager
from app.modules.pi_meetings import native_stt
from app.modules.pi_meetings.guest_routes import system_scope
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom
from app.modules.pi_meetings.room_provider import build_provider
from app.modules.pi_meetings.room_routes import room_enabled


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


async def sweep_meeting_rooms(ctx: dict[str, Any]) -> None:
    """Recover rooms waiting for their transcript (also after a lost job)."""
    async with ctx["sessions"]() as session:
        ids = await native_stt.pending_rooms(session)
    for room_id in ids:
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job(
                "finish_meeting_room", str(room_id), _job_id=f"room-finish:{room_id}"
            )
        else:
            await finish_meeting_room(ctx, str(room_id))
