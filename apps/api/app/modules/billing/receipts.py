"""Receipts: a PDF bill for every payment, kept on record and sent to the customer.

    payment recorded (manual, bank/cash verified, Stripe)  →  receipt RCPT-000001 (PDF)
    →  saved in the customer's files (Attachments, the invoice's Receipts, Activity)
    →  sent: a WhatsApp link to its page (24-hour rules) and an email with the link

What it shows is the business's choice (Deal automation → Receipts): the customer's
details, the project the payment is for (title, scope, features and timeline from the
brief), the line items and a footer note. A partial payment shows the balance left;
the last payment says PAID IN FULL. Never stops the payment being recorded.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.access.dependencies import Session, require
from app.modules.billing.models import Invoice, InvoiceLine, Payment
from app.modules.customers.models import Customer, CustomerFile
from app.modules.tenants.models import Tenant
from app.shared.pdf import MARGIN, WIDTH, Document, wrap
from app.shared.scope import WorkspaceScope
from app.shared.sequences import next_number
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

INK = (0.1, 0.1, 0.12)
MUTED = (0.42, 0.44, 0.48)
BRAND = (0.05, 0.37, 0.31)
METHODS = {
    "cash": "Cash",
    "bank_transfer": "Bank transfer",
    "card": "Card",
    "mobile_wallet": "Mobile wallet",
    "other": "Other",
}


def money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


async def project_for(
    session: AsyncSession, scope: WorkspaceScope, invoice: Invoice
) -> dict[str, str] | None:
    """The deal this invoice belongs to: its lead's title and brief."""
    from app.modules.quotes.models import Quote
    from app.modules.sales.models import SalesLead

    if invoice.order_id is None:
        return None
    lead_id = await session.scalar(
        WorkspaceRepository(session, Quote, scope)
        .select()
        .with_only_columns(Quote.lead_id)
        .where(Quote.order_id == invoice.order_id)
        .limit(1)
    )
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
        "audience": str(needs.get("audience") or ""),
        "timeline": str(needs.get("target_date") or ""),
    }


def render(
    *,
    business: str,
    number: str,
    invoice: Invoice,
    payment: Payment,
    lines: list[InvoiceLine],
    customer: Customer,
    project: dict[str, str] | None,
    options: dict[str, Any],
) -> bytes:
    doc = Document(title=f"Receipt {number}")
    right = WIDTH - MARGIN
    paid_in_full = invoice.status == "paid"
    doc.box(0, 0, WIDTH, 96, BRAND)
    doc.text(MARGIN, 46, business, 20, True, (1, 1, 1))
    doc.text(MARGIN, 68, "Payment receipt", 11, False, (0.85, 0.94, 0.9))
    doc.text(right, 46, number, 14, True, (1, 1, 1), "right")
    doc.text(right, 68, f"{payment.received_on:%d %b %Y}", 11, False, (0.85, 0.94, 0.9), "right")

    y = 132.0
    doc.text(MARGIN, y, "Amount received", 10, False, MUTED)
    doc.text(MARGIN, y + 24, money(payment.amount, payment.currency), 22, True, INK)
    if paid_in_full:
        doc.box(right - 110, y - 10, 110, 26, (0.86, 0.96, 0.91))
        doc.text(right - 55, y + 7, "PAID IN FULL", 10, True, BRAND, "center")
    y += 52
    facts = [
        ("Invoice", invoice.number),
        ("Payment", payment.number),
        ("Method", METHODS.get(payment.method, payment.method)),
        ("Reference", payment.reference or "-"),
        ("Invoice total", money(invoice.total, invoice.currency)),
        ("Paid so far", money(invoice.amount_paid, invoice.currency)),
        ("Balance", money(invoice.total - invoice.amount_paid, invoice.currency)),
    ]
    for index, (label, value) in enumerate(facts):
        column = index % 2
        row_y = y + (index // 2) * 22
        x = MARGIN + column * 260
        doc.text(x, row_y, label, 9, False, MUTED)
        doc.text(x + 90, row_y, value, 10, label == "Balance", INK)
    y += ((len(facts) + 1) // 2) * 22 + 10
    doc.line(MARGIN, y, right, y)
    y += 26

    if options["customer_details"]:
        doc.text(MARGIN, y, "Received from", 9, True, MUTED)
        y += 16
        for value in (customer.name, customer.phone or "", customer.email or ""):
            if value:
                doc.text(MARGIN, y, value, 10)
                y += 14
        y += 12

    if options["project_details"] and project:
        doc.text(MARGIN, y, "Your project", 9, True, MUTED)
        y += 16
        doc.text(MARGIN, y, project["title"], 12, True)
        y += 16
        for label, key in (
            ("Service", "service"),
            ("Scope", "scope"),
            ("For", "audience"),
            ("Timeline", "timeline"),
        ):
            if not project.get(key) or (key == "service" and project[key] == project["title"]):
                continue
            wrapped = wrap(project[key], 10, right - MARGIN - 70)[:6]
            doc.text(MARGIN, y, label, 9, False, MUTED)
            for line in wrapped:
                doc.text(MARGIN + 70, y, line, 10)
                y += 14
            y += 4
        y += 10

    if options["line_items"] and lines:
        doc.box(MARGIN, y - 12, right - MARGIN, 20, (0.95, 0.96, 0.97))
        doc.text(MARGIN + 8, y + 2, "Item", 9, True, MUTED)
        doc.text(right - 160, y + 2, "Qty", 9, True, MUTED, "right")
        doc.text(right - 8, y + 2, "Amount", 9, True, MUTED, "right")
        y += 24
        for item in lines[:30]:
            for i, part in enumerate(wrap(item.description, 10, right - MARGIN - 210)[:3]):
                doc.text(MARGIN + 8, y + i * 13, part, 10)
            doc.text(right - 160, y, f"{item.quantity.normalize():f}", 10, align="right")
            doc.text(right - 8, y, money(item.line_total, invoice.currency), 10, align="right")
            y += 13 * min(3, len(wrap(item.description, 10, right - MARGIN - 210))) + 8
            if y > 720:
                break
        doc.line(MARGIN, y, right, y)
        y += 18
        doc.text(right - 120, y, "Total", 10, True, MUTED, "right")
        doc.text(right - 8, y, money(invoice.total, invoice.currency), 11, True, align="right")
        y += 24

    footer_y = 790.0
    if options["footer"]:
        for i, line in enumerate(wrap(options["footer"], 9, right - MARGIN)[:3]):
            doc.text(MARGIN, footer_y - 30 + i * 12, line, 9, False, MUTED)
    doc.line(MARGIN, footer_y - 40, right, footer_y - 40)
    doc.text(MARGIN, footer_y, f"Thank you for your payment. Receipt {number}.", 9, False, MUTED)
    doc.text(right, footer_y, f"Issued {datetime.now(UTC):%d %b %Y}", 9, False, MUTED, "right")
    return doc.render()


async def issue(
    session: AsyncSession,
    scope: WorkspaceScope,
    invoice: Invoice,
    payment: Payment,
    settings: Settings | None = None,
) -> tuple[CustomerFile | None, list[str]]:
    """Make, keep and send the receipt for one payment. Returns the saved file and the
    WhatsApp message ids to enqueue. Once per payment."""
    from app.modules.customers import files
    from app.modules.customers.service import log_activity
    from app.modules.pi_saas import deals

    if invoice.customer_id is None:
        return None, []
    found = await WorkspaceRepository(session, CustomerFile, scope).find(
        CustomerFile.ref_type == "payment", CustomerFile.ref_id == payment.id
    )
    if found is not None:
        return found, []
    options = await receipt_options(session, scope)
    if not options["enabled"]:
        return None, []
    customer = await WorkspaceRepository(session, Customer, scope).get(invoice.customer_id)
    lines = list(
        await session.scalars(
            WorkspaceRepository(session, InvoiceLine, scope)
            .select()
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.position)
        )
    )
    business = await session.scalar(select(Tenant.name).where(Tenant.id == scope.tenant_id))
    number = await next_number(session, scope, "receipt")
    pdf = render(
        business=business or "Receipt",
        number=number,
        invoice=invoice,
        payment=payment,
        lines=lines,
        customer=customer,
        project=await project_for(session, scope, invoice),
        options=options,
    )
    saved = await files.save(
        session,
        scope,
        customer.id,
        pdf,
        f"{number} {invoice.number}",
        "receipt",
        ref_type="payment",
        ref_id=payment.id,
    )
    await log_activity(
        session,
        scope,
        customer.id,
        "payment.receipt",
        f"Receipt {number} for {invoice.number}: {money(payment.amount, payment.currency)}",
        "invoice",
        invoice.id,
    )
    ids: list[str] = []
    if options["whatsapp"] or options["email"]:
        app_settings = settings or get_settings()
        doc, token = await deals.new_document(
            session, scope, "receipt", customer.id, invoice_id=invoice.id
        )
        doc.file_id = saved.id
        url = deals.document_url(app_settings, token)
        language = await deals.customer_language(session, scope, customer.id)
        text = receipt_message(language, number, invoice, payment, url)
        if options["whatsapp"]:
            ids = await deals.deliver(session, scope, doc, customer, text)
        else:
            doc.message_text, doc.delivery = text, "manual"
        if options["email"]:
            await _email(session, scope, customer, number, invoice, payment, url)
    return saved, ids


def receipt_message(
    language: str, number: str, invoice: Invoice, payment: Payment, url: str
) -> str:
    amount = money(payment.amount, payment.currency)
    full = invoice.status == "paid"
    if language == "roman_ur":
        head = f"Shukriya! Aap ki payment {amount} mil gayi hai" + (
            " aur invoice poori ada ho gayi hai." if full else "."
        )
        rest = (
            ""
            if full
            else (f"\nBaqi raqam: {money(invoice.total - invoice.amount_paid, invoice.currency)}")
        )
        return f"{head}{rest}\nRaseed {number} ({invoice.number}): {url}"
    head = f"Thank you! We received your payment of {amount}" + (
        f" and invoice {invoice.number} is paid in full." if full else f" for {invoice.number}."
    )
    rest = (
        ""
        if full
        else (f"\nBalance left: {money(invoice.total - invoice.amount_paid, invoice.currency)}")
    )
    return f"{head}{rest}\nYour receipt {number}: {url}"


async def _email(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer: Customer,
    number: str,
    invoice: Invoice,
    payment: Payment,
    url: str,
) -> None:
    """Best effort: no email address or no email provider simply skips it."""
    from pydantic import TypeAdapter
    from pydantic.networks import EmailStr

    from app.integrations import business
    from app.integrations.email import EMAIL_KEYS
    from app.shared.errors import BusinessRuleViolation

    try:
        address = str(TypeAdapter(EmailStr).validate_python(customer.email))
        connection = await business.connection_for(session, scope, EMAIL_KEYS)
    except (ValueError, BusinessRuleViolation):
        return
    tenant = await session.get(Tenant, scope.tenant_id)
    await business.operation(
        session,
        scope,
        connection,
        "notification",
        f"receipt:{payment.id}",
        "invoice",
        invoice.id,
        {
            "template": "customer_notice",
            "name": customer.name,
            "business": tenant.name if tenant else "",
            "recipient": address,
            "title": f"Receipt {number}",
            "message": (
                f"Thank you for your payment of {money(payment.amount, payment.currency)} "
                f"for invoice {invoice.number}. Your receipt {number}: {url}"
            ),
        },
    )


async def receipt_options(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any]:
    from app.modules.pi_saas.deals import deal_settings

    row = await deal_settings(session, scope)
    return {
        "enabled": row.auto_receipt,
        "whatsapp": row.receipt_whatsapp,
        "email": row.receipt_email,
        "customer_details": row.receipt_customer_details,
        "project_details": row.receipt_project_details,
        "line_items": row.receipt_line_items,
        "footer": row.receipt_footer,
    }


# ---- API: an invoice's receipts ---------------------------------------------------------

router = APIRouter(prefix="/billing/invoices", tags=["billing-receipts"])
ReadBilling = Annotated[WorkspaceScope, Depends(require("billing.read"))]


@router.get("/{invoice_id}/receipts")
async def invoice_receipts(
    invoice_id: UUID, scope: ReadBilling, session: Session
) -> list[dict[str, Any]]:
    """The receipts made for this invoice's payments (newest first)."""
    from app.modules.customers import files

    await WorkspaceRepository(session, Invoice, scope).get(invoice_id)
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
    return [files.view(row) for row in rows]
