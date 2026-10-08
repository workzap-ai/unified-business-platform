"""Deal flow API. ``router`` is mounted for Owner OS (/api/v1/pi/deals) and the pi app
(/api/v1/pi-app/pi/deals); ``public_router`` serves the customer's proposal or invoice
page in the pi app (/api/v1/pi-app/docs/{token}). See ``deals`` for the flow."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_

from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.customers.models import Customer
from app.modules.pi.service import require_pi
from app.modules.pi_saas import deals
from app.modules.pi_saas.deal_models import PAYMENT_DEFAULTS, PiDocument
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi/deals", tags=["pi-deals"])
public_router = APIRouter(prefix="/docs", tags=["pi-documents"])


async def _enqueue(request: Request, ids: list[str]) -> None:
    for message_id in ids:
        await request.app.state.queue.enqueue(
            "send_pi_message", message_id, job_id=f"send:{message_id}"
        )


# ---- Settings -------------------------------------------------------------------------


class DealSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    auto_order: bool
    auto_invoice: bool
    auto_payment_request: bool
    thank_you_on_paid: bool
    payment_method: Literal["auto", "stripe", "bank_transfer", "mobile_wallet", "cash"]
    template_name: str = Field("", max_length=512, pattern=r"^[a-z0-9_]*$")
    template_language: str = Field("", max_length=16, pattern=r"^([a-z]{2,3}(_[A-Z]{2})?)?$")


@router.get("/settings")
async def get_settings(scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "sales.read")
    row = await deals.deal_settings(session, scope)
    await session.commit()
    return {**deals.settings_view(row), "payment_methods": list(PAYMENT_DEFAULTS)}


@router.put("/settings")
async def put_settings(data: DealSettingsInput, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "sales.write")
    if bool(data.template_name) != bool(data.template_language):
        raise BusinessRuleViolation(
            "TEMPLATE_INCOMPLETE", "Give both the template name and its language"
        )
    row = await deals.deal_settings(session, scope)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    await record(
        session,
        "pi.deal_settings_updated",
        scope=scope,
        entity_type="pi_deal_settings",
        entity_id=row.id,
        details=data.model_dump(),
    )
    await session.commit()
    return deals.settings_view(row)


# ---- The team's actions ---------------------------------------------------------------


@router.post("/leads/{lead_id}/proposal", status_code=201)
async def proposal_from_lead(lead_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "quotes.write")
    quote = await deals.proposal_from_lead(session, scope, lead_id)
    await session.commit()
    return {"quote_id": quote.id, "number": quote.number}


@router.post("/quotes/{quote_id}/send")
async def send_proposal(
    quote_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "quotes.write")
    view, ids = await deals.send_proposal(session, scope, request.app.state.settings, quote_id)
    await session.commit()
    await _enqueue(request, ids)
    return view


@router.post("/invoices/{invoice_id}/send")
async def send_invoice(
    invoice_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "billing.write")
    view, ids = await deals.send_invoice(session, scope, request.app.state.settings, invoice_id)
    await session.commit()
    await _enqueue(request, ids)
    return view


class StartDeal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    phone: str = Field(min_length=6, max_length=32)
    name: str = Field("", max_length=160)
    title: str = Field("", max_length=200)
    notes: str = Field("", max_length=4000)


@router.post("/start", status_code=201)
async def start_deal(data: StartDeal, scope: Scope, session: Session) -> dict[str, Any]:
    """A deal with someone who hasn't messaged yet, from their WhatsApp number."""
    await require_pi(session, scope, "sales.write")
    scope.require("customers.write")
    customer, lead = await deals.start_from_number(
        session, scope, phone=data.phone, name=data.name, title=data.title, notes=data.notes
    )
    await session.commit()
    return {"customer_id": customer.id, "lead_id": lead.id}


@router.get("/documents")
async def documents(
    scope: Scope,
    session: Session,
    quote_id: UUID | None = None,
    invoice_id: UUID | None = None,
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "sales.read")
    query = WorkspaceRepository(session, PiDocument, scope).select()
    if quote_id:
        query = query.where(PiDocument.quote_id == quote_id)
    if invoice_id:
        query = query.where(PiDocument.invoice_id == invoice_id)
    rows = await session.scalars(query.order_by(PiDocument.created_at.desc()).limit(20))
    return [_document(d) for d in rows]


def _document(d: PiDocument) -> dict[str, Any]:
    return {
        "id": d.id,
        "kind": d.kind,
        "delivery": d.delivery,
        "viewed_at": d.viewed_at,
        "response": d.response,
        "response_note": d.response_note,
        "responded_at": d.responded_at,
        "created_at": d.created_at,
    }


@router.get("/board")
async def board(scope: Scope, session: Session) -> dict[str, Any]:
    """Every open deal, plus the last 30 days of won and lost, with where each one is:
    the latest proposal, its invoice and payment, and what the customer did."""
    await require_pi(session, scope, "sales.read")
    since = datetime.now(UTC) - timedelta(days=30)
    leads = list(
        await session.scalars(
            WorkspaceRepository(session, SalesLead, scope)
            .select()
            .where(
                or_(
                    SalesLead.stage.in_(["new", "qualified", "proposal"]),
                    SalesLead.updated_at >= since,
                )
            )
            .order_by(SalesLead.updated_at.desc())
            .limit(300)
        )
    )
    customer_ids = {lead.customer_id for lead in leads if lead.customer_id}
    customers = {
        c.id: c
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_(list(customer_ids) or [None]))
        )
    }
    quotes: dict[UUID, Quote] = {}
    for q in await session.scalars(
        WorkspaceRepository(session, Quote, scope)
        .select()
        .where(Quote.lead_id.in_([lead.id for lead in leads] or [None]))
        .order_by(Quote.created_at)
    ):
        if q.lead_id:
            quotes[q.lead_id] = q  # the newest wins
    order_ids = [q.order_id for q in quotes.values() if q.order_id]
    invoices = {
        i.order_id: i
        for i in await session.scalars(
            WorkspaceRepository(session, Invoice, scope)
            .select()
            .where(Invoice.order_id.in_(order_ids or [None]), Invoice.status != "void")
        )
    }
    docs: dict[UUID, PiDocument] = {}
    for d in await session.scalars(
        WorkspaceRepository(session, PiDocument, scope)
        .select()
        .where(PiDocument.quote_id.in_([q.id for q in quotes.values()] or [None]))
        .order_by(PiDocument.created_at)
    ):
        if d.quote_id:
            docs[d.quote_id] = d
    items: list[dict[str, Any]] = []
    for lead in leads:
        customer = customers.get(lead.customer_id) if lead.customer_id else None
        quote = quotes.get(lead.id)
        invoice = invoices.get(quote.order_id) if quote and quote.order_id else None
        doc = docs.get(quote.id) if quote else None
        items.append(
            {
                "id": lead.id,
                "title": lead.title,
                "stage": lead.stage,
                "source": lead.source,
                "updated_at": lead.updated_at,
                "conversation_id": lead.conversation_id,
                "customer": {"id": customer.id, "name": customer.name, "phone": customer.phone}
                if customer
                else None,
                "proposal": {
                    "id": quote.id,
                    "number": quote.number,
                    "status": quote.status,
                    "total": str(quote.total),
                    "currency": quote.currency,
                    "delivery": doc.delivery if doc else None,
                    "viewed": bool(doc and doc.viewed_at),
                    "response": doc.response if doc else None,
                }
                if quote
                else None,
                "invoice": {
                    "id": invoice.id,
                    "number": invoice.number,
                    "status": invoice.status,
                    "total": str(invoice.total),
                    "amount_paid": str(invoice.amount_paid),
                    "currency": invoice.currency,
                }
                if invoice
                else None,
                "next": _next_step(lead.stage, quote, invoice),
            }
        )
    counts: dict[str, int] = {}
    for lead in leads:
        counts[lead.stage] = counts.get(lead.stage, 0) + 1
    return {"items": items, "counts": counts}


def _next_step(stage: str, quote: Quote | None, invoice: Invoice | None) -> str:
    """Plain words for the team: what this deal needs next."""
    if stage == "lost":
        return "Closed: not this time"
    if invoice is not None:
        if invoice.status == "paid":
            return "Paid: deliver the work"
        return "Waiting for payment"
    if quote is None:
        return "Collect the brief" if stage == "new" else "Prepare a proposal"
    return {
        "draft": "Add prices and send the proposal",
        "pending_approval": "Approve the proposal",
        "approved": "Send the proposal",
        "sent": "Waiting for the customer's answer",
        "accepted": "Accepted: confirm the order",
        "rejected": "Changes asked: send a revised proposal",
        "expired": "Expired: send a fresh proposal",
        "cancelled": "Prepare a proposal",
    }.get(quote.status, "Prepare a proposal")


# ---- The customer's page --------------------------------------------------------------


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["accepted", "changes", "rejected"]
    note: str = Field("", max_length=2000)


@public_router.get("/{token}")
async def public_document(token: str, request: Request, session: Session) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pi-doc-view", f"{token[:16]}:{ip}", 60, 3600):
        raise HTTPException(status_code=429)
    doc = await deals.document_for(session, token, lock=True)
    if doc.viewed_at is None:
        doc.viewed_at = datetime.now(UTC)
    view = await deals.public_view(session, request.app.state.settings, doc)
    await session.commit()
    return view


@public_router.post("/{token}/respond")
async def public_respond(
    token: str, data: Answer, request: Request, session: Session
) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pi-doc-respond", ip, 20, 3600):
        raise HTTPException(status_code=429)
    if data.action == "changes" and not data.note:
        raise BusinessRuleViolation("NOTE_REQUIRED", "Tell us what you'd like changed")
    view, ids = await deals.respond(
        session, request.app.state.settings, token, data.action, data.note
    )
    await session.commit()
    await _enqueue(request, ids)
    return view
