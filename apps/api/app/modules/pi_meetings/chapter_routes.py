"""Chapters and key moments of a meeting (`/api/v1/pi/meeting-intel`).

`POST /{id}/chapters` makes (or remakes) the chapters from the transcript with one model call;
`GET /{id}/chapters` returns them with the key moments (the approved findings, at their time).
Nothing here is approved, sent or written to memory. Audit entries carry ids and counts only.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_meetings import chapters
from app.modules.pi_meetings.models import PiMeetingInsight, PiMeetingParticipant, PiMeetingSegment
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

REMAKE_AFTER = timedelta(seconds=30)  # pressing twice makes the chapters once


async def _lines(session: Any, scope: Any, meeting_id: UUID) -> list[chapters.Line]:
    rows = await session.execute(
        select(
            PiMeetingSegment.ordinal,
            PiMeetingSegment.start_ms,
            PiMeetingSegment.end_ms,
            PiMeetingParticipant.label,
            PiMeetingSegment.text,
        )
        .join(
            PiMeetingParticipant,
            PiMeetingParticipant.id == PiMeetingSegment.participant_id,
            isouter=True,
        )
        .where(
            PiMeetingSegment.tenant_id == scope.tenant_id,
            PiMeetingSegment.environment_id == scope.environment_id,
            PiMeetingSegment.meeting_id == meeting_id,
        )
        .order_by(PiMeetingSegment.ordinal)
    )
    return [chapters.Line(o, s, e, who or "", text) for o, s, e, who, text in rows.all()]


async def _view(
    session: Any, scope: Any, meeting: Any, lines: list[chapters.Line]
) -> dict[str, Any]:
    stored = meeting.chapters if isinstance(meeting.chapters, dict) else {}
    insights = (
        await session.scalars(
            select(PiMeetingInsight).where(
                PiMeetingInsight.tenant_id == scope.tenant_id,
                PiMeetingInsight.environment_id == scope.environment_id,
                PiMeetingInsight.meeting_id == meeting.id,
                PiMeetingInsight.review_status.in_(("approved", "edited")),
            )
        )
    ).all()
    times = {line.ordinal: line.start_ms for line in lines}
    return {
        "made_at": stored.get("made_at"),
        "chapters": list(stored.get("items") or []),
        "moments": chapters.moments(insights, times),
        "lines": len(lines),
    }


@router.get("/{meeting_id}/chapters")
async def get_chapters(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    return await _view(session, scope, meeting, await _lines(session, scope, meeting.id))


@router.post("/{meeting_id}/chapters")
async def make_chapters(
    meeting_id: UUID, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    lines = await _lines(session, scope, meeting.id)
    if not lines:
        raise BusinessRuleViolation("TRANSCRIPT_EMPTY", "There is no transcript yet", 422)
    stored = meeting.chapters if isinstance(meeting.chapters, dict) else {}
    made = stored.get("made_at")
    if made and datetime.now(UTC) - datetime.fromisoformat(made) < REMAKE_AFTER:
        return await _view(session, scope, meeting, lines)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    try:
        meeting.chapters = await chapters.make(manager, scope, lines, meeting.language)
    except chapters.ChaptersFailed:
        raise BusinessRuleViolation(
            "MEETING_CHAPTERS_FAILED", "The chapters could not be made; try again", 502
        ) from None
    await record(
        session,
        "pi.meeting_chapters_made",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"chapters": len(meeting.chapters["items"]), "lines": len(lines)},
    )
    await session.commit()
    return await _view(session, scope, meeting, lines)
