"""What the bot's provider tells us becomes meeting state and transcript lines.

Two kinds of callback arrive: where the bot is (joining, waiting to be let in, recording, done) and
the words as they are said. Both are applied here, idempotently, because a provider retries: the
same status twice changes nothing, the same line twice is stored once.

The words are the provider's own speech-to-text. The speaker is the NAME THE CALL SHOWS for that
person (a Zoom or Meet display name), kept as a label with role `unknown`. It says who the platform
says spoke; it never says the person is the customer, which only a human mapping does.
"""

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.bot_provider import our_status
from app.modules.pi_meetings.guest_routes import RESERVED_LABELS
from app.modules.pi_meetings.models import (
    BOT_ACTIVE,
    PiMeeting,
    PiMeetingBot,
    PiMeetingParticipant,
    PiMeetingSegment,
)
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.shared.scope import WorkspaceScope

LINE_CHARS = 1000
MAX_LINES = 20_000  # one call's transcript: a flood of callbacks cannot grow it without end
MAX_MS = 24 * 3600 * 1000
VOICE_BASE = 100_000_000  # ordinals from here belong to the link-page conversation
# a status only moves forward: a late "joining" after "recording" is ignored
RANK = {
    "requested": 0,
    "joining": 1,
    "waiting": 2,
    "in_call": 3,
    "recording": 4,
    "denied": 5,
    "ended": 6,
    "done": 7,
    "failed": 7,
}
REASONS = {
    "denied": "The host did not allow the bot to record",
    "failed": "The bot could not stay in the meeting",
}
_SAFE = re.compile(r"[^\w.-]")


def _ms(stamp: Any) -> int | None:
    value = stamp.get("relative") if isinstance(stamp, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return max(0, min(MAX_MS, int(value * 1000)))


async def apply_status(
    session: AsyncSession,
    bot: PiMeetingBot,
    meeting: PiMeeting,
    code: str,
    sub_code: str = "",
    *,
    now: datetime | None = None,
) -> bool:
    """Move the bot (and, at the end, the meeting) forward. False when nothing changed."""
    new = our_status(code)
    if new is None or RANK[new] < RANK[bot.status] or (new == bot.status and new != "failed"):
        return False
    now = now or datetime.now(UTC)
    bot.status = new
    bot.sub_code = _SAFE.sub("", sub_code or "")[:80]
    if new == "recording":
        bot.started_at = bot.started_at or now
        if meeting.recording_started_at is None:
            meeting.recording_started_at = now
    if new in ("ended", "done", "failed", "denied"):
        bot.ended_at = bot.ended_at or now
    if new in REASONS:
        meeting.status = "failed"
        meeting.failure_reason = REASONS[new]
    elif new == "done":
        have = await session.scalar(
            select(PiMeetingSegment.id)
            .where(
                PiMeetingSegment.tenant_id == meeting.tenant_id,
                PiMeetingSegment.environment_id == meeting.environment_id,
                PiMeetingSegment.meeting_id == meeting.id,
            )
            .limit(1)
        )
        if have is None:
            meeting.status = "failed"
            meeting.failure_reason = "No speech was captured in the call"
        else:
            meeting.status = "analysing"
            meeting.failure_reason = ""
            if meeting.recording_started_at is not None:
                spent = (now - meeting.recording_started_at).total_seconds()
                meeting.duration_ms = max(meeting.duration_ms, int(spent * 1000))
    return True


async def _participant(
    session: AsyncSession, scope: WorkspaceScope, meeting_id: Any, who: dict[str, Any]
) -> PiMeetingParticipant:
    shown = redacted(str(who.get("name") or ""), 60).strip()
    label = shown or f"Participant {str(who.get('id') or '')[:8] or '?'}"
    if label.lower() in RESERVED_LABELS:  # nobody in a call can be pi, or the host's own lines
        label = f"{label} (call)"
    found = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.label == label,
        )
    )
    if found is not None:
        return found
    made = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        label=label,
        role="unknown",
    )
    session.add(made)
    await session.flush()
    return made


async def add_words(
    session: AsyncSession, scope: WorkspaceScope, meeting: PiMeeting, data: dict[str, Any]
) -> bool:
    """Store one utterance. False when empty, a repeat, or the call's line limit is reached."""
    words = data.get("words")
    if not isinstance(words, list) or not words:
        return False
    pieces = [w["text"] for w in words if isinstance(w, dict) and isinstance(w.get("text"), str)]
    line = redacted(join_spoken_digits(" ".join(pieces)), LINE_CHARS)
    if not line:
        return False
    first = words[0] if isinstance(words[0], dict) else {}
    last = words[-1] if isinstance(words[-1], dict) else {}
    start = _ms(first.get("start_timestamp")) or 0
    end = _ms(last.get("end_timestamp"))
    end = max(start + 1, end if end is not None else start + 1000)
    who = data.get("participant")
    # callbacks for one meeting are applied one at a time, so ordinals never collide
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"bot-ingest:{meeting.id}"}
    )
    speaker = await _participant(session, scope, meeting.id, who if isinstance(who, dict) else {})
    key = hashlib.sha256(line.lower().encode()).hexdigest()
    repeat = await session.scalar(
        select(PiMeetingSegment.id)
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
            PiMeetingSegment.participant_id == speaker.id,
            PiMeetingSegment.start_ms == start,
            PiMeetingSegment.text_hash == key,
        )
        .limit(1)
    )
    if repeat is not None:
        return False
    top = await session.scalar(
        select(func.max(PiMeetingSegment.ordinal)).where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
            PiMeetingSegment.ordinal < VOICE_BASE,
        )
    )
    nxt = 0 if top is None else top + 1
    if nxt >= MAX_LINES:
        return False
    session.add(
        PiMeetingSegment(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=meeting.id,
            ordinal=nxt,
            start_ms=start,
            end_ms=end,
            participant_id=speaker.id,
            text=line,
            text_hash=key,
        )
    )
    if meeting.status == "created":
        meeting.status = "transcribing"
    return True


def is_active(bot: PiMeetingBot) -> bool:
    return bot.status in BOT_ACTIVE
