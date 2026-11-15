"""Send the approved meeting summary to the customer.

`POST /api/v1/pi/meeting-intel/{id}/share-summary`.

pi never sends this by itself. A person with the approve permission looks at the words, may change
them, and presses send; the message then goes through the same path as any human reply in the inbox
(`PiService.human_message`), so every rule of that path holds: the conversation must be taken over
by a person, the customer must have written in the last 24 hours, the reply permission is needed
and the message is queued, never reported as sent here.

Extra rules for this message:

* the summary insight must already be approved (or edited and approved) on the Review tab;
* the meeting must be linked to a customer who has a conversation;
* the words are redacted again, may not carry a price (pi does not price, the quote does) and are
  at most `MAX_CHARS` long;
* one summary per meeting: asking again returns the message that was already queued.

The audit entry carries ids and a length, never the words.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.memory_ledger import redacted
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service import PiService
from app.modules.pi_meetings.brain_bridge import _conversation
from app.modules.pi_meetings.insight_rules import PRICE
from app.modules.pi_meetings.models import PiMeetingInsight
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

MAX_CHARS = 900
LEAD = "Thank you for your time. Here is a short summary of our meeting:\n\n"


class ShareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # the reviewer's own wording; empty means the approved summary as it stands
    text: str = Field(default="", max_length=2000)


def _key(meeting_id: UUID) -> str:
    return f"meeting-summary:{meeting_id.hex}"


@router.post("/{meeting_id}/share-summary", status_code=201)
async def share_summary(
    meeting_id: UUID, data: ShareInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    meeting = await _meeting(session, scope, meeting_id)
    if meeting.customer_id is None:
        raise BusinessRuleViolation(
            "MEETING_NOT_LINKED", "Link this meeting to a customer first", 422
        )
    conversation_id = await _conversation(session, scope, meeting.customer_id)
    if conversation_id is None:
        raise BusinessRuleViolation(
            "MEETING_NO_CONVERSATION", "This customer has no conversation to send to", 422
        )
    done = await session.scalar(
        select(PiMessage).where(
            PiMessage.tenant_id == scope.tenant_id,
            PiMessage.environment_id == scope.environment_id,
            PiMessage.idempotency_key == _key(meeting.id),
        )
    )
    if done is not None:
        return {"message_id": str(done.id), "status": done.status, "again": True}
    summary = await session.scalar(
        select(PiMeetingInsight)
        .where(
            PiMeetingInsight.tenant_id == scope.tenant_id,
            PiMeetingInsight.environment_id == scope.environment_id,
            PiMeetingInsight.meeting_id == meeting.id,
            PiMeetingInsight.kind == "summary",
            PiMeetingInsight.review_status.in_(("approved", "edited")),
        )
        .order_by(PiMeetingInsight.created_at.desc())
        .limit(1)
    )
    if summary is None:
        raise BusinessRuleViolation(
            "MEETING_SUMMARY_NOT_APPROVED", "Approve the summary on the Review tab first", 422
        )
    words = redacted(data.text.strip() or summary.edited_text or summary.text, MAX_CHARS)
    if not words:
        raise BusinessRuleViolation("MEETING_EDIT_REFUSED", "There is nothing to send", 422)
    if PRICE.search(words):
        raise BusinessRuleViolation(
            "MEETING_PRICE_NOT_ALLOWED",
            "A price cannot be sent here: pi does not price, the quote does",
            422,
        )
    # the same checks as any person's reply in the inbox (takeover, 24 hours, permission)
    message = await PiService(session, scope).human_message(conversation_id, LEAD + words)
    message.idempotency_key = _key(meeting.id)
    conversation = await session.get(PiConversation, conversation_id)
    if conversation is not None:
        conversation.last_message_preview = (LEAD + words)[:200]
    await record(
        session,
        "pi.meeting_summary_shared",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"message_id": str(message.id), "chars": len(words)},
    )
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    return {"message_id": str(message.id), "status": message.status, "again": False}
