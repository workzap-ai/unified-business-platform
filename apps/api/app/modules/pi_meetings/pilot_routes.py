"""pi suggests the next question during a live meeting.

`POST /api/v1/pi/meeting-intel/{id}/pilot/suggest`. Needs the PI product, `pi.meetings.record` (the
person running the meeting), the meeting-intelligence flag and `response_rules.brain.meeting_pilot`
(default off). The suggestion goes to that staff member only; pi says nothing to the customer in
this phase. The audit entry holds ids and counts, never a question, a checklist item or a line.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.problem_models import PiProblem
from app.modules.pi_meetings import pilot
from app.modules.pi_meetings.models import PiMeetingParticipant, PiMeetingSegment
from app.modules.pi_meetings.qa import Line
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])


class SuggestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checklist: list[str] = Field(default_factory=list, max_length=pilot.MAX_ITEMS)


@router.post("/{meeting_id}/pilot/suggest")
async def suggest(
    meeting_id: UUID, data: SuggestInput, scope: Scope, session: Session, request: Request
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    if brain.get("meeting_pilot") is not True:
        raise BusinessRuleViolation(
            "MEETING_PILOT_OFF", "pi in meetings is not switched on for this workspace", 403
        )
    meeting = await _meeting(session, scope, meeting_id)
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
            .order_by(PiMeetingSegment.ordinal.desc())
            .limit(pilot.RECENT_LINES)
        )
    ).all()
    lines = [
        Line(o, t, who or "", role or "unknown", start or 0)
        for o, t, start, who, role in reversed(rows)
    ]
    items = pilot.clean_items(data.checklist)
    known: list[str] = []
    if meeting.customer_id is not None:
        known = list(
            await session.scalars(
                select(PiProblem.title)
                .where(
                    PiProblem.tenant_id == scope.tenant_id,
                    PiProblem.environment_id == scope.environment_id,
                    PiProblem.customer_id == meeting.customer_id,
                )
                .order_by(PiProblem.number.desc())
                .limit(pilot.MAX_KNOWN)
            )
        )
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    if not lines:  # nothing said yet: nothing to read, nothing to ask the model
        result = pilot.Suggestion("", [pilot.Item(t) for t in items], 0)
    else:
        try:
            result = await pilot.suggest(
                manager, scope, lines, items, known=known, language=meeting.language
            )
        except pilot.PilotFailed:
            raise BusinessRuleViolation(
                "MEETING_PILOT_UNAVAILABLE", "No suggestion right now; try again", 502
            ) from None
    await record(
        session,
        "pi.meeting_suggested",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={
            "lines_read": result.lines_read,
            "asked": bool(result.question),
            "items": len(result.checklist),
            "done": sum(1 for i in result.checklist if i.done),
        },
    )
    await session.commit()
    return {
        "question": result.question,
        "lines_read": result.lines_read,
        "checklist": [{"text": i.text, "done": i.done, "refs": i.refs} for i in result.checklist],
    }
