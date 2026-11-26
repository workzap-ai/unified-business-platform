"""pi's own spoken lines in a room go into the meeting's transcript.

People's lines come later, from the recordings (`native_stt`) or the provider's transcript, and are
renumbered in the order they were said. pi's lines are stored as the call goes, as pi's own speaker
(`pi (AI)`, the same one the link-page conversation uses), numbered in the same range as everyone's,
and carry no provider user id. That is what lets the final rebuild keep them and sort them in among
the others by time: it only replaces the lines of people it transcribed.

Times are milliseconds from the room's start. The final transcript (`native_stt`) puts people's
lines on the same clock, from when each person entered, so a question and its answer sort in the
order they were said. A line can still sit a few seconds off its true place.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import voice
from app.modules.pi_meetings.bot_ingest import LINE_CHARS, MAX_LINES, VOICE_BASE
from app.modules.pi_meetings.models import PiMeetingSegment
from app.modules.pi_meetings.room_agent_claim import Orders
from app.modules.pi_meetings.voice_routes import _pi_participant

SPEAKING_MS = 60  # a spoken line lasts at least this per character: a rough length for its end time


async def store_pi_line(
    session: Any, orders: Orders, words: str, *, now: datetime | None = None
) -> bool:
    """Add one line pi said. The caller commits. False when nothing was stored."""
    line = redacted(words, LINE_CHARS)
    if not line:
        return False
    now = now or datetime.now(UTC)
    scope = orders.scope
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"room-ingest:{orders.meeting_id}"},
    )
    top = await session.scalar(
        select(func.max(PiMeetingSegment.ordinal)).where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == orders.meeting_id,
            PiMeetingSegment.ordinal < VOICE_BASE,
        )
    )
    ordinal = 0 if top is None else top + 1
    if ordinal >= MAX_LINES:
        return False
    began = orders.started_at or now
    end_ms = max(1, int((now - began).total_seconds() * 1000))
    start_ms = max(0, end_ms - SPEAKING_MS * len(line))
    pi_id = await _pi_participant(session, scope, orders.meeting_id)
    session.add(
        PiMeetingSegment(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=orders.meeting_id,
            ordinal=ordinal,
            start_ms=start_ms,
            end_ms=max(end_ms, start_ms + 1),
            participant_id=pi_id,
            text=line,
            text_hash=hashlib.sha256(line.lower().encode()).hexdigest(),
        )
    )
    return True


def is_pi(speaker: str) -> bool:
    return speaker == voice.PI_LABEL
