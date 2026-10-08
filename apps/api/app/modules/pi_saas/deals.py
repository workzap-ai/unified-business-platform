"""The deal flow: from a WhatsApp enquiry to a paid invoice, with pi doing the sending.

    interest (chat) → lead "new" → brief confirmed: "qualified"            (pi already)
    → proposal from the brief; the team sets prices and approves it
    → send: lead "proposal"; pi posts the proposal link on WhatsApp
    → the customer opens it and taps Accept / Ask for changes / Not now
    → accepted: lead "won", order confirmed, invoice issued, payment link sent
    → paid: a thank-you message (and the lead stays "won")

Prices only ever come from a quote a person priced and approved; pi never makes one up.

Reaching the customer on WhatsApp follows Meta's rules:
- the customer wrote in the last 24 hours → the link goes in their chat now;
- otherwise, if the business set an approved template with no variables ("Your document
  is ready, reply to see it") → that goes out, and the link follows the moment they
  reply (``release_waiting``, called for every inbound message);
- otherwise the team gets a ready-made link and a wa.me share to send it themselves.
A business can start a deal from just a WhatsApp number, with no chat yet.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote as url_quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.auth.crypto import digest, new_token
from app.modules.billing.models import Invoice, InvoiceLine
from app.modules.billing.service import BillingService
from app.modules.business_settings.capabilities import business_permissions
from app.modules.customers.models import Customer
from app.modules.customers.service import CustomerService
from app.modules.notifications.service import notify
from app.modules.orders.models import Order, OrderLine
from app.modules.orders.service import OrderService
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.tools.base import PI_RUNTIME_PERMISSIONS
from app.modules.pi_saas import customer_payments as cp
from app.modules.pi_saas import pay_links
from app.modules.pi_saas.campaigns import production_connection
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.deal_models import PiDealSettings, PiDocument
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.quotes.schemas import QuoteCreate, QuoteLineInput
from app.modules.quotes.service import QuoteService
from app.modules.sales.models import SalesLead
from app.modules.sales.schemas import LeadCreate
from app.modules.sales.service import SalesService
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

LINK_DAYS = 30
WINDOW = timedelta(hours=24)
# Lead stages in order; moving forward walks through the allowed steps.
_FORWARD = ("new", "qualified", "proposal", "won")


# ---- Basics ---------------------------------------------------------------------------


async def deal_settings(session: AsyncSession, scope: WorkspaceScope) -> PiDealSettings:
    repo = WorkspaceRepository(session, PiDealSettings, scope)
    row = await repo.find()
    if row is None:
        row = await repo.add(repo.new())
    return row


def settings_view(row: PiDealSettings) -> dict[str, Any]:
    return {
        "auto_order": row.auto_order,
        "auto_invoice": row.auto_invoice,
        "auto_payment_request": row.auto_payment_request,
        "thank_you_on_paid": row.thank_you_on_paid,
        "payment_method": row.payment_method,
        "template_name": row.template_name,
        "template_language": row.template_language,
    }


def document_url(settings: Settings, token: str) -> str:
    return f"{settings.pi_app_public_url.rstrip('/')}/d/{token}"


def pay_url(settings: Settings, token: str) -> str:
    return f"{settings.pi_app_public_url.rstrip('/')}/pay/request/{token}"


def money(amount: Decimal, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _contact(customer: Customer) -> str | None:
    raw = customer.whatsapp_id or customer.phone or ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits if 8 <= len(digits) <= 15 else None


def share_link(customer: Customer, text: str) -> str | None:
    """wa.me link the team can tap to send the message from their own WhatsApp."""
    contact = _contact(customer)
    return f"https://wa.me/{contact}?text={url_quote(text)}" if contact else None


async def system_scope_for(
    session: AsyncSession, tenant_id: UUID, environment_id: UUID
) -> WorkspaceScope:
    """The pi actor for one business: what a customer's tap on Accept may do."""
    permissions = await business_permissions(
        session, tenant_id, environment_id, PI_RUNTIME_PERMISSIONS
    )
    return WorkspaceScope.system(tenant_id, environment_id, permissions, "PI")


async def _business_name(session: AsyncSession, scope: WorkspaceScope) -> str:
    name = await session.scalar(select(Tenant.name).where(Tenant.id == scope.tenant_id))
    return name or "us"


async def move_lead(session: AsyncSession, scope: WorkspaceScope, lead_id: UUID, to: str) -> None:
    """Walk the lead to ``to`` through the allowed stages; never backwards past won."""
    lead = await WorkspaceRepository(session, SalesLead, scope).find(SalesLead.id == lead_id)
    if lead is None or lead.stage == to:
        return
    sales = SalesService(session, scope)
    if to == "lost":
        if lead.stage in {"new", "qualified", "proposal"}:
            await sales.move(lead.id, "lost")
        return
    if to == "qualified" and lead.stage == "proposal":
        await sales.move(lead.id, "qualified")
        return
    if lead.stage == "lost":
        await sales.move(lead.id, "new")
    if lead.stage not in _FORWARD or to not in _FORWARD:
        return
    for stage in _FORWARD[_FORWARD.index(lead.stage) + 1 : _FORWARD.index(to) + 1]:
        await sales.move(lead.id, stage)


# ---- Reaching the customer ------------------------------------------------------------


async def new_document(
    session: AsyncSession,
    scope: WorkspaceScope,
    kind: str,
    customer_id: UUID,
    *,
    quote_id: UUID | None = None,
    invoice_id: UUID | None = None,
    lead_id: UUID | None = None,
) -> tuple[PiDocument, str]:
    token = new_token()
    repo = WorkspaceRepository(session, PiDocument, scope)
    doc = await repo.add(
        repo.new(
            kind=kind,
            customer_id=customer_id,
            quote_id=quote_id,
            invoice_id=invoice_id,
            lead_id=lead_id,
            token_hash=digest(token),
            expires_at=datetime.now(UTC) + timedelta(days=LINK_DAYS),
        )
    )
    return doc, token


async def _conversation(
    session: AsyncSession, scope: WorkspaceScope, customer: Customer, contact: str
) -> PiConversation | None:
    connection = await production_connection(session, scope)
    if connection is None:
        return None
    repo = WorkspaceRepository(session, PiConversation, scope)
    found = await repo.find(
        PiConversation.connection_id == connection.id,
        PiConversation.contact_wa_id == contact,
        PiConversation.status == "open",
    )
    if found is not None:
        return found
    # Outbound first: the business starts the chat with a number it was given.
    return await repo.add(
        repo.new(
            customer_id=customer.id,
            connection_id=connection.id,
            contact_wa_id=contact,
            last_message_at=datetime.now(UTC),
        )
    )


async def _queue(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    body: str,
    key: str,
    media: dict[str, Any] | None = None,
) -> str:
    repo = WorkspaceRepository(session, PiMessage, scope)
    existing = await repo.find(PiMessage.idempotency_key == key)
    if existing is not None:
        return str(existing.id)
    message = await repo.add(
        repo.new(
            conversation_id=conversation.id,
            direction="outbound",
            sender_type="system",
            body=body,
            media=media or {},
            status="queued",
            idempotency_key=key,
        )
    )
    conversation.last_message_at = datetime.now(UTC)
    if body:
        conversation.last_message_preview = body[:200]
    return str(message.id)


async def deliver(
    session: AsyncSession, scope: WorkspaceScope, doc: PiDocument, customer: Customer, text: str
) -> list[str]:
    """Send ``text`` to the customer the best way WhatsApp allows; returns message ids
    to enqueue. Sets ``doc.delivery``."""
    doc.message_text = text
    contact = _contact(customer)
    conversation = await _conversation(session, scope, customer, contact) if contact else None
    if conversation is None:
        doc.delivery = "manual"
        return []
    doc.conversation_id = conversation.id
    now = datetime.now(UTC)
    if conversation.last_inbound_at and conversation.last_inbound_at > now - WINDOW:
        doc.delivery = "sent"
        return [await _queue(session, scope, conversation, text, f"pi-doc:{doc.id}")]
    settings = await deal_settings(session, scope)
    if settings.template_name and settings.template_language:
        doc.delivery = "waiting"
        template = {"name": settings.template_name, "language": settings.template_language}
        return [
            await _queue(
                session,
                scope,
                conversation,
                "",
                f"pi-doc-notice:{doc.id}",
                {"document_notice": {"template": template, "document_id": str(doc.id)}},
            )
        ]
    doc.delivery = "manual"
    return []


async def release_waiting(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage
) -> list[str]:
    """The customer wrote, so the 24-hour window is open: send every proposal or
    invoice link that was waiting for them. Returns message ids to enqueue."""
    if message.direction != "inbound":
        return []
    conversation = await WorkspaceRepository(session, PiConversation, scope).find(
        PiConversation.id == message.conversation_id
    )
    if conversation is None:
        return []
    waiting = list(
        await session.scalars(
            WorkspaceRepository(session, PiDocument, scope)
            .select()
            .where(
                PiDocument.customer_id == conversation.customer_id,
                PiDocument.delivery == "waiting",
                PiDocument.expires_at > datetime.now(UTC),
            )
            .order_by(PiDocument.created_at)
            .with_for_update()
        )
    )
    ids = []
    for doc in waiting:
        doc.delivery, doc.conversation_id = "sent", conversation.id
        ids.append(await _queue(session, scope, conversation, doc.message_text, f"pi-doc:{doc.id}"))
    return ids


def delivery_view(doc: PiDocument, customer: Customer, url: str) -> dict[str, Any]:
    return {
        "document_id": doc.id,
        "delivery": doc.delivery,
        "link": url,
        "share": share_link(customer, doc.message_text),
        "message": doc.message_text,
    }


# ---- Proposals ------------------------------------------------------------------------


async def proposal_from_lead(session: AsyncSession, scope: WorkspaceScope, lead_id: UUID) -> Quote:
    """A draft proposal with one line per project in the confirmed brief, at zero: the
    team sets the prices (pi never invents one)."""
    lead = await WorkspaceRepository(session, SalesLead, scope).get(lead_id)
    if lead.customer_id is None:
        raise BusinessRuleViolation("LEAD_HAS_NO_CUSTOMER", "Link this lead to a customer first")
    brief: dict[str, Any] = {}
    if lead.conversation_id:
        conversation = await WorkspaceRepository(session, PiConversation, scope).find(
            PiConversation.id == lead.conversation_id
        )
        brief = dict(conversation.service_brief or {}) if conversation else {}
    lines: list[QuoteLineInput] = []
    for project in brief.get("projects") or []:
        if not isinstance(project, dict) or project.get("status") == "dropped":
            continue
        title = str(project.get("title") or project.get("service") or "").strip()
        details = str(project.get("details") or "").strip()
        if title:
            text = f"{title}: {details}" if details else title
            lines.append(
                QuoteLineInput(description=text[:300], quantity=Decimal(1), unit_price=Decimal(0))
            )
    if not lines:
        requirements = lead.requirements or {}
        title = str(requirements.get("service") or lead.title or "Service").strip()
        scope_text = str(requirements.get("scope") or "").strip()
        text = f"{title}: {scope_text}" if scope_text else title
        lines.append(
            QuoteLineInput(description=text[:300], quantity=Decimal(1), unit_price=Decimal(0))
        )
    quote = await QuoteService(session, scope).create(
        QuoteCreate(
            customer_id=lead.customer_id,
            lead_id=lead.id,
            notes=(lead.notes or "")[:4000],
            lines=lines[:100],
        ),
        source="manual",
    )
    return quote


async def send_proposal(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, quote_id: UUID
) -> tuple[dict[str, Any], list[str]]:
    """Send (or resend) a priced, approved proposal. Draft → submitted first; one that
    still needs a manager's approval stops there with a clear message."""
    service = QuoteService(session, scope)
    quote = await WorkspaceRepository(session, Quote, scope).get(quote_id)
    if quote.total <= 0:
        raise BusinessRuleViolation("QUOTE_NOT_PRICED", "Add prices before sending the proposal")
    if quote.status == "draft":
        quote = await service.transition(quote.id, "submit")
    if quote.status == "pending_approval":
        raise BusinessRuleViolation(
            "QUOTE_NEEDS_APPROVAL", "A manager needs to approve this proposal first"
        )
    if quote.status == "approved":
        quote = await service.transition(quote.id, "send")
    if quote.status != "sent":
        raise BusinessRuleViolation("QUOTE_NOT_SENDABLE", "This proposal can't be sent now")
    if quote.lead_id:
        await move_lead(session, scope, quote.lead_id, "proposal")
    customer = await WorkspaceRepository(session, Customer, scope).get(quote.customer_id)
    doc, token = await new_document(
        session, scope, "proposal", customer.id, quote_id=quote.id, lead_id=quote.lead_id
    )
    url = document_url(settings, token)
    business = await _business_name(session, scope)
    first = "" if customer.name.startswith("WhatsApp") else customer.name.split(" ")[0]
    text = (
        f"Hi{(' ' + first) if first else ''}, here is your proposal {quote.number} from "
        f"{business}.\nTotal: {money(quote.total, quote.currency)}\n"
        f"Valid until {quote.valid_until:%d %b %Y}.\nView and accept: {url}"
    )
    ids = await deliver(session, scope, doc, customer, text)
    return delivery_view(doc, customer, url), ids


# ---- What the customer's tap does -----------------------------------------------------


async def document_for(session: AsyncSession, token: str, *, lock: bool = False) -> PiDocument:
    query = select(PiDocument).where(PiDocument.token_hash == digest(token))
    if lock:
        query = query.with_for_update()
    doc = await session.scalar(query)
    if doc is None or doc.expires_at < datetime.now(UTC):
        raise ResourceNotFound
    return doc


async def public_view(session: AsyncSession, settings: Settings, doc: PiDocument) -> dict[str, Any]:
    """What the customer sees: the business, the lines, totals and what they can do."""
    scope = await system_scope_for(session, doc.tenant_id, doc.environment_id)
    customer = await WorkspaceRepository(session, Customer, scope).get(doc.customer_id)
    business = await _business_name(session, scope)
    base: dict[str, Any] = {
        "kind": doc.kind,
        "business": business,
        "customer": customer.name,
        "response": doc.response,
        "responded_at": doc.responded_at,
    }
    if doc.kind == "proposal" and doc.quote_id:
        quote = await WorkspaceRepository(session, Quote, scope).get(doc.quote_id)
        lines = await session.scalars(
            WorkspaceRepository(session, QuoteLine, scope)
            .select()
            .where(QuoteLine.quote_id == quote.id)
            .order_by(QuoteLine.position)
        )
        return {
            **base,
            "number": quote.number,
            "status": quote.status,
            "currency": quote.currency,
            "lines": [_line(x) for x in lines],
            "subtotal": str(quote.subtotal),
            "discount_total": str(quote.discount_total),
            "tax_total": str(quote.tax_total),
            "total": str(quote.total),
            "valid_until": quote.valid_until,
            "notes": quote.notes,
            "can_respond": quote.status == "sent"
            and doc.response is None
            and quote.valid_until >= date.today(),
        }
    if doc.invoice_id is None:
        raise ResourceNotFound
    invoice = await WorkspaceRepository(session, Invoice, scope).get(doc.invoice_id)
    invoice_lines = await session.scalars(
        WorkspaceRepository(session, InvoiceLine, scope)
        .select()
        .where(InvoiceLine.invoice_id == invoice.id)
        .order_by(InvoiceLine.position)
    )
    return {
        **base,
        "number": invoice.number,
        "status": invoice.status,
        "currency": invoice.currency,
        "lines": [_line(x) for x in invoice_lines],
        "subtotal": str(invoice.subtotal),
        "discount_total": str(invoice.discount_total),
        "tax_total": str(invoice.tax_total),
        "total": str(invoice.total),
        "amount_paid": str(invoice.amount_paid),
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "notes": invoice.notes,
        "pay_link": await _open_pay_link(session, scope, settings, invoice),
        "can_respond": False,
    }


def _line(line: Any) -> dict[str, Any]:
    return {
        "description": line.description,
        "quantity": str(line.quantity),
        "unit_price": str(line.unit_price),
        "discount": str(line.discount),
        "line_total": str(line.line_total),
    }


async def _open_pay_link(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, invoice: Invoice
) -> str | None:
    if invoice.status not in {"issued", "partially_paid"}:
        return None
    row = await session.scalar(
        WorkspaceRepository(session, PiPaymentRequest, scope)
        .select()
        .where(
            PiPaymentRequest.invoice_id == invoice.id,
            PiPaymentRequest.status.in_(["open", "awaiting_verification"]),
        )
        .order_by(PiPaymentRequest.created_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    if row.method == "stripe" and row.checkout_url:
        return row.checkout_url
    return pay_url(settings, pay_links.issue(row))


async def respond(
    session: AsyncSession, settings: Settings, token: str, action: str, note: str
) -> tuple[dict[str, Any], list[str]]:
    doc = await document_for(session, token, lock=True)
    if doc.kind != "proposal" or doc.quote_id is None:
        raise BusinessRuleViolation("NOT_A_PROPOSAL", "Only a proposal can be answered")
    if doc.response is not None:
        raise BusinessRuleViolation("ALREADY_ANSWERED", "You already answered this proposal")
    scope = await system_scope_for(session, doc.tenant_id, doc.environment_id)
    quotes = QuoteService(session, scope)
    quote = await WorkspaceRepository(session, Quote, scope).get(doc.quote_id)
    if quote.status != "sent":
        raise BusinessRuleViolation(
            "PROPOSAL_CLOSED", "This proposal can't be answered any more. Ask for a new one."
        )
    doc.response, doc.response_note, doc.responded_at = action, note[:2000], datetime.now(UTC)
    ids: list[str] = []
    if action == "accepted":
        await quotes.transition(quote.id, "accept")
        if quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "won")
        ids = await after_accept(session, scope, settings, quote)
        title = f"Proposal {quote.number} accepted"
    elif action == "changes":
        await quotes.transition(quote.id, "reject")
        if quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "qualified")
        title = f"Changes asked on proposal {quote.number}"
    else:
        await quotes.transition(quote.id, "reject")
        if quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "lost")
        title = f"Proposal {quote.number} declined"
    await notify(
        session,
        scope,
        "pi.deal",
        title,
        note[:500] or "The customer answered on the proposal page.",
        link=f"/quotes/{quote.id}",
        permission="quotes.read",
        severity="info" if action == "accepted" else "warning",
        dedupe_key=f"pi-deal:{doc.id}",
    )
    return await public_view(session, settings, doc), ids


def _method(row: Any, preferred: str, stripe_ready: bool) -> str | None:
    methods = cp.enabled_methods(row, stripe_ready)
    if preferred != "auto":
        return preferred if preferred in methods else None
    for method in ("stripe", "bank_transfer", "mobile_wallet", "cash"):
        if method in methods:
            return method
    return None


async def invoice_message(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    invoice: Invoice,
    *,
    intro: str,
) -> tuple[PiDocument, str, Customer]:
    """The invoice document plus a payment request (when payments are set up) and the
    WhatsApp text that carries both links."""
    customer = await WorkspaceRepository(session, Customer, scope).get(invoice.customer_id)
    doc, token = await new_document(session, scope, "invoice", customer.id, invoice_id=invoice.id)
    lines = [
        intro,
        f"Invoice {invoice.number}: {money(invoice.total - invoice.amount_paid, invoice.currency)}",
    ]
    deals = await deal_settings(session, scope)
    pay_row = await cp.settings_for(session, scope)
    stripe_ready = await cp.stripe_connected(session, scope)
    method = _method(pay_row, deals.payment_method, stripe_ready)
    if method is not None and invoice.status in {"issued", "partially_paid"}:
        request = await cp.create_request(
            session,
            scope,
            invoice_id=invoice.id,
            method=method,
            idempotency_key=f"deal-invoice:{invoice.id}:{method}",
            customer_id=customer.id,
        )
        lines.append(cp.customer_message(request))
        if request.method != "stripe":
            lines.append(f"Pay online: {pay_url(settings, pay_links.issue(request))}")
    lines.append(f"Invoice: {document_url(settings, token)}")
    return doc, "\n".join(lines), customer


async def after_accept(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, quote: Quote
) -> list[str]:
    """Accepted: confirm the order, issue the invoice and send the payment link, each
    step only if the business switched it on."""
    deals = await deal_settings(session, scope)
    if not deals.auto_order:
        return []
    orders = OrderService(session, scope)
    order = await orders.create_from_quote(quote.id)
    if order.status == "draft":
        order = await orders.transition(order.id, "confirm")
    invoice = await session.scalar(
        WorkspaceRepository(session, Invoice, scope)
        .select()
        .where(Invoice.order_id == order.id, Invoice.status != "void")
    )
    if invoice is None and deals.auto_invoice:
        lines = list(
            await session.scalars(
                WorkspaceRepository(session, OrderLine, scope)
                .select()
                .where(OrderLine.order_id == order.id)
            )
        )
        invoice = await BillingService(session, scope).create_from_order(order, lines)
    if invoice is None or not deals.auto_payment_request:
        return []
    doc, text, customer = await invoice_message(
        session,
        scope,
        settings,
        invoice,
        intro=f"Thank you! Your order {order.number} is confirmed.",
    )
    return await deliver(session, scope, doc, customer, text)


async def send_invoice(
    session: AsyncSession, scope: WorkspaceScope, settings: Settings, invoice_id: UUID
) -> tuple[dict[str, Any], list[str]]:
    invoice = await WorkspaceRepository(session, Invoice, scope).get(invoice_id)
    if invoice.status == "draft":
        invoice = await BillingService(session, scope).act(invoice.id, "issue")
    if invoice.status not in {"issued", "partially_paid"}:
        raise BusinessRuleViolation(
            "INVOICE_NOT_OPEN", "Only an issued, unpaid invoice can be sent"
        )
    business = await _business_name(session, scope)
    doc, text, customer = await invoice_message(
        session, scope, settings, invoice, intro=f"Here is your invoice from {business}."
    )
    ids = await deliver(session, scope, doc, customer, text)
    url = text.rsplit("Invoice: ", 1)[-1]
    return delivery_view(doc, customer, url), ids


async def after_paid(session: AsyncSession, scope: WorkspaceScope, invoice: Invoice) -> list[str]:
    """Paid in full: a thank-you on WhatsApp, and the deal's lead marked won."""
    order = (
        await WorkspaceRepository(session, Order, scope).find(Order.id == invoice.order_id)
        if invoice.order_id
        else None
    )
    if order is not None and order.quote_id:
        quote = await WorkspaceRepository(session, Quote, scope).find(Quote.id == order.quote_id)
        if quote is not None and quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "won")
    deals = await deal_settings(session, scope)
    if not deals.thank_you_on_paid:
        return []
    customer = await WorkspaceRepository(session, Customer, scope).find(
        Customer.id == invoice.customer_id
    )
    contact = _contact(customer) if customer else None
    conversation = (
        await _conversation(session, scope, customer, contact) if customer and contact else None
    )
    if conversation is None or not conversation.last_inbound_at:
        return []
    if conversation.last_inbound_at < datetime.now(UTC) - WINDOW:
        return []  # Outside the window a thank-you isn't worth a template.
    text = f"Payment received for invoice {invoice.number}. Thank you!"
    return [await _queue(session, scope, conversation, text, f"pi-paid:{invoice.id}")]


# ---- Starting from a number -----------------------------------------------------------


async def start_from_number(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    phone: str,
    name: str,
    title: str,
    notes: str,
) -> tuple[Customer, SalesLead]:
    """A deal with someone who hasn't messaged yet: their customer record (found or
    created by WhatsApp number) and a new lead."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not 8 <= len(digits) <= 15:
        raise BusinessRuleViolation("PHONE_INVALID", "Enter the WhatsApp number with country code")
    customers = CustomerService(session, scope)
    customer, created = await customers.resolve_whatsapp(digits, name or None)
    if created:
        customer.source = "manual"
    lead = await SalesService(session, scope).create(
        LeadCreate(
            title=(title or f"Deal with {customer.name}")[:200],
            customer_id=customer.id,
            notes=notes[:4000],
        )
    )
    return customer, lead
