"""Designed documents after a meeting: the summary PDF and the deck (`/api/v1/pi/meeting-intel`).

`POST /{id}/documents` draws a document from the meeting's APPROVED insights (pending and rejected
ones are never used), `GET /{id}/documents` lists them, `GET .../{doc}/download` returns the file,
`POST .../{doc}/approve` marks a draft as approved, `DELETE .../{doc}` removes a draft.

pi drafts; a person with the approve permission approves; a person sends. A draft can be opened by
the team, and only an approved document may be sent on to a customer (sending is a separate step
that goes through the inbox's own rules). No price, phone, card or ID number can be in a document
(`deliverables/content.py`), a draw that would leave Urdu text out is refused instead of delivered
with a gap, and the same approved content gives the same draft, not a new one each press.

Audit entries carry ids, the kind and counts, never the words.
"""

import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import undefer

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_meetings.deliverables import content as builder
from app.modules.pi_meetings.deliverables import deck, pdf_report
from app.modules.pi_meetings.models import (
    DOCUMENT_KINDS,
    MAX_DOCUMENT_BYTES,
    PiMeetingDocument,
    PiMeetingInsight,
    PiMeetingParticipant,
)
from app.modules.pi_meetings.routes import _gate, _meeting
from app.modules.tenants.errors import ResourceNotFound
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])

MAX_DOCUMENTS = 20  # per meeting: a stuck page cannot fill the table
MIME = {
    "summary_pdf": "application/pdf",
    "deck_pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
NAME = {"summary_pdf": ("meeting-summary", "pdf"), "deck_pptx": ("meeting-deck", "pptx")}


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str


def _view(d: PiMeetingDocument) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "meeting_id": str(d.meeting_id),
        "kind": d.kind,
        "status": d.status,
        "title": d.title,
        "language": d.language,
        "size_bytes": d.size_bytes,
        "insights_used": d.insight_count,
        "lines_left_out": d.dropped_count,
        "approved_at": d.approved_at.isoformat() if d.approved_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


def _mine(scope: Any) -> tuple[Any, ...]:
    return (
        PiMeetingDocument.tenant_id == scope.tenant_id,
        PiMeetingDocument.environment_id == scope.environment_id,
    )


async def _document(
    session: Any, scope: Any, meeting_id: UUID, doc_id: UUID, *, with_data: bool = False
) -> PiMeetingDocument:
    query = select(PiMeetingDocument).where(
        *_mine(scope), PiMeetingDocument.meeting_id == meeting_id, PiMeetingDocument.id == doc_id
    )
    if with_data:
        query = query.options(undefer(PiMeetingDocument.data))  # the file itself, read only here
    found = await session.scalar(query)
    if found is None:
        raise ResourceNotFound
    return found  # type: ignore[no-any-return]


@router.post("/{meeting_id}/documents")
async def make_document(
    meeting_id: UUID, data: DocumentInput, scope: Scope, session: Session, response: Response
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    if data.kind not in DOCUMENT_KINDS:
        raise BusinessRuleViolation(
            "MEETING_DOCUMENT_KIND_INVALID", "Choose the summary PDF or the deck", 422
        )
    meeting = await _meeting(session, scope, meeting_id)
    insights = (
        await session.scalars(
            select(PiMeetingInsight)
            .where(
                PiMeetingInsight.tenant_id == scope.tenant_id,
                PiMeetingInsight.environment_id == scope.environment_id,
                PiMeetingInsight.meeting_id == meeting.id,
                PiMeetingInsight.review_status.in_(("approved", "edited")),
            )
            .order_by(PiMeetingInsight.created_at, PiMeetingInsight.id)
        )
    ).all()
    people = (
        await session.execute(
            select(PiMeetingParticipant.label, PiMeetingParticipant.role)
            .where(
                PiMeetingParticipant.tenant_id == scope.tenant_id,
                PiMeetingParticipant.environment_id == scope.environment_id,
                PiMeetingParticipant.meeting_id == meeting.id,
            )
            .order_by(PiMeetingParticipant.label)
        )
    ).all()
    content = builder.build(
        title=meeting.title,
        held_at=meeting.held_at,
        created_at=meeting.created_at,
        participants=[(label, role) for label, role in people],
        insights=list(insights),
    )
    if content.empty:
        raise BusinessRuleViolation(
            "MEETING_NOTHING_APPROVED",
            "Approve at least one finding on the Review tab before making a document",
            422,
        )
    source = hashlib.sha256(
        json.dumps([data.kind, asdict(content)], sort_keys=True, default=str).encode()
    ).hexdigest()
    same = await session.scalar(
        select(PiMeetingDocument)
        .where(
            *_mine(scope),
            PiMeetingDocument.meeting_id == meeting.id,
            PiMeetingDocument.kind == data.kind,
            PiMeetingDocument.source_hash == source,
        )
        .order_by(PiMeetingDocument.created_at.desc())
        .limit(1)
    )
    if same is not None:
        return {**_view(same), "again": True}
    count = await session.scalar(
        select(func.count())
        .select_from(PiMeetingDocument)
        .where(*_mine(scope), PiMeetingDocument.meeting_id == meeting.id)
    )
    if (count or 0) >= MAX_DOCUMENTS:
        raise BusinessRuleViolation(
            "MEETING_DOCUMENT_LIMIT", "This meeting has enough documents; delete a draft first", 409
        )
    if data.kind == "summary_pdf":
        body, hidden = await asyncio.to_thread(pdf_report.render, content)
        if hidden:
            raise BusinessRuleViolation(
                "MEETING_DOCUMENT_FONT_MISSING",
                "This document needs a font the server does not have, so it was not made",
                503,
            )
    else:
        body = await asyncio.to_thread(deck.render, content)
    if len(body) > MAX_DOCUMENT_BYTES:
        raise BusinessRuleViolation(
            "MEETING_DOCUMENT_TOO_LARGE", "This document is too large to keep", 422
        )
    made = PiMeetingDocument(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        kind=data.kind,
        status="draft",
        title=content.title,
        language=content.language,
        size_bytes=len(body),
        source_hash=source,
        insight_count=content.used,
        dropped_count=content.dropped,
        created_by=scope.user_id,
        data=body,
    )
    session.add(made)
    await session.flush()
    await record(
        session,
        "pi.meeting_document_created",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={
            "document_id": str(made.id),
            "kind": data.kind,
            "insights": content.used,
            "left_out": content.dropped,
            "bytes": len(body),
        },
    )
    await session.commit()
    response.status_code = 201
    return {**_view(made), "again": False}


@router.get("/{meeting_id}/documents")
async def list_documents(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    rows = await session.scalars(
        select(PiMeetingDocument)
        .where(*_mine(scope), PiMeetingDocument.meeting_id == meeting.id)
        .order_by(PiMeetingDocument.created_at.desc())
    )
    return {"items": [_view(d) for d in rows.all()]}


@router.get("/{meeting_id}/documents/{doc_id}/download")
async def download_document(
    meeting_id: UUID, doc_id: UUID, scope: Scope, session: Session
) -> Response:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    doc = await _document(session, scope, meeting.id, doc_id, with_data=True)
    stem, ext = NAME[doc.kind]
    stamp = (doc.created_at or datetime.now(UTC)).strftime("%Y%m%d")
    return Response(
        content=bytes(doc.data),
        media_type=MIME[doc.kind],
        headers={
            "Content-Disposition": f'attachment; filename="{stem}-{stamp}.{ext}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{meeting_id}/documents/{doc_id}/approve")
async def approve_document(
    meeting_id: UUID, doc_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    meeting = await _meeting(session, scope, meeting_id)
    doc = await _document(session, scope, meeting.id, doc_id)
    if doc.status == "draft":
        doc.status = "approved"
        doc.approved_by = scope.user_id
        doc.approved_at = datetime.now(UTC)
        await record(
            session,
            "pi.meeting_document_approved",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
            details={"document_id": str(doc.id), "kind": doc.kind},
        )
        await session.commit()
    return _view(doc)


@router.delete("/{meeting_id}/documents/{doc_id}", status_code=204)
async def delete_document(meeting_id: UUID, doc_id: UUID, scope: Scope, session: Session) -> None:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    doc = await _document(session, scope, meeting.id, doc_id)
    if doc.status != "draft":
        raise BusinessRuleViolation(
            "MEETING_DOCUMENT_APPROVED", "An approved document cannot be deleted here", 409
        )
    await session.delete(doc)
    await record(
        session,
        "pi.meeting_document_deleted",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"document_id": str(doc.id), "kind": doc.kind},
    )
    await session.commit()
