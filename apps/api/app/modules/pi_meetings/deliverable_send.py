"""Send an approved meeting document (summary PDF or deck) to the customer on WhatsApp.

`POST /api/v1/pi/meeting-intel/{id}/documents/{doc}/send` (staff) and the public download the
customer opens from the message, `GET /api/v1/pi-app/meeting-docs/{token}/{name}`.

pi never sends this by itself: a person with the approve permission presses send, and the message
goes through the same path as any human reply in the inbox (`PiService.human_message`), so every
rule of that path holds: a person has taken the conversation over, the customer wrote in the last
24 hours, the reply permission is needed, and the message is queued, never reported as sent here.

Extra rules for this message:

* only an APPROVED document can be sent (a draft is for the team);
* the meeting must be linked to a customer who has a conversation;
* one send per document: pressing again returns the message that was already queued;
* the customer gets a signed link (30 days) to the stored file, exactly what was approved; the
  link serves nothing once the document is deleted or the meeting erased;
* the audit entry carries ids and the kind, never the words.
"""

from typing import Any
from urllib.parse import quote as quote_name
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi import brain_docs
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service import PiService
from app.modules.pi_meetings.brain_bridge import _conversation
from app.modules.pi_meetings.deliverable_routes import MIME, NAME, _document
from app.modules.pi_meetings.models import PiMeetingDocument
from app.modules.pi_meetings.routes import _gate, _meeting
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
public_router = APIRouter(prefix="/meeting-docs", tags=["pi-meeting-intel"])

CAPTION = {
    "summary_pdf": {
        "en": "Thank you for your time. Here is the summary of our meeting.",
        "ur": "آپ کے وقت کا شکریہ۔ یہ ہماری میٹنگ کا خلاصہ ہے۔",
    },
    "deck_pptx": {
        "en": "Thank you for your time. Here is the presentation from our meeting.",
        "ur": "آپ کے وقت کا شکریہ۔ یہ ہماری میٹنگ کی پریزنٹیشن ہے۔",
    },
}


def _key(doc_id: UUID) -> str:
    return f"meeting-doc:{doc_id.hex}"


def _file_name(doc: PiMeetingDocument) -> str:
    stem, ext = NAME[doc.kind]
    stamp = doc.created_at.strftime("%Y%m%d") if doc.created_at else "meeting"
    return f"{stem}-{stamp}.{ext}"


def link_for(settings: Any, doc: PiMeetingDocument) -> str:
    """The signed link a customer opens: it carries no meeting or customer detail."""
    base = settings.pi_app_public_url.rstrip("/")
    return (
        f"{base}/api/v1/pi-app/meeting-docs/{brain_docs.doc_token(settings, doc.id)}/"
        f"{quote_name(_file_name(doc))}"
    )


@router.post("/{meeting_id}/documents/{doc_id}/send", status_code=201)
async def send_document(
    meeting_id: UUID, doc_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    meeting = await _meeting(session, scope, meeting_id)
    doc = await _document(session, scope, meeting.id, doc_id)
    if doc.status != "approved":
        raise BusinessRuleViolation(
            "MEETING_DOCUMENT_NOT_APPROVED", "Approve the document before sending it", 422
        )
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
            PiMessage.idempotency_key == _key(doc.id),
        )
    )
    if done is not None:
        return {"message_id": str(done.id), "status": done.status, "again": True}
    lines = CAPTION[doc.kind]
    caption = lines.get(doc.language, lines["en"])
    # the same checks as any person's reply in the inbox (takeover, 24 hours, permission)
    message = await PiService(session, scope).human_message(conversation_id, caption)
    message.media = {
        "document": {"link": link_for(request.app.state.settings, doc), "filename": _file_name(doc)}
    }
    message.idempotency_key = _key(doc.id)
    conversation = await session.get(PiConversation, conversation_id)
    if conversation is not None:
        conversation.last_message_preview = caption[:200]
    await record(
        session,
        "pi.meeting_document_sent",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"document_id": str(doc.id), "kind": doc.kind, "message_id": str(message.id)},
    )
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    return {"message_id": str(message.id), "status": message.status, "again": False}


@public_router.get("/{token}/{name}")
async def public_document(token: str, name: str, request: Request, session: Session) -> Response:
    """The approved file a customer opens from WhatsApp. Only an approved document is served, and
    only the stored file: what was approved is exactly what they read. The signed token is the
    only key; it expires, and the rate limit keeps it from being guessed at."""
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pi-meeting-doc", f"{token[:16]}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    doc_id = brain_docs.read_doc_token(request.app.state.settings, token)
    if doc_id is None:
        raise HTTPException(status_code=404)
    doc = await session.scalar(
        select(PiMeetingDocument)
        .where(PiMeetingDocument.id == doc_id, PiMeetingDocument.status == "approved")
        .options(undefer(PiMeetingDocument.data))
    )
    if doc is None:
        raise HTTPException(status_code=404)
    return Response(
        content=bytes(doc.data),
        media_type=MIME[doc.kind],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote_name(_file_name(doc))}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
