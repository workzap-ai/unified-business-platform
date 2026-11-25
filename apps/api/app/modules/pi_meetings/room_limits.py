"""Limits for video rooms: how long, how many people, how much a month, and the off switch.

docs/pi-saas/pi-meeting-rooms-limits.md. A room costs money for every minute and every person, and
nothing else ends a call that people forget to close, so these are enforced in code:

- a call is ended after MAX_CALL_MINUTES (a worker sweep; the staff page does not have to be open);
- at most MAX_PEOPLE different people get a token for one room;
- a workspace has a monthly allowance of call minutes (`brain.meeting_room_month_minutes`, 0 means
  the built-in DEFAULT_MONTH_MINUTES); a new room is refused once it is used up;
- `brain.meeting_room_kill` stops everything for a workspace: no new room, no new token, and the
  sweep ends any live call.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.modules.pi.configuration import settings_row
from app.modules.pi_meetings.models import PiMeetingParticipant, PiMeetingRoom
from app.shared.scope import WorkspaceScope

MAX_CALL_MINUTES = 90
MAX_PEOPLE = 8
DEFAULT_MONTH_MINUTES = 600


async def _brain(session: Any, scope: WorkspaceScope) -> dict[str, Any]:
    return (await settings_row(session, scope)).response_rules.get("brain") or {}


async def killed(session: Any, scope: WorkspaceScope) -> bool:
    return (await _brain(session, scope)).get("meeting_room_kill") is True


async def month_allowance(session: Any, scope: WorkspaceScope) -> int:
    value = (await _brain(session, scope)).get("meeting_room_month_minutes", 0)
    return value if type(value) is int and value > 0 else DEFAULT_MONTH_MINUTES


async def month_minutes_used(
    session: Any, scope: WorkspaceScope, now: datetime | None = None
) -> int:
    """Minutes of call time this calendar month (UTC), counting a live call up to now."""
    now = now or datetime.now(UTC)
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    begun = func.coalesce(PiMeetingRoom.started_at, PiMeetingRoom.created_at)
    seconds = await session.scalar(
        select(
            func.coalesce(
                func.sum(func.extract("epoch", func.coalesce(PiMeetingRoom.ended_at, now) - begun)),
                0,
            )
        ).where(
            PiMeetingRoom.tenant_id == scope.tenant_id,
            PiMeetingRoom.environment_id == scope.environment_id,
            PiMeetingRoom.state.in_(("live", "ended")),
            begun >= first,
        )
    )
    return int(max(float(seconds or 0), 0) // 60)


async def people_in(session: Any, scope: WorkspaceScope, meeting_id: UUID) -> int:
    """Different people who have been given a token for this room (a removed person still counts:
    removing someone must not free a seat for a new token)."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PiMeetingParticipant)
            .where(
                PiMeetingParticipant.tenant_id == scope.tenant_id,
                PiMeetingParticipant.environment_id == scope.environment_id,
                PiMeetingParticipant.meeting_id == meeting_id,
                PiMeetingParticipant.stream_user_id.is_not(None),
            )
        )
        or 0
    )


async def live_rooms(session: Any, limit: int = 200) -> list[PiMeetingRoom]:
    return list(
        (
            await session.scalars(
                select(PiMeetingRoom)
                .where(PiMeetingRoom.state.in_(("created", "live")))
                .limit(limit)
            )
        ).all()
    )


def overdue(room: PiMeetingRoom, now: datetime) -> bool:
    """A live call past its time limit (a room nobody entered counts from when it was made)."""
    begun = room.started_at or room.created_at
    return begun is not None and now - begun > timedelta(minutes=MAX_CALL_MINUTES)
