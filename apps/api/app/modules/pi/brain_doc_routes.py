"""Reviewing the solution document and quote pi drafted (pi Brain spec 5.1, R-DOC-00).

``router`` is for the Workzap team (Owner OS /api/v1/pi/brain-documents and the pi app's
/api/v1/pi-app/pi/brain-documents). ``public_router`` serves the approved PDF a customer
opens from the WhatsApp message (/api/v1/pi-app/brain-docs/{token}/{name}); the signed
token is the only key.
"""

import json
from typing import Any
from urllib.parse import quote as quote_name
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.manager import build_llm_manager
from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers import files
from app.modules.pi import box_lifecycle, brain_docs, brain_payments, learning_docs
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.configuration import settings_row
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi/brain-documents", tags=["pi-brain-documents"])
public_router = APIRouter(prefix="/brain-docs", tags=["pi-brain-documents"])


class PatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Solution: components, covers, wont_do, needs. Quote: included, not_included, payment,
    # cost {total, currency, tax_text, instalments}, time {estimate, milestones}, valid_until.
    components: list[dict[str, Any]] | None = None
    covers: list[str] | None = None
    wont_do: list[dict[str, Any]] | None = None
    needs: list[str] | None = None
    # Solution Box (spec 5.2): section 7 and 3 edits, phase names (solution) or phase prices (quote)
    assumptions: list[str] | None = None
    ideas: list[dict[str, Any]] | None = None
    phases: list[dict[str, Any]] | None = None
    included: list[str] | None = None
    not_included: list[str] | None = None
    payment: str | None = None
    cost: dict[str, Any] | None = None
    time: dict[str, Any] | None = None
    valid_until: str | None = None
    review_notes: str | None = None


def _view(doc: PiBrainDocument, issues: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": doc.id,
        "ref": doc.ref,
        "kind": doc.kind,
        "version": doc.version,
        "status": doc.status,
        "offer_id": doc.offer_id,
        "customer_id": doc.customer_id,
        "conversation_id": doc.conversation_id,
        "solution_id": doc.solution_id,
        "language": doc.language,
        "content": doc.content,
        "content_en": doc.content_en,
        "total": str(doc.total) if doc.total is not None else None,
        "currency": doc.currency,
        "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
        "drafted_by": doc.drafted_by,
        "approved_by": doc.approved_by,
        "approved_at": doc.approved_at,
        "sent_at": doc.sent_at,
        "review_notes": doc.review_notes,
        "blockers": issues if issues is not None else [],
        "created_at": doc.created_at,
    }


async def _doc(session: Session, scope: Scope, doc_id: UUID) -> PiBrainDocument:
    return await WorkspaceRepository(session, PiBrainDocument, scope).get(doc_id)


@router.get("")
async def list_documents(
    scope: Scope, session: Session, status: str | None = None, kind: str | None = None
) -> dict[str, Any]:
    await require_pi(session, scope, "sales.read")
    repo = WorkspaceRepository(session, PiBrainDocument, scope)
    query = repo.select().order_by(PiBrainDocument.created_at.desc()).limit(100)
    if status:
        query = query.where(PiBrainDocument.status == status)
    if kind:
        query = query.where(PiBrainDocument.kind == kind)
    rows = list((await session.scalars(query)).all())
    return {"items": [_view(r) for r in rows]}


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str = ""  # the bank's reference for the transfer
    note: str = ""


@router.get("/payments")
async def list_payments(
    scope: Scope, session: Session, status: str | None = None
) -> dict[str, Any]:
    """Transfers waiting for Workzap: claimed ones first (the customer says they paid)."""
    await require_pi(session, scope, "billing.read")
    repo = WorkspaceRepository(session, PiBrainPayment, scope)
    query = repo.select().order_by(PiBrainPayment.created_at.desc()).limit(100)
    if status:
        query = query.where(PiBrainPayment.status == status)
    rows = list((await session.scalars(query)).all())
    quotes = {
        q.id: q
        for q in (
            await session.scalars(
                select(PiBrainDocument).where(PiBrainDocument.id.in_([r.quote_id for r in rows]))
            )
        ).all()
    }
    items = [brain_payments.view(r, quotes.get(r.quote_id)) for r in rows]
    items.sort(key=lambda i: i["status"] != "claimed")
    return {"items": items}


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(
    payment_id: UUID, data: ConfirmInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Staff confirm the bank transfer arrived: the only way a payment becomes confirmed (R-PAY-05).
    The chat moves to S11 and the customer is told."""
    await require_pi(session, scope, "billing.write")
    ids = await brain_payments.confirm(
        session, scope, payment_id, scope.user_id, data.reference, data.note
    )
    await record(
        session,
        "pi.brain_payment_confirmed",
        scope=scope,
        entity_type="pi_brain_payment",
        entity_id=payment_id,
        details={"reference": data.reference[:120]},
    )
    payment = await WorkspaceRepository(session, PiBrainPayment, scope).get(payment_id)
    quote = await session.get(PiBrainDocument, payment.quote_id)
    await session.commit()
    for message_id in ids:
        await request.app.state.queue.enqueue(
            "send_pi_message", message_id, job_id=f"send:{message_id}"
        )
    return {**brain_payments.view(payment, quote), "notified": bool(ids)}


@router.get("/{doc_id}")
async def get_document(doc_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "sales.read")
    doc = await _doc(session, scope, doc_id)
    return _view(doc, await brain_docs.blockers(session, scope, doc))


@router.patch("/{doc_id}")
async def edit_document(
    doc_id: UUID, data: PatchInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "quotes.write")
    doc = await _doc(session, scope, doc_id)
    patch = data.model_dump(exclude_none=True)
    before, drafted_by = json.loads(json.dumps(doc.content)), doc.drafted_by
    brain_docs.edit(doc, patch)
    rules = (await settings_row(session, scope)).response_rules
    await learning_docs.learn_from_edit(
        session, scope, doc, before, drafted_by, rules, scope.user_id
    )
    await record(
        session,
        "pi.brain_document_edited",
        scope=scope,
        entity_type="pi_brain_document",
        entity_id=doc.id,
        details={"ref": doc.ref, "fields": sorted(patch)},
    )
    await session.commit()
    return _view(doc, await brain_docs.blockers(session, scope, doc))


class OutcomeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str = Field(pattern="^(won|lost|stalled)$")
    note: str = Field(default="", max_length=300)


@router.post("/{doc_id}/outcome")
async def quote_outcome(
    doc_id: UUID, data: OutcomeInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """Win/loss note on a quote (spec 8.10): it improves later documents and quotes, never what pi
    says in a chat."""
    await require_pi(session, scope, "quotes.write")
    doc = await _doc(session, scope, doc_id)
    rules = (await settings_row(session, scope)).response_rules
    offered = await learning_docs.record_outcome(
        session, scope, doc, data.result, data.note, rules, scope.user_id
    )
    await record(
        session,
        "pi.brain_quote_outcome",
        scope=scope,
        entity_type="pi_brain_document",
        entity_id=doc.id,
        details={"ref": doc.ref, "result": data.result, "lesson_offered": offered},
    )
    await session.commit()
    return {**_view(doc), "lesson_offered": offered}


@router.post("/{doc_id}/approve")
async def approve_document(doc_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """The reviewer's approval. Refused (409) while a rule is broken or a price is missing."""
    await require_pi(session, scope, "quotes.approve")
    doc = await _doc(session, scope, doc_id)
    await brain_docs.approve(session, scope, doc, scope.user_id)
    await box_lifecycle.on_approved(session, scope, doc.customer_id, str(scope.user_id or ""))
    await record(
        session,
        "pi.brain_document_approved",
        scope=scope,
        entity_type="pi_brain_document",
        entity_id=doc.id,
        details={"ref": doc.ref},
    )
    await session.commit()
    return _view(doc)


@router.post("/{doc_id}/revise", status_code=201)
async def revise_document(
    doc_id: UUID, data: PatchInput, scope: Scope, session: Session
) -> dict[str, Any]:
    """A new version after the customer asked for changes; the old one is superseded."""
    await require_pi(session, scope, "quotes.write")
    doc = await _doc(session, scope, doc_id)
    fresh = await brain_docs.revise(session, scope, doc, data.model_dump(exclude_none=True))
    await record(
        session,
        "pi.brain_document_revised",
        scope=scope,
        entity_type="pi_brain_document",
        entity_id=fresh.id,
        details={"ref": fresh.ref, "from": doc.ref},
    )
    await session.commit()
    return _view(fresh, await brain_docs.blockers(session, scope, fresh))


@router.post("/offers/{offer_id}/send")
async def send_offer(
    offer_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Send the approved solution document and quote to the customer on WhatsApp."""
    await require_pi(session, scope, "quotes.write")
    ids = await brain_docs.send(session, scope, request.app.state.settings, offer_id)
    sent_solution, sent_quote = await brain_docs.latest_pair(session, scope, offer_id)
    pair = [d for d in (sent_solution, sent_quote) if d is not None]
    await box_lifecycle.on_sent(
        session,
        scope,
        sent_solution.customer_id if sent_solution else None,
        str(scope.user_id or ""),
        approved_document=len(pair) == 2 and all(d.status in ("approved", "sent") for d in pair),
    )
    await record(
        session,
        "pi.brain_documents_sent",
        scope=scope,
        entity_type="pi_brain_offer",
        entity_id=offer_id,
        details={"messages": len(ids)},
    )
    await session.commit()
    for message_id in ids:
        await request.app.state.queue.enqueue(
            "send_pi_message", message_id, job_id=f"send:{message_id}"
        )
    return {"offer_id": offer_id, "queued": len(ids)}


@router.post("/conversations/{conversation_id}/draft", status_code=201)
async def draft_for_conversation(
    conversation_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Draft the solution document and quote for a customer who said yes (normally pi does this
    on its own; this is for a retry)."""
    await require_pi(session, scope, "quotes.write")
    state = request.app.state
    made = await brain_docs.draft_offer(
        session,
        scope,
        build_llm_manager(state.settings, state.http, state.sessions),
        conversation_id,
    )
    if made is None:
        raise BusinessRuleViolation(
            "NOTHING_TO_DRAFT", "No offer was accepted in this chat, or it is drafted"
        )
    await session.commit()
    return {"solution": _view(made[0]), "quote": _view(made[1])}


@router.get("/{doc_id}/pdf")
async def staff_pdf(doc_id: UUID, scope: Scope, session: Session) -> Response:
    """The PDF a reviewer checks: the stored one once approved, otherwise a fresh preview."""
    await require_pi(session, scope, "sales.read")
    doc = await _doc(session, scope, doc_id)
    data, name = await brain_docs.render_pdf(session, scope, doc)
    if doc.file_id is not None:
        from app.modules.customers.models import CustomerFile

        stored = await WorkspaceRepository(session, CustomerFile, scope).find(
            CustomerFile.id == doc.file_id
        )
        if stored is not None:
            data = await files.file_bytes(session, stored)
    return _pdf(data, name)


def _pdf(data: bytes, name: str) -> Response:
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote_name(name)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@public_router.get("/{token}/{name}")
async def public_pdf(token: str, name: str, request: Request, session: Session) -> Response:
    """The approved PDF a customer opens from WhatsApp. Only an approved or sent document is
    served, and only the stored file: what was approved is exactly what they read."""
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pi-brain-doc", f"{token[:16]}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    doc_id = brain_docs.read_doc_token(request.app.state.settings, token)
    if doc_id is None:
        raise HTTPException(status_code=404)
    from app.modules.customers.models import CustomerFile

    doc = await session.scalar(select(PiBrainDocument).where(PiBrainDocument.id == doc_id))
    if doc is None or doc.status not in ("approved", "sent") or doc.file_id is None:
        raise HTTPException(status_code=404)
    file_id = doc.file_id
    if name.endswith("-EN.pdf"):  # R-DOC-07: the English copy kept at approval
        try:
            file_id = UUID(str(doc.content.get("en_file_id")))
        except ValueError:
            raise HTTPException(status_code=404) from None
    stored = await session.scalar(select(CustomerFile).where(CustomerFile.id == file_id))
    if stored is None:
        raise HTTPException(status_code=404)
    return _pdf(
        await files.file_bytes(session, stored),
        name if name.endswith("-EN.pdf") else f"{doc.ref}.pdf",
    )
