"""Ask a meeting a question (`POST /api/v1/pi/meeting-intel/{id}/ask`).

Needs the PI product, `pi.meetings.read` and the meeting-intelligence flag, like reading the
transcript. The audit entry carries ids and counts only, never the question or the answer.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_meetings import qa
from app.modules.pi_meetings.models import PiMeetingParticipant, PiMeetingSegment
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

MAX_QUESTION_CHARS = 300
SNIPPET_CHARS = 240


class AskInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


@router.post("/{meeting_id}/ask")
async def ask_meeting(
    meeting_id: UUID, data: AskInput, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    question = " ".join(data.question.split())
    rows = (
        await session.execute(
            select(
                PiMeetingSegment.ordinal,
                PiMeetingSegment.text,
                PiMeetingSegment.start_ms,
                PiMeetingParticipant.label,
                PiMeetingParticipant.role,
            )
            .join(
                PiMeetingParticipant,
                (PiMeetingParticipant.id == PiMeetingSegment.participant_id)
                & (PiMeetingParticipant.tenant_id == PiMeetingSegment.tenant_id)
                & (PiMeetingParticipant.environment_id == PiMeetingSegment.environment_id),
                isouter=True,
            )
            .where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.environment_id == scope.environment_id,
                PiMeetingSegment.meeting_id == meeting.id,
            )
            .order_by(PiMeetingSegment.ordinal)
        )
    ).all()
    if not rows:
        raise BusinessRuleViolation("TRANSCRIPT_EMPTY", "This meeting has no transcript yet", 422)
    lines = [
        qa.Line(o, t, who or "", role or "unknown", start or 0) for o, t, start, who, role in rows
    ]
    hits: list[int] = []
    terms = qa.search_terms(question)
    if terms and sum(len(x.text) for x in lines) > qa.QA_CHARS:
        position = {x.ordinal: i for i, x in enumerate(lines)}
        match = func.to_tsquery("simple", " | ".join(terms))
        found = await session.scalars(
            select(PiMeetingSegment.ordinal)
            .where(
                PiMeetingSegment.tenant_id == scope.tenant_id,
                PiMeetingSegment.environment_id == scope.environment_id,
                PiMeetingSegment.meeting_id == meeting.id,
                PiMeetingSegment.tsv.op("@@")(match),
            )
            .order_by(func.ts_rank(PiMeetingSegment.tsv, match).desc())
            .limit(qa.HITS)
        )
        hits = [position[o] for o in found if o in position]
    part, partial = qa.pick(lines, hits)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    try:
        answer = await qa.ask(
            manager, scope, question, part, partial=partial, language=meeting.language
        )
    except qa.AskFailed:
        raise BusinessRuleViolation(
            "MEETING_ASK_UNAVAILABLE", "The answer could not be written; try again", 502
        ) from None
    await record(
        session,
        "pi.meeting_asked",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={
            "found": answer.found,
            "lines_read": len(part),
            "lines_total": len(lines),
            "question_chars": len(question),
        },
    )
    await session.commit()
    return {
        "found": answer.found,
        "answer": answer.text,
        "partial": answer.partial,
        "sources": [
            {
                "ordinal": s.ordinal,
                "speaker": s.speaker,
                "role": s.role,
                "start_ms": s.start_ms,
                "text": s.text[:SNIPPET_CHARS],
            }
            for s in answer.sources
        ],
    }
