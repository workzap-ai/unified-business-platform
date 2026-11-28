"""Staff are told when a video room's background process dies (each one watches the other).

Two processes run a room: the room agent (it is in the call, listens and speaks) and the worker
(it ends calls, writes transcripts, drafts the summary). Neither can report its own death, so each
looks at the other's footprints in the database:

* `agent_missing` runs in the WORKER: a live room where pi should speak, but no agent has renewed
  its claim for `AGENT_DEAD_S` (or none ever claimed it), means pi has left the call or never came.
* `transcripts_stuck` runs in the AGENT and in the worker: a call ended more than `STUCK_S` ago
  whose transcript is still pending (the worker gives up after six minutes and uses the provider's
  captions), means the worker is down or its jobs keep failing.

The alert is an in-app notification to everyone who may record meetings in that workspace, once
per room (the dedupe key), with a link to the room. It carries the meeting's title and a plain
sentence, never anything said in the call. A watchdog must not break what it watches: every
function here swallows its own errors and returns how many alerts it raised.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.modules.notifications.service import notify
from app.modules.pi_meetings.guest_routes import system_scope
from app.modules.pi_meetings.models import PiMeeting, PiMeetingRoom

logger = logging.getLogger(__name__)

AGENT_DEAD_S = 90  # three missed claims (the claim lasts 30 s, the agent renews every 5 s)
STUCK_S = 15 * 60  # a transcript normally takes about a minute; the worker gives up after six
PERMISSION = "pi.meetings.record"
KIND = "pi_room_alert"


async def _title(session: Any, room: PiMeetingRoom) -> str:
    title = await session.scalar(
        select(PiMeeting.title).where(
            PiMeeting.id == room.meeting_id,
            PiMeeting.tenant_id == room.tenant_id,
            PiMeeting.environment_id == room.environment_id,
        )
    )
    return str(title or "the video call")[:80]


async def agent_missing(session: Any, now: datetime | None = None) -> int:
    """Alert for each live room where pi should be speaking but no agent is holding it."""
    now = now or datetime.now(UTC)
    raised = 0
    try:
        rooms = (
            await session.scalars(
                select(PiMeetingRoom).where(
                    PiMeetingRoom.state == "live", PiMeetingRoom.pi_mode == "speak"
                )
            )
        ).all()
        for room in rooms:
            seen = room.agent_beat_at or room.started_at or room.created_at
            if seen is None or now - seen < timedelta(seconds=AGENT_DEAD_S):
                continue
            scope = system_scope(room.tenant_id, room.environment_id)
            await notify(
                session,
                scope,
                KIND,
                "pi is not in the call",
                f"pi stopped answering in '{await _title(session, room)}'. People can keep "
                "talking and the call is still being transcribed, but pi will not speak or "
                "listen until its service is back.",
                link=f"/pi/meetings/{room.meeting_id}/room",
                permission=PERMISSION,
                severity="critical",
                dedupe_key=f"room-agent-missing:{room.id}",
            )
            raised += 1
        await session.commit()
    except Exception:  # noqa: BLE001 - a watchdog never breaks what it watches
        logger.warning("room_watchdog_agent_failed", exc_info=True)
        await session.rollback()
    return raised


async def transcripts_stuck(session: Any, now: datetime | None = None) -> int:
    """Alert for each ended call whose transcript has not been written for far too long."""
    now = now or datetime.now(UTC)
    raised = 0
    try:
        rooms = (
            await session.scalars(
                select(PiMeetingRoom).where(
                    PiMeetingRoom.state == "ended",
                    PiMeetingRoom.transcript_state == "pending",
                    PiMeetingRoom.ended_at < now - timedelta(seconds=STUCK_S),
                )
            )
        ).all()
        for room in rooms:
            scope = system_scope(room.tenant_id, room.environment_id)
            await notify(
                session,
                scope,
                KIND,
                "A call's transcript is stuck",
                f"The transcript of '{await _title(session, room)}' has not been written, "
                "so its summary is waiting. The background worker may be down; the call itself "
                "is safe.",
                link=f"/pi/meetings/{room.meeting_id}/room",
                permission=PERMISSION,
                severity="warning",
                dedupe_key=f"room-transcript-stuck:{room.id}",
            )
            raised += 1
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.warning("room_watchdog_transcripts_failed", exc_info=True)
        await session.rollback()
    return raised
