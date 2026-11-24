"""What a video room's provider tells us becomes meeting state and transcript lines.

The words come after the call, as one finished transcript the provider assembled from everyone's
audio: one line per sentence with the id of who spoke and when. They are stored here, idempotently
(a callback is retried; the same line twice is stored once) and redacted before storage.

The speaker is the room's own user id: `s_...` for staff who logged in, `g_...` for a guest who
joined by link and agreed to be recorded. That id is the only thing used to say who spoke. A
guest's lines stay role `unknown`: only a person's mapping ever says someone IS the customer.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.bot_ingest import LINE_CHARS, MAX_LINES, MAX_MS, VOICE_BASE
from app.modules.pi_meetings.guest_routes import RESERVED_LABELS
from app.modules.pi_meetings.models import (
    PiMeeting,
    PiMeetingParticipant,
    PiMeetingRoom,
    PiMeetingSegment,
)
from app.modules.pi_meetings.recording_routes import join_spoken_digits
from app.shared.scope import WorkspaceScope

NO_SPEECH = "No speech was captured in the call"
# people the provider shows in a call that are not a person who spoke to us
NOT_PEOPLE = frozenset({"pi_server", "pi_agent"})


def _ms(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return max(0, min(MAX_MS, int(value)))


async def participant_for(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting_id: Any,
    stream_user: str,
    *,
    label: str,
    role: str = "unknown",
) -> PiMeetingParticipant:
    """The meeting's participant for a room user id, made the first time they appear."""
    found = await session.scalar(
        select(PiMeetingParticipant).where(
            PiMeetingParticipant.tenant_id == scope.tenant_id,
            PiMeetingParticipant.environment_id == scope.environment_id,
            PiMeetingParticipant.meeting_id == meeting_id,
            PiMeetingParticipant.stream_user_id == stream_user,
        )
    )
    if found is not None:
        return found
    taken = set(
        (
            await session.scalars(
                select(func.lower(PiMeetingParticipant.label)).where(
                    PiMeetingParticipant.tenant_id == scope.tenant_id,
                    PiMeetingParticipant.environment_id == scope.environment_id,
                    PiMeetingParticipant.meeting_id == meeting_id,
                )
            )
        ).all()
    )
    shown = redacted(label, 60).strip() or "Participant"
    candidate, n = shown, 1
    while candidate.lower() in taken or candidate.lower() in RESERVED_LABELS:
        n += 1
        candidate = f"{shown[:54]} ({n})"
    made = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        label=candidate,
        role=role,
        stream_user_id=stream_user,
    )
    session.add(made)
    await session.flush()
    return made


def spoken(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The lines a person said, in the order they began: not the provider's other entries, and not
    the lines of its own server users."""
    speech = [
        r
        for r in rows
        if isinstance(r, dict)
        and r.get("type") == "speech"
        and isinstance(r.get("text"), str)
        and isinstance(r.get("speaker_id"), str)
        and r["speaker_id"] not in NOT_PEOPLE
    ]
    speech.sort(key=lambda r: (_ms(r.get("start_ts")) or 0, _ms(r.get("stop_ts")) or 0))
    return speech


async def add_lines(
    session: AsyncSession, scope: WorkspaceScope, meeting: PiMeeting, rows: list[dict[str, Any]]
) -> int:
    """Store the transcript lines of one call; returns how many were new."""
    speech = spoken(rows)
    # one transcript is applied at a time, so numbering never collides with a retried callback
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"room-ingest:{meeting.id}"}
    )
    top = await session.scalar(
        select(func.max(PiMeetingSegment.ordinal)).where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
            PiMeetingSegment.ordinal < VOICE_BASE,
        )
    )
    nxt = 0 if top is None else top + 1
    added = 0
    for row in speech:
        line = redacted(join_spoken_digits(str(row["text"])), LINE_CHARS)
        if not line or nxt >= MAX_LINES:
            continue
        start = _ms(row.get("start_ts")) or 0
        end = max(start + 1, _ms(row.get("stop_ts")) or start + 1000)
        speaker = await participant_for(
            session, scope, meeting.id, row["speaker_id"][:80], label="Participant"
        )
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
            continue
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
        nxt += 1
        added += 1
    return added


async def finish_transcript(
    session: AsyncSession,
    scope: WorkspaceScope,
    meeting: PiMeeting,
    room: PiMeetingRoom,
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> None:
    """The call's transcript arrived: store it and hand the meeting to analysis."""
    now = now or datetime.now(UTC)
    await add_lines(session, scope, meeting, rows)
    total = await session.scalar(
        select(func.count())
        .select_from(PiMeetingSegment)
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting.id,
        )
    )
    room.lines = int(total or 0)
    room.transcript_state = "done"
    if room.lines == 0:
        meeting.status = "failed"
        meeting.failure_reason = NO_SPEECH
        return
    if meeting.status in ("created", "transcribing"):
        meeting.status = "analysing"
        meeting.failure_reason = ""
    longest = max((_ms(r.get("stop_ts")) or 0 for r in spoken(rows)), default=0)
    meeting.duration_ms = max(meeting.duration_ms, longest)
    if meeting.held_at is None:
        meeting.held_at = room.started_at or now
