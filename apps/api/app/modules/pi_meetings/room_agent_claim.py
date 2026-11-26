"""Which agent process holds a video room, and what the host has told pi to do there.

One agent per call (Phase 0 showed that pressing "join" four times put four pi's in a room). An
agent claims a room by writing its id and the time on the room's row under a row lock; the claim is
renewed every few seconds (`beat`) and is lost, to another agent, when it has not been renewed for
`LEASE_S`. Everything the agent needs to decide (mode, mute, intake, whether the workspace still
allows it) is read from the row on every beat, so a mute set in the app reaches the agent within one
beat and a stopped agent can never keep a room.

The agent is a platform process: it reads rooms across workspaces, then acts for one workspace at a
time through that room's own scope.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from app.modules.pi.configuration import settings_row
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom
from app.shared.scope import WorkspaceScope

LEASE_S = 30  # a claim not renewed for this long is free
BEAT_S = 5  # the agent renews at this interval
LIVE = ("created", "live")


@dataclass(frozen=True)
class Orders:
    """What the agent should do right now in one room."""

    room_id: UUID
    meeting_id: UUID
    started_at: datetime | None  # when the call began (or the room was made): pi's line times
    call_id: str
    scope: WorkspaceScope
    speak: bool  # pi may speak (mode 'speak' and the workspace allows it)
    muted: bool
    intake: bool
    language: str
    stay: bool  # False: the room has ended, been paused or switched off: leave
    # what pi already did in this call (kept across an agent restart)
    spoken: int = 0
    disclosed: bool = False
    halted: bool = False
    last_spoke_at: datetime | None = None


def scope_of(room: PiMeetingRoom) -> WorkspaceScope:
    return WorkspaceScope.system(room.tenant_id, room.environment_id, frozenset(), "pi_room_agent")


async def workspace_allows(session: Any, scope: WorkspaceScope) -> bool:
    """The workspace has rooms and pi speech on, and the pause switch off."""
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    return (
        brain.get("meeting_intel") is True
        and brain.get("meeting_room") is True
        and brain.get("meeting_room_speak") is True
        and brain.get("meeting_room_kill") is not True
    )


async def claim(
    session: Any, agent_id: str, now: datetime, *, limit: int = 3
) -> list[PiMeetingRoom]:
    """Take up to `limit` live rooms where pi is asked to speak and nobody holds the lease. The
    caller commits. Rooms of a workspace that no longer allows speech are left alone."""
    rows = (
        await session.scalars(
            select(PiMeetingRoom)
            .where(
                PiMeetingRoom.state.in_(LIVE),
                PiMeetingRoom.pi_mode == "speak",
                or_(
                    PiMeetingRoom.agent_id.is_(None),
                    PiMeetingRoom.agent_id == agent_id,
                    PiMeetingRoom.agent_beat_at.is_(None),
                    PiMeetingRoom.agent_beat_at < now - timedelta(seconds=LEASE_S),
                ),
            )
            .order_by(PiMeetingRoom.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    taken: list[PiMeetingRoom] = []
    for room in rows:
        if not await workspace_allows(session, scope_of(room)):
            continue
        room.agent_id = agent_id
        room.agent_beat_at = now
        taken.append(room)
    return taken


async def beat(session: Any, room_id: UUID, agent_id: str, now: datetime) -> Orders | None:
    """Renew the claim and read the orders. None when the claim is no longer this agent's (another
    one took it, or the row is gone): the agent must leave the room at once."""
    room = await session.scalar(
        select(PiMeetingRoom).where(PiMeetingRoom.id == room_id).with_for_update()
    )
    if room is None or room.agent_id != agent_id:
        return None
    room.agent_beat_at = now
    scope = scope_of(room)
    allowed = await workspace_allows(session, scope)
    language = (
        await session.scalar(
            select(PiMeeting.language).where(
                PiMeeting.tenant_id == room.tenant_id,
                PiMeeting.environment_id == room.environment_id,
                PiMeeting.id == room.meeting_id,
            )
        )
        or ""
    )
    return Orders(
        room_id=room.id,
        meeting_id=room.meeting_id,
        started_at=room.started_at or room.created_at,
        call_id=room.call_id,
        scope=scope,
        speak=allowed and room.pi_mode == "speak",
        muted=room.pi_muted,
        intake=room.pi_intake,
        language=language,
        stay=room.state in LIVE and allowed and room.pi_mode == "speak",
        spoken=room.pi_spoken,
        disclosed=room.pi_disclosed,
        halted=room.pi_halted,
        last_spoke_at=room.pi_last_spoke_at,
    )


async def release(session: Any, room_id: UUID, agent_id: str) -> None:
    """The agent has left: free the room so a restarted agent can take it back at once."""
    room = await session.scalar(
        select(PiMeetingRoom).where(PiMeetingRoom.id == room_id).with_for_update()
    )
    if room is not None and room.agent_id == agent_id:
        room.agent_id = None
        room.agent_beat_at = None


async def save_state(
    session: Any,
    room_id: UUID,
    agent_id: str,
    *,
    spoken: int,
    disclosed: bool,
    halted: bool,
    last_spoke_at: datetime | None,
) -> bool:
    """Keep what pi has done so far, only while this agent still holds the room. The caller
    commits. False when the room is no longer this agent's."""
    room = await session.scalar(
        select(PiMeetingRoom).where(PiMeetingRoom.id == room_id).with_for_update()
    )
    if room is None or room.agent_id != agent_id:
        return False
    room.pi_spoken = max(room.pi_spoken, spoken)
    room.pi_disclosed = room.pi_disclosed or disclosed
    room.pi_halted = room.pi_halted or halted
    if last_spoke_at is not None:
        room.pi_last_spoke_at = last_spoke_at
    return True
