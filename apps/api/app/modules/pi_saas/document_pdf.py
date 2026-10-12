"""A proposal or invoice as a PDF on the business's letterhead (the "Download PDF" on the
customer's document page).

    business header  →  number, date, valid until / due  →  prepared for, the project
    →  lines with qty and amount  →  subtotal, discount, tax, total  →  notes
    →  bank details (when bank transfer is on)  →  "verify on <WhatsApp number>" footer

Bank details live only in this PDF, never in chat. Reading only: nothing is written.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Invoice, InvoiceLine
from app.modules.customers.models import Customer
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi_saas.customer_payment_models import PiCustomerPaymentSettings
from app.modules.pi_saas.deal_models import PiDocument
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.sales.models import SalesLead
from app.modules.tenants.models import Tenant
from app.shared.errors import ResourceNotFound
from app.shared.pdf import MARGIN, WIDTH, Document, wrap
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

INK = (0.1, 0.1, 0.12)
MUTED = (0.42, 0.44, 0.48)
BRAND = (0.05, 0.37, 0.31)
LIGHT = (0.85, 0.94, 0.9)
BOTTOM = 740.0


def money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _day(value: date | datetime | None) -> str:
    return f"{value:%d %b %Y}" if value else "-"


def render_document(
    *,
    kind: str,
    business: str,
    number: str,
    issued: date | datetime | None,
    until: date | None,
    customer: str,
    project: dict[str, str] | None,
    lines: list[Any],
    currency: str,
    subtotal: Decimal,
    discount: Decimal,
    tax: Decimal,
    total: Decimal,
    notes: str,
    banks: list[dict[str, Any]],
    phone: str | None,
) -> bytes:
    """Draw a proposal (``kind="proposal"``) or an invoice. ``lines`` need description,
    quantity and line_total; ``banks`` are the business's bank accounts (or [])."""
    label = "Proposal" if kind == "proposal" else "Invoice"
    doc = Document(title=f"{label} {number}")
    right = WIDTH - MARGIN
    doc.box(0, 0, WIDTH, 96, BRAND)
    doc.text(MARGIN, 46, business, 20, True, (1, 1, 1))
    doc.text(MARGIN, 68, label, 11, False, LIGHT)
    doc.text(right, 46, number, 14, True, (1, 1, 1), "right")
    doc.text(right, 68, _day(issued), 11, False, LIGHT, "right")

    y = 132.0
    doc.text(MARGIN, y, "Total", 10, False, MUTED)
    doc.text(MARGIN, y + 24, money(total, currency), 22, True, INK)
    y += 52
    facts = [
        (label, number),
        ("Date", _day(issued)),
        ("Valid until" if kind == "proposal" else "Due date", _day(until)),
        ("Prepared for", customer),
    ]
    for index, (name, value) in enumerate(facts):
        row_y = y + (index // 2) * 22
        x = MARGIN + (index % 2) * 260
        doc.text(x, row_y, name, 9, False, MUTED)
        doc.text(x + 80, row_y, wrap(value, 10, 170)[0], 10, False, INK)
    y += ((len(facts) + 1) // 2) * 22 + 10
    doc.line(MARGIN, y, right, y)
    y += 26

    def room(y: float, need: float) -> float:
        if y + need <= BOTTOM:
            return y
        doc.new_page()
        return MARGIN + 12

    if project:
        doc.text(MARGIN, y, "The project", 9, True, MUTED)
        y += 16
        doc.text(MARGIN, y, project["title"], 12, True)
        y += 16
        for name, key in (("Service", "service"), ("Scope", "scope")):
            if not project.get(key) or (key == "service" and project[key] == project["title"]):
                continue
            doc.text(MARGIN, y, name, 9, False, MUTED)
            for line in wrap(project[key], 10, right - MARGIN - 70)[:6]:
                doc.text(MARGIN + 70, y, line, 10)
                y += 14
            y += 4
        y += 10

    y = room(y, 60)
    doc.box(MARGIN, y - 12, right - MARGIN, 20, (0.95, 0.96, 0.97))
    doc.text(MARGIN + 8, y + 2, "Item", 9, True, MUTED)
    doc.text(right - 160, y + 2, "Qty", 9, True, MUTED, "right")
    doc.text(right - 8, y + 2, "Amount", 9, True, MUTED, "right")
    y += 24
    for item in lines:
        parts = wrap(item.description, 10, right - MARGIN - 210)[:3]
        y = room(y, 13 * len(parts) + 8)
        for i, part in enumerate(parts):
            doc.text(MARGIN + 8, y + i * 13, part, 10)
        doc.text(right - 160, y, f"{Decimal(item.quantity).normalize():f}", 10, align="right")
        doc.text(right - 8, y, money(item.line_total, currency), 10, align="right")
        y += 13 * len(parts) + 8
    doc.line(MARGIN, y, right, y)
    y += 18
    sums = [("Subtotal", subtotal)]
    if discount:
        sums.append(("Discount", -discount))
    if tax:
        sums.append(("Tax", tax))
    sums.append(("Total", total))
    y = room(y, 18 * len(sums))
    for name, amount in sums:
        strong = name == "Total"
        doc.text(right - 120, y, name, 10, strong, MUTED, "right")
        doc.text(right - 8, y, money(amount, currency), 11 if strong else 10, strong, align="right")
        y += 18
    y += 10

    if notes.strip():
        wrapped = wrap(notes.strip(), 10, right - MARGIN)[:12]
        y = room(y, 16 + 14 * len(wrapped))
        doc.text(MARGIN, y, "Notes", 9, True, MUTED)
        y += 16
        for line in wrapped:
            doc.text(MARGIN, y, line, 10)
            y += 14
        y += 12

    if banks:
        y = room(y, 30 + 70 * min(len(banks), 2))
        doc.text(MARGIN, y, "Bank details", 9, True, MUTED)
        y += 18
        for account in banks:
            rows = [
                ("Bank", account.get("bank", "")),
                ("Account title", account.get("account_title", "")),
                ("Account no.", account.get("account_number", "")),
                ("IBAN", account.get("iban", "")),
                ("Branch", account.get("branch", "")),
            ]
            rows = [(n, str(v)) for n, v in rows if v]
            y = room(y, 14 * len(rows) + 10)
            for name, value in rows:
                doc.text(MARGIN, y, name, 9, False, MUTED)
                doc.text(MARGIN + 90, y, value, 10, name == "IBAN")
                y += 14
            y += 10

    footer_y = 790.0
    doc.line(MARGIN, footer_y - 40, right, footer_y - 40)
    footer = "Bank details are only in this PDF."
    if phone:
        footer += f" Before paying, verify them on {phone}."
    footer += " We never ask for payment details in chat."
    for i, line in enumerate(wrap(footer, 9, right - MARGIN)[:2]):
        doc.text(MARGIN, footer_y - 26 + i * 12, line, 9, False, MUTED)
    doc.text(MARGIN, footer_y, f"{label} {number}", 9, False, MUTED)
    doc.text(right, footer_y, f"Issued {datetime.now(UTC):%d %b %Y}", 9, False, MUTED, "right")
    return doc.render()


async def _project(
    session: AsyncSession, scope: WorkspaceScope, lead_id: Any
) -> dict[str, str] | None:
    if lead_id is None:
        return None
    lead = await WorkspaceRepository(session, SalesLead, scope).find(SalesLead.id == lead_id)
    if lead is None:
        return None
    needs = lead.requirements or {}
    return {
        "title": lead.title,
        "service": str(needs.get("service") or ""),
        "scope": str(needs.get("scope") or ""),
    }


async def for_document(
    session: AsyncSession, scope: WorkspaceScope, doc: PiDocument
) -> tuple[bytes, str]:
    """The PDF of a proposal or invoice link and its file name ("Proposal QUO-000016.pdf")."""
    customer = await WorkspaceRepository(session, Customer, scope).get(doc.customer_id)
    business = await session.scalar(select(Tenant.name).where(Tenant.id == scope.tenant_id))
    payments = await WorkspaceRepository(session, PiCustomerPaymentSettings, scope).find()
    banks = list(payments.bank_accounts or []) if payments and payments.bank_enabled else []
    phone = await session.scalar(
        select(WhatsAppConnection.display_phone_number)
        .where(
            WhatsAppConnection.tenant_id == scope.tenant_id,
            WhatsAppConnection.environment_id == scope.environment_id,
            WhatsAppConnection.status == "active",
        )
        .limit(1)
    )
    common: dict[str, Any] = {
        "business": business or "Business",
        "customer": customer.name,
        "banks": banks,
        "phone": phone or None,
    }
    if doc.kind == "proposal" and doc.quote_id:
        quote = await WorkspaceRepository(session, Quote, scope).get(doc.quote_id)
        lines = await session.scalars(
            WorkspaceRepository(session, QuoteLine, scope)
            .select()
            .where(QuoteLine.quote_id == quote.id)
            .order_by(QuoteLine.position)
        )
        pdf = render_document(
            kind="proposal",
            number=quote.number,
            issued=quote.created_at,
            until=quote.valid_until,
            project=await _project(session, scope, quote.lead_id or doc.lead_id),
            lines=list(lines),
            currency=quote.currency,
            subtotal=quote.subtotal,
            discount=quote.discount_total,
            tax=quote.tax_total,
            total=quote.total,
            notes=quote.notes,
            **common,
        )
        return pdf, f"Proposal {quote.number}.pdf"
    if doc.kind != "invoice" or doc.invoice_id is None:
        raise ResourceNotFound
    from app.modules.billing.receipts import project_for

    invoice = await WorkspaceRepository(session, Invoice, scope).get(doc.invoice_id)
    lines = await session.scalars(
        WorkspaceRepository(session, InvoiceLine, scope)
        .select()
        .where(InvoiceLine.invoice_id == invoice.id)
        .order_by(InvoiceLine.position)
    )
    project = await _project(session, scope, doc.lead_id) or await project_for(
        session, scope, invoice
    )
    pdf = render_document(
        kind="invoice",
        number=invoice.number,
        issued=invoice.issue_date or invoice.created_at,
        until=invoice.due_date,
        project=project,
        lines=list(lines),
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        discount=invoice.discount_total,
        tax=invoice.tax_total,
        total=invoice.total,
        notes=invoice.notes,
        **common,
    )
    return pdf, f"Invoice {invoice.number}.pdf"
