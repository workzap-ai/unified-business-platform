"""What a paying customer asked for and what they bought, project by project.

    GET /customers/{id}/solution

Only deals whose invoice is paid (or part paid) are listed. Everything comes from saved
records: pi's notes on the lead (the problem, the goal, the must-haves), the proposal
(its lines and the scope pi wrote into its notes), the invoice with its payments and
receipts, the order's work steps (dated from the customer's timeline) and the feedback
the customer gave in the chat. An unpaid customer gets an empty list.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.billing.models import Invoice, Payment
from app.modules.customers.models import Customer, CustomerActivity, CustomerFile
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation
from app.modules.pi_saas.customer_overview import _same, project_notes
from app.modules.pi_saas.deal_routes import _guide
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.sales.models import SalesLead
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/customers", tags=["customer-solution"])

PAID = ("paid", "partially_paid")
# The proposal's notes, as pi's writer lays them out (proposal_writer.to_quote).
SECTIONS = ("Scope", "Deliverables", "Timeline", "Not included", "Next steps")
WORK = {"processing": 1, "shipped": 2, "delivered": 2}


def proposal_sections(notes: str) -> dict[str, Any]:
    """The written proposal in parts: an intro and titled sections of points."""
    intro: list[str] = []
    sections: list[dict[str, Any]] = []
    for block in (notes or "").split("\n\n"):
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0] in SECTIONS:
            points = [line.lstrip("•-* ").strip() for line in lines[1:]]
            sections.append({"title": lines[0], "points": [p for p in points if p][:20]})
        elif not sections:
            intro.append(" ".join(lines))
    return {"intro": "\n\n".join(intro)[:1500], "sections": sections}


async def _work_dates(session: Any, scope: Any, customer_id: UUID) -> dict[UUID, dict[str, Any]]:
    """When each order's work started and was delivered, from the customer's timeline
    ("Order SO-1: confirmed → processing"). The earliest change to a status counts."""
    rows = await session.execute(
        WorkspaceRepository(session, CustomerActivity, scope)
        .select()
        .with_only_columns(
            CustomerActivity.ref_id, CustomerActivity.summary, CustomerActivity.created_at
        )
        .where(
            CustomerActivity.customer_id == customer_id,
            CustomerActivity.ref_type == "order",
            CustomerActivity.summary.like("%→%"),
        )
        .order_by(CustomerActivity.created_at)
    )
    dates: dict[UUID, dict[str, Any]] = {}
    for ref_id, summary, at in rows:
        target = summary.rsplit("→", 1)[1].strip()
        if ref_id is not None and target in WORK:
            key = "work_started_at" if target == "processing" else "delivered_at"
            dates.setdefault(ref_id, {}).setdefault(key, at)
    return dates


async def _receipts(session: Any, scope: Any, invoice_id: UUID) -> list[dict[str, Any]]:
    """The receipt PDFs made for this invoice's payments (as billing.receipts lists them)."""
    payment_ids = select(Payment.id).where(
        Payment.invoice_id == invoice_id,
        Payment.tenant_id == scope.tenant_id,
        Payment.environment_id == scope.environment_id,
    )
    rows = await session.scalars(
        WorkspaceRepository(session, CustomerFile, scope)
        .select()
        .where(CustomerFile.ref_type == "payment", CustomerFile.ref_id.in_(payment_ids))
        .order_by(CustomerFile.created_at.desc())
    )
    return [{"file_id": r.id, "name": r.name, "created_at": r.created_at} for r in rows]


def _delivery(order: Order, dates: dict[str, Any], paid_at: Any) -> dict[str, Any]:
    stage = WORK.get(order.status, 0)
    shipped = order.status == "shipped"
    return {
        "order_id": order.id,
        "order_number": order.number,
        "order_status": order.status,
        "steps": [
            {"key": "paid", "label": "Paid", "done": True, "at": paid_at},
            {
                "key": "work",
                "label": "Work started",
                "done": stage >= 1,
                "at": dates.get("work_started_at"),
            },
            {
                "key": "delivered",
                "label": "Shipped" if shipped else "Delivered",
                "done": stage >= 2,
                "at": dates.get("delivered_at"),
            },
        ],
    }


@router.get("/{customer_id}/solution")
async def solution(customer_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("customers.read")
    await WorkspaceRepository(session, Customer, scope).get(customer_id)
    leads = list(
        await session.scalars(
            WorkspaceRepository(session, SalesLead, scope)
            .select()
            .where(SalesLead.customer_id == customer_id)
            .order_by(SalesLead.created_at.desc())
            .limit(50)
        )
    )
    feedback: list[dict[str, Any]] = []
    for brief in await session.scalars(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .with_only_columns(PiConversation.service_brief)
        .where(PiConversation.customer_id == customer_id)
    ):
        feedback += [f for f in (brief or {}).get("feedback") or [] if isinstance(f, dict)]
    work_dates: dict[UUID, dict[str, Any]] | None = None
    projects: list[dict[str, Any]] = []
    for lead in leads:
        # The same lookups as the deal journey: newest quote → its order → live invoice.
        quote = await session.scalar(
            WorkspaceRepository(session, Quote, scope)
            .select()
            .where(Quote.lead_id == lead.id)
            .order_by(Quote.created_at.desc())
            .limit(1)
        )
        if quote is None or quote.order_id is None:
            continue
        order = await WorkspaceRepository(session, Order, scope).find(Order.id == quote.order_id)
        if order is None:
            continue
        invoice = await session.scalar(
            WorkspaceRepository(session, Invoice, scope)
            .select()
            .where(Invoice.order_id == order.id, Invoice.status.in_(PAID))
            .limit(1)
        )
        if invoice is None:
            continue
        if work_dates is None:
            work_dates = await _work_dates(session, scope, customer_id)
        lines = await session.scalars(
            WorkspaceRepository(session, QuoteLine, scope)
            .select()
            .where(QuoteLine.quote_id == quote.id)
            .order_by(QuoteLine.position)
        )
        paid_at = await session.scalar(
            WorkspaceRepository(session, Payment, scope)
            .select()
            .with_only_columns(Payment.created_at)
            .where(Payment.invoice_id == invoice.id)
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
        requirements = lead.requirements or {}
        projects.append(
            {
                "lead_id": lead.id,
                "title": lead.title,
                "service": str(requirements.get("service") or "")[:120],
                "scope": str(requirements.get("scope") or "")[:300],
                "notes": project_notes(requirements),
                "bought": {
                    "quote_id": quote.id,
                    "quote_number": quote.number,
                    "currency": quote.currency,
                    "total": str(quote.total),
                    "lines": [
                        {
                            "description": line.description,
                            "quantity": str(line.quantity),
                            "line_total": str(line.line_total),
                        }
                        for line in lines
                    ],
                    "proposal": proposal_sections(quote.notes),
                },
                "payment": {
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.number,
                    "status": invoice.status,
                    "currency": invoice.currency,
                    "total": str(invoice.total),
                    "amount_paid": str(invoice.amount_paid),
                    "balance": str(max(invoice.total - invoice.amount_paid, Decimal(0))),
                    "paid_at": paid_at,
                    "receipts": await _receipts(session, scope, invoice.id),
                },
                "delivery": _delivery(order, work_dates.get(order.id, {}), paid_at),
                "feedback": [
                    {k: str(f.get(k) or "") for k in ("project", "mood", "words", "at")}
                    for f in feedback
                    if _same(lead.title, str(f.get("project") or ""))
                ][-5:],
                # Settings only matter before the invoice; every deal here has one.
                "next": _guide(lead, quote, None, invoice, {}, None, order),
            }
        )
    return {"projects": projects}
