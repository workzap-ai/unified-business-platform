"""Send an invoice's payment link to the customer in one step: WhatsApp and email.

The pay link comes from the business's own payment setup, in this order:
1. pi customer payments (card through Stripe, bank transfer, wallet, cash), which the
   deal flow's invoice message already includes;
2. otherwise the workspace's Stripe integration (Settings → Integrations), a Stripe
   Checkout link for the open balance.

A draft invoice is issued first (the team approving it is what sends it). WhatsApp
follows the deal flow's rules (24-hour window, template, or a share link for the team).
Email goes to the customer's saved address through the email integration.
"""

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.networks import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations import business
from app.integrations.email import EMAIL_KEYS
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.workflow_models import IntegrationOperation
from app.modules.access.dependencies import Scope, Session
from app.modules.billing.models import Invoice
from app.modules.billing.service import BillingService
from app.modules.customers.models import Customer
from app.modules.pi.models import PiMessage
from app.modules.pi_saas import customer_payments as cp
from app.modules.pi_saas import deals
from app.modules.pi_saas.deal_models import PiDocument
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

PAY_LINE = re.compile(r"https?://(?:checkout\.stripe\.com/\S+|\S+/pay/request/\S+)", re.IGNORECASE)


def pay_link_in(text: str) -> str | None:
    found = PAY_LINE.search(text or "")
    return found.group(0) if found else None


async def stripe_link(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    scope: WorkspaceScope,
    invoice: Invoice,
) -> str | None:
    """A Stripe Checkout link from the workspace's Stripe integration, or None when it
    isn't connected or can't make one right now."""
    if not await cp.stripe_connected(session, scope):
        return None
    try:
        view = await business.checkout(session, settings, http, scope, invoice.id)
    except (BusinessRuleViolation, IntegrationError):
        return None
    url = (view.get("output") or {}).get("url")
    return str(url) if url else None


async def email_link(
    session: AsyncSession,
    scope: WorkspaceScope,
    invoice: Invoice,
    pay_url: str | None,
    invoice_url: str | None,
) -> IntegrationOperation:
    """Queue the customer's email: amount, due date, the pay link and the invoice page."""
    customer = await WorkspaceRepository(session, Customer, scope).get(invoice.customer_id)
    try:
        address = str(TypeAdapter(EmailStr).validate_python(customer.email))
    except ValueError:
        raise BusinessRuleViolation(
            "CUSTOMER_EMAIL_REQUIRED", "Add the customer's email address to email the link"
        ) from None
    connection = await business.connection_for(session, scope, EMAIL_KEYS)
    tenant = await session.get(Tenant, scope.tenant_id)
    balance = invoice.total - invoice.amount_paid
    lines = [
        f"Invoice {invoice.number}: {deals.money(balance, invoice.currency)} due "
        f"{invoice.due_date or 'on receipt'}."
    ]
    if pay_url:
        lines.append(f"Pay online: {pay_url}")
    if invoice_url:
        lines.append(f"View the invoice: {invoice_url}")
    return await business.operation(
        session,
        scope,
        connection,
        "notification",
        f"invoice-pay-link:{invoice.id}:{invoice.amount_paid}:{pay_url or ''}",
        "invoice",
        invoice.id,
        {
            "template": "customer_notice",
            "name": customer.name,
            "business": tenant.name if tenant else "",
            "recipient": address,
            "title": f"Payment for invoice {invoice.number}",
            "message": " ".join(lines),
        },
    )


async def send(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    scope: WorkspaceScope,
    invoice_id: UUID,
    *,
    whatsapp: bool,
    email: bool,
) -> tuple[dict[str, Any], list[str], IntegrationOperation | None]:
    """Issue (if draft) and send the payment link. Returns the result for the team, the
    WhatsApp message ids to enqueue and the email operation to deliver."""
    scope.require("billing.write")
    invoice = await WorkspaceRepository(session, Invoice, scope).get(invoice_id)
    if invoice.status == "draft":
        invoice = await BillingService(session, scope).act(invoice.id, "issue")
    if invoice.status not in {"issued", "partially_paid"}:
        raise BusinessRuleViolation("INVOICE_NOT_OPEN", "This invoice has nothing left to pay")

    result: dict[str, Any] = {"whatsapp": None, "email": None, "email_error": None}
    ids: list[str] = []
    invoice_url: str | None = None
    pay_url: str | None = None
    if whatsapp:
        view, ids = await deals.send_invoice(session, scope, settings, invoice.id)
        invoice_url, pay_url = str(view["link"]), pay_link_in(str(view["message"]))
        if pay_url is None:
            # pi's own payment methods are off: fall back to the Stripe integration.
            pay_url = await stripe_link(session, settings, http, scope, invoice)
            if pay_url:
                extra = f"\nPay by card: {pay_url}"
                doc = await WorkspaceRepository(session, PiDocument, scope).get(
                    UUID(str(view["document_id"]))
                )
                doc.message_text = f"{doc.message_text}{extra}"
                for message_id in ids:
                    message = await WorkspaceRepository(session, PiMessage, scope).find(
                        PiMessage.id == UUID(message_id)
                    )
                    if message is not None and message.status == "queued" and message.body:
                        message.body = f"{message.body}{extra}"
                customer = await WorkspaceRepository(session, Customer, scope).get(
                    invoice.customer_id
                )
                view = deals.delivery_view(doc, customer, invoice_url)
        result["whatsapp"] = view
    elif email:
        pay_url = await stripe_link(session, settings, http, scope, invoice)
    result["pay_link"] = pay_url

    operation: IntegrationOperation | None = None
    if email:
        try:
            operation = await email_link(session, scope, invoice, pay_url, invoice_url)
            result["email"] = "queued"
        except BusinessRuleViolation as error:
            result["email_error"] = error.message
    return result, ids, operation


# ---- Route ----------------------------------------------------------------------------

router = APIRouter(prefix="/billing/invoices", tags=["billing-payment-link"])


class SendLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whatsapp: bool = True
    email: bool = True


@router.post("/{invoice_id}/payment-link/send")
async def send_payment_link(
    invoice_id: UUID, data: SendLink, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """'Send payment link' on the invoice page: WhatsApp (when pi is on) and email."""
    from app.modules.pi.service import require_pi

    whatsapp = data.whatsapp
    if whatsapp:
        try:
            await require_pi(session, scope, "billing.write")
        except BusinessRuleViolation:
            whatsapp = False  # No pi here: email only.
    if not whatsapp and not data.email:
        raise BusinessRuleViolation("NOTHING_TO_SEND", "Choose WhatsApp or email")
    settings = request.app.state.settings
    http = OutboundClient(
        settings,
        request.app.state.http,
        resolver=getattr(request.app.state, "integration_resolver", None),
    )
    result, ids, operation = await send(
        session, settings, http, scope, invoice_id, whatsapp=whatsapp, email=data.email
    )
    await session.commit()
    queue = request.app.state.queue
    for message_id in ids:
        await queue.enqueue("send_pi_message", message_id, job_id=f"send:{message_id}")
    if operation is not None:
        await queue.enqueue(
            "deliver_integration_operation", str(operation.id), job_id=f"operation:{operation.id}"
        )
    return result
