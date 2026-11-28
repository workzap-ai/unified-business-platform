"""Staff start, move and stop what pi presents in a live room (`/api/v1/pi/meeting-intel`).

`POST /{id}/room/present` starts a recap (the team's approved points from this customer's earlier
calls and the notes taken in this call), `POST .../present/go` moves to another slide and
`POST .../present/stop` ends it. A person with the record permission does each one, so someone is
always choosing what the room sees. It needs the workspace flag `meeting_room_present`, a live room
and pi in it. Audit entries carry ids and counts, never the words on a slide.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_meetings import meeting_memory, room_agent_claim, room_live, room_present
from app.modules.pi_meetings.room_routes import LIVE, room_of
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["recap"] = "recap"


class GoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int | None = Field(default=None, ge=-20, le=20)
    index: int | None = Field(default=None, ge=0, le=20)


async def _live_room(session: Any, scope: Any, meeting_id: UUID) -> tuple[Any, Any]:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    room = await room_of(session, scope, meeting.id)
    if room is None:
        raise HTTPException(status_code=404)
    if room.state not in LIVE:
        raise BusinessRuleViolation("MEETING_ROOM_CLOSED", "This room is not open", 409)
    return meeting, room


@router.post("/{meeting_id}/room/present")
async def start_presenting(
    meeting_id: UUID, body: StartInput, scope: Scope, session: Session
) -> dict[str, Any]:
    meeting, room = await _live_room(session, scope, meeting_id)
    if not await room_agent_claim.present_on(session, scope):
        raise BusinessRuleViolation(
            "MEETING_ROOM_PRESENT_OFF", "Presenting is not switched on for this workspace", 403
        )
    if room.pi_mode != "speak":
        raise BusinessRuleViolation("MEETING_ROOM_PI_OFF", "pi is not in this room", 409)
    earlier = await meeting_memory.earlier_calls(session, scope, meeting)
    notes = [
        tip["text"] for tip in room_live.normal(room.live)["tips"] if tip.get("kind") == "note"
    ]
    slides = room_present.build(earlier, notes)
    if not slides:
        raise BusinessRuleViolation(
            "MEETING_ROOM_NOTHING_TO_PRESENT",
            "There is nothing approved or noted to show yet",
            422,
        )
    room.present = room_present.start(slides, room.present)
    await record(
        session,
        "pi.meeting_room_present_started",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"source": body.source, "slides": len(slides)},
    )
    await session.commit()
    return {"present": room_present.summary(room.present)}


@router.post("/{meeting_id}/room/present/go")
async def go_to_slide(
    meeting_id: UUID, body: GoInput, scope: Scope, session: Session
) -> dict[str, Any]:
    meeting, room = await _live_room(session, scope, meeting_id)
    if not room_present.summary(room.present)["on"]:
        raise BusinessRuleViolation(
            "MEETING_ROOM_NOT_PRESENTING", "pi is not presenting right now", 409
        )
    room.present = room_present.go(room.present, step=body.step, index=body.index)
    await session.commit()
    return {"present": room_present.summary(room.present)}


@router.post("/{meeting_id}/room/present/stop")
async def stop_presenting(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    meeting, room = await _live_room(session, scope, meeting_id)
    was_on = room_present.summary(room.present)["on"]
    room.present = room_present.stop(room.present)
    if was_on:
        await record(
            session,
            "pi.meeting_room_present_stopped",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
            details={},
        )
    await session.commit()
    return {"present": room_present.summary(room.present)}
