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

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote as url_quote
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.http import OutboundClient
from app.modules.auth.crypto import digest, new_token
from app.modules.billing.models import Invoice, InvoiceLine
from app.modules.billing.service import BillingService
from app.modules.business_settings.capabilities import business_permissions
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.models import CatalogProduct, CatalogVariant
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

logger = logging.getLogger(__name__)
LINK_DAYS = 30
HOW = {
    "pending": "prepared",
    "sent": "sent on WhatsApp",
    "waiting": "announced on WhatsApp; the link follows their reply",
    "manual": "ready to share by hand (no open WhatsApp chat)",
    "failed": "could not be sent",
}
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
        "auto_proposal": row.auto_proposal,
        "auto_followups": row.auto_followups,
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


# What pi sends with a document, in the customer's language (the chat's language; other
# languages get English, the links and amounts carry the meaning).
TEXTS: dict[str, dict[str, str]] = {
    "proposal": {
        "en": "Hi{hi}, here is your proposal {number} from {business}.\nTotal: {total}\n"
        "Valid until {until}.\nView and accept: {url}\n"
        "You can also reply here to accept it or to ask for changes.",
        "roman_ur": "Assalam o alaikum{hi}, {business} ki taraf se aap ka proposal {number}.\n"
        "Total: {total}\nValid: {until} tak.\nDekhein aur accept karein: {url}\n"
        "Aap yahin reply kar ke bhi accept kar sakte hain ya changes bata sakte hain.",
    },
    "accepted": {
        "en": "Thank you! Your order {number} is confirmed.",
        "roman_ur": "Shukriya! Aap ka order {number} confirm ho gaya hai.",
    },
    "invoice": {
        "en": "Here is your invoice from {business}.",
        "roman_ur": "{business} ki taraf se aap ki invoice.",
    },
    "paid": {
        "en": "Payment received for invoice {number}. Thank you!",
        "roman_ur": "Invoice {number} ki payment mil gayi hai. Shukriya!",
    },
}


def say(key: str, language: str, **values: str) -> str:
    texts = TEXTS[key]
    return texts.get(language, texts["en"]).format(**values)


async def customer_language(session: AsyncSession, scope: WorkspaceScope, customer_id: UUID) -> str:
    """The language of the customer's latest chat with pi ("en" when unknown)."""
    language = await session.scalar(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .with_only_columns(PiConversation.language)
        .where(PiConversation.customer_id == customer_id)
        .order_by(PiConversation.last_message_at.desc().nulls_last())
        .limit(1)
    )
    return str(language or "en")


async def note_lead(
    session: AsyncSession, scope: WorkspaceScope, lead_id: UUID | None, text: str
) -> None:
    if lead_id is None:
        return
    lead = await WorkspaceRepository(session, SalesLead, scope).find(SalesLead.id == lead_id)
    if lead is not None:
        add_note(lead, text)


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
    try:
        # A savepoint: this runs inside every inbound message's transaction, so a
        # database without the deal tables yet (migration pending) must never stop
        # customer messages from being saved and answered.
        async with session.begin_nested():
            return await _release_waiting(session, scope, message)
    except DBAPIError:
        logger.warning("deal_release_skipped", exc_info=True)
        return []


async def _release_waiting(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage
) -> list[str]:
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


async def write_proposal(
    session: AsyncSession, scope: WorkspaceScope, manager: Any, lead_id: UUID
) -> tuple[list[QuoteLineInput], str] | None:
    """pi's written proposal (lines + scope text) for the lead, or None to use the plain
    one. The model call happens with no row locks held; see ``proposal_writer``."""
    from app.modules.pi_saas import proposal_writer

    lead = await WorkspaceRepository(session, SalesLead, scope).get(lead_id)
    data = await proposal_writer.gather(session, scope, lead)
    await session.commit()
    draft = await proposal_writer.compose(manager, scope, data)
    if draft is None:
        return None
    lines, notes = proposal_writer.to_quote(draft, data)
    return (lines, notes) if lines else None


async def proposal_from_lead(
    session: AsyncSession,
    scope: WorkspaceScope,
    lead_id: UUID,
    written: tuple[list[QuoteLineInput], str] | None = None,
) -> Quote:
    """A draft proposal for the confirmed brief. ``written`` is pi's draft (lines and the
    scope text the customer sees); without it, one line per project. Prices only come
    from catalog options; other lines stay at zero for the team (pi never invents one)."""
    lead = await WorkspaceRepository(session, SalesLead, scope).get(lead_id)
    if lead.customer_id is None:
        raise BusinessRuleViolation("LEAD_HAS_NO_CUSTOMER", "Link this lead to a customer first")
    if written is not None:
        quote = await QuoteService(session, scope).create(
            QuoteCreate(
                customer_id=lead.customer_id,
                lead_id=lead.id,
                notes=written[1],
                lines=written[0][:100],
            ),
            source="manual",
        )
        if quote.total > 0:
            lead.estimated_value = quote.total
        return quote
    brief: dict[str, Any] = {}
    if lead.conversation_id:
        conversation = await WorkspaceRepository(session, PiConversation, scope).find(
            PiConversation.id == lead.conversation_id
        )
        brief = dict(conversation.service_brief or {}) if conversation else {}
    wanted: list[tuple[str, str]] = []
    for project in brief.get("projects") or []:
        if not isinstance(project, dict) or project.get("status") == "dropped":
            continue
        title = str(project.get("title") or project.get("service") or "").strip()
        details = str(project.get("details") or "").strip()
        if title:
            wanted.append((title, f"{title}: {details}" if details else title))
    if not wanted:
        requirements = lead.requirements or {}
        title = str(requirements.get("service") or lead.title or "Service").strip()
        scope_text = str(requirements.get("scope") or "").strip()
        wanted.append((title, f"{title}: {scope_text}" if scope_text else title))
    prices = await _catalog_prices(session, scope)
    lines: list[QuoteLineInput] = []
    for title, text in wanted:
        variant = _price_for(prices, title)
        if variant is not None:
            # The business's own catalog price: the only price pi may ever put in.
            lines.append(
                QuoteLineInput(variant_id=variant, description=text[:300], quantity=Decimal(1))
            )
        else:
            lines.append(
                QuoteLineInput(description=text[:300], quantity=Decimal(1), unit_price=Decimal(0))
            )
    # No notes: lead notes are internal and quote notes show on the customer's page.
    quote = await QuoteService(session, scope).create(
        QuoteCreate(
            customer_id=lead.customer_id,
            lead_id=lead.id,
            notes="",
            lines=lines[:100],
        ),
        source="manual",
    )
    if quote.total > 0:
        lead.estimated_value = quote.total
    return quote


async def _catalog_prices(session: AsyncSession, scope: WorkspaceScope) -> list[tuple[str, UUID]]:
    """(product name, variant id) for every offering with exactly one active price in
    the business's currency: the prices pi can put on a proposal by itself."""
    currency = (await get_settings_row(session, scope)).default_currency
    rows = await session.execute(
        select(CatalogProduct.name, CatalogVariant.id, CatalogVariant.product_id)
        .join(CatalogVariant, CatalogVariant.product_id == CatalogProduct.id)
        .where(
            CatalogProduct.tenant_id == scope.tenant_id,
            CatalogProduct.environment_id == scope.environment_id,
            CatalogProduct.status == "active",
            CatalogVariant.status == "active",
            CatalogVariant.currency == currency,
        )
    )
    by_product: dict[UUID, list[tuple[str, UUID]]] = {}
    for name, variant_id, product_id in rows:
        by_product.setdefault(product_id, []).append((name, variant_id))
    return [found[0] for found in by_product.values() if len(found) == 1]


def _price_for(prices: list[tuple[str, UUID]], title: str) -> UUID | None:
    """The catalog price for a project, when one offering's name clearly matches it."""
    wanted = title.casefold().strip()
    matches = [
        (len(name), variant)
        for name, variant in prices
        if len(name.strip()) >= 3
        and (name.casefold().strip() in wanted or wanted in name.casefold().strip())
    ]
    if not matches:
        return None
    matches.sort(reverse=True)
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        return None  # Two offerings fit equally well: a person picks.
    return matches[0][1]


def add_note(lead: SalesLead, text: str) -> None:
    """A dated line in the lead's notes, so the team sees what pi did and when."""
    line = f"• {datetime.now(UTC):%d %b %H:%M} UTC · pi: {text}"
    notes = f"{lead.notes.rstrip()}\n{line}" if lead.notes.strip() else line
    lead.notes = notes[-5000:]


# pi's own part of the lead notes: rewritten from the chat on every turn. The team writes
# anywhere outside it; deleting the whole block stops pi from writing it again.
NOTES_START = "── pi's notes (updated from the chat) ──"
NOTES_END = "── end of pi's notes ──"


def write_pi_notes(lead: SalesLead, body: str, *, written_before: bool) -> bool:
    """Put ``body`` in pi's block of the lead notes. Returns False when the team removed
    the block (pi leaves their notes alone from then on)."""
    body = body.strip()
    if not body:
        return written_before
    block = f"{NOTES_START}\n{body[:3000]}\n{NOTES_END}"
    notes = lead.notes or ""
    start, end = notes.find(NOTES_START), notes.find(NOTES_END)
    if start != -1 and end > start:
        lead.notes = (notes[:start] + block + notes[end + len(NOTES_END) :])[-5000:]
        return True
    if written_before:
        return False  # The team deleted pi's block: their notes, their call.
    lead.notes = f"{block}\n\n{notes.strip()}".strip()[-5000:]
    return True


# A quote that is still in play for a lead; a rejected one (changes asked) or a dead one
# makes room for a revised proposal.
OPEN_QUOTE = ("draft", "pending_approval", "approved", "sent", "accepted")


async def proposal_due(session: AsyncSession, scope: WorkspaceScope, lead_id: UUID) -> bool:
    """Should pi write a proposal for this lead now?"""
    if not (await deal_settings(session, scope)).auto_proposal:
        return False
    lead = await WorkspaceRepository(session, SalesLead, scope).find(SalesLead.id == lead_id)
    if lead is None or lead.customer_id is None or lead.stage in {"won", "lost"}:
        return False
    existing = await session.scalar(
        WorkspaceRepository(session, Quote, scope)
        .select()
        .where(Quote.lead_id == lead.id, Quote.status.in_(OPEN_QUOTE))
        .limit(1)
    )
    return existing is None


async def auto_proposal(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    lead_id: UUID,
    written: tuple[list[QuoteLineInput], str] | None = None,
) -> list[str]:
    """The customer confirmed the brief: make the proposal (pi's written draft when
    given) with catalog prices and send it on WhatsApp. When a line has no catalog price,
    the draft waits for the team (they get a notification). Never fails the
    conversation: errors only skip this step."""
    try:
        async with session.begin_nested():
            return await _auto_proposal(session, scope, settings, lead_id, written)
    except (DBAPIError, BusinessRuleViolation, ResourceNotFound):
        logger.warning("deal_auto_proposal_skipped", exc_info=True)
        return []


async def _auto_proposal(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    lead_id: UUID,
    written: tuple[list[QuoteLineInput], str] | None,
) -> list[str]:
    if not await proposal_due(session, scope, lead_id):
        return []
    lead = await WorkspaceRepository(session, SalesLead, scope).get(lead_id)
    revised = await session.scalar(
        WorkspaceRepository(session, Quote, scope)
        .select()
        .where(Quote.lead_id == lead.id, Quote.status == "rejected")
        .limit(1)
    )
    quote = await proposal_from_lead(session, scope, lead.id, written)
    if revised is not None:
        add_note(lead, f"revised proposal {quote.number} made after the requested changes")
    lines = list(
        await session.scalars(
            WorkspaceRepository(session, QuoteLine, scope)
            .select()
            .where(QuoteLine.quote_id == quote.id)
        )
    )
    priced = bool(lines) and all(line.unit_price > 0 for line in lines)
    if priced:
        try:
            async with session.begin_nested():
                _, ids = await send_proposal(session, scope, settings, quote.id)
        except BusinessRuleViolation as exc:
            if exc.code != "QUOTE_NEEDS_APPROVAL":
                raise
            add_note(lead, f"proposal {quote.number} made from catalog prices; needs approval")
            await notify(
                session,
                scope,
                "pi.deal",
                f"Approve proposal {quote.number}",
                "pi made it from the confirmed brief with your catalog prices. Approve it "
                "and pi sends it on WhatsApp.",
                link=f"/quotes/{quote.id}",
                permission="quotes.read",
                severity="info",
                dedupe_key=f"pi-auto-proposal:{quote.id}",
            )
            return []
        return ids
    add_note(lead, f"draft proposal {quote.number} made from the brief; add prices to send it")
    await notify(
        session,
        scope,
        "pi.deal",
        f"Price proposal {quote.number}",
        "The customer confirmed their brief. pi made the proposal; add the prices that "
        "aren't in your catalog and send it.",
        link=f"/quotes/{quote.id}/edit",
        permission="quotes.read",
        severity="info",
        dedupe_key=f"pi-auto-proposal:{quote.id}",
    )
    return []


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
    text = say(
        "proposal",
        await customer_language(session, scope, customer.id),
        hi=f" {first}" if first else "",
        number=quote.number,
        business=business,
        total=money(quote.total, quote.currency),
        until=f"{quote.valid_until:%d %b %Y}",
        url=url,
    )
    ids = await deliver(session, scope, doc, customer, text)
    await note_lead(
        session,
        scope,
        quote.lead_id,
        f"proposal {quote.number} ({money(quote.total, quote.currency)}) {HOW[doc.delivery]}",
    )
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
    session: AsyncSession,
    settings: Settings,
    token: str,
    action: str,
    note: str,
    *,
    http: OutboundClient | None = None,
) -> tuple[dict[str, Any], list[str]]:
    doc = await document_for(session, token, lock=True)
    scope = await system_scope_for(session, doc.tenant_id, doc.environment_id)
    ids = await answer(session, scope, settings, doc, action, note, via="page", http=http)
    return await public_view(session, settings, doc), ids


async def open_proposal(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID | None, *, lock: bool = False
) -> tuple[PiDocument, Quote] | None:
    """The proposal this customer has in hand and hasn't answered yet (latest first)."""
    if customer_id is None:
        return None
    query = (
        WorkspaceRepository(session, PiDocument, scope)
        .select()
        .join(Quote, Quote.id == PiDocument.quote_id)
        .where(
            PiDocument.customer_id == customer_id,
            PiDocument.kind == "proposal",
            PiDocument.response.is_(None),
            PiDocument.delivery.in_(["sent", "waiting", "manual"]),
            PiDocument.expires_at > datetime.now(UTC),
            Quote.status == "sent",
        )
        .order_by(PiDocument.created_at.desc())
        .limit(1)
    )
    doc = await session.scalar(query.with_for_update(of=PiDocument) if lock else query)
    if doc is None or doc.quote_id is None:
        return None
    quote = await WorkspaceRepository(session, Quote, scope).get(doc.quote_id)
    return doc, quote


async def proposal_context(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID | None
) -> dict[str, Any] | None:
    """What pi needs to know about an unanswered proposal in the chat (no prices)."""
    try:
        async with session.begin_nested():
            found = await open_proposal(session, scope, customer_id)
    except DBAPIError:  # Deal tables not migrated yet: no proposal to talk about.
        return None
    if found is None:
        return None
    doc, quote = found
    lines = await session.scalars(
        WorkspaceRepository(session, QuoteLine, scope)
        .select()
        .with_only_columns(QuoteLine.description)
        .where(QuoteLine.quote_id == quote.id)
        .limit(10)
    )
    return {
        "number": quote.number,
        "sent_on": f"{quote.sent_at or doc.created_at:%Y-%m-%d}",
        "covers": [str(d)[:120] for d in lines],
        "opened": doc.viewed_at is not None,
    }


async def answer_in_chat(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    customer_id: UUID | None,
    action: str,
    note: str,
    *,
    http: OutboundClient | None = None,
) -> list[str]:
    """The customer answered the proposal in the chat ("haan, accept hai"): the same
    steps as the page's buttons. Returns message ids to enqueue; [] when there was
    nothing open to answer or a step failed (the team is told by the usual notices)."""
    try:
        async with session.begin_nested():
            found = await open_proposal(session, scope, customer_id, lock=True)
            if found is None:
                return []
            return await answer(
                session, scope, settings, found[0], action, note, via="chat", http=http
            )
    except (DBAPIError, BusinessRuleViolation, ResourceNotFound):
        logger.warning("deal_chat_answer_skipped", exc_info=True)
        return []


async def answer(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    doc: PiDocument,
    action: str,
    note: str,
    *,
    via: str,
    http: OutboundClient | None = None,
) -> list[str]:
    """Accept / ask for changes / decline a proposal, from its page or from the chat."""
    if doc.kind != "proposal" or doc.quote_id is None:
        raise BusinessRuleViolation("NOT_A_PROPOSAL", "Only a proposal can be answered")
    if doc.response is not None:
        raise BusinessRuleViolation("ALREADY_ANSWERED", "You already answered this proposal")
    where = "in the WhatsApp chat" if via == "chat" else "on the proposal page"
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
        await note_lead(session, scope, quote.lead_id, f"customer accepted {quote.number} {where}")
        ids = await after_accept(session, scope, settings, quote, http=http)
        title = f"Proposal {quote.number} accepted"
    elif action == "changes":
        await quotes.transition(quote.id, "reject")
        if quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "qualified")
        await note_lead(
            session,
            scope,
            quote.lead_id,
            f"customer asked for changes on {quote.number} {where}: {note[:300] or 'no details'}",
        )
        await reopen_brief(session, scope, quote.lead_id, note)
        title = f"Changes asked on proposal {quote.number}"
    else:
        await quotes.transition(quote.id, "reject")
        if quote.lead_id:
            await move_lead(session, scope, quote.lead_id, "lost")
        await note_lead(
            session, scope, quote.lead_id, f"customer declined {quote.number} {where}: {note[:300]}"
        )
        title = f"Proposal {quote.number} declined"
    await notify(
        session,
        scope,
        "pi.deal",
        title,
        note[:500] or f"The customer answered {where}.",
        link=f"/quotes/{quote.id}",
        permission="quotes.read",
        severity="info" if action == "accepted" else "warning",
        dedupe_key=f"pi-deal:{doc.id}",
    )
    return ids


async def reopen_brief(
    session: AsyncSession, scope: WorkspaceScope, lead_id: UUID | None, note: str
) -> None:
    """Changes were asked: the chat's brief goes back to "waiting for the customer's yes"
    with the change request in it, so pi confirms the updated brief and, on their yes,
    writes the revised proposal."""
    lead = (
        await WorkspaceRepository(session, SalesLead, scope).find(SalesLead.id == lead_id)
        if lead_id
        else None
    )
    if lead is None or lead.conversation_id is None:
        return
    conversation = await WorkspaceRepository(session, PiConversation, scope).find(
        PiConversation.id == lead.conversation_id
    )
    if conversation is None:
        return
    brief = dict(conversation.service_brief or {})
    brief["projects"] = [
        {**p, "status": "awaiting_confirmation"}
        if isinstance(p, dict) and p.get("status") in {"confirmed", "with_team"}
        else p
        for p in brief.get("projects") or []
    ]
    brief["ready_for_team"] = False
    brief["proposal_changes"] = note[:1000] or "The customer asked for changes."
    conversation.service_brief = brief


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
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: Settings,
    quote: Quote,
    *,
    http: OutboundClient | None = None,
) -> list[str]:
    """Accepted: confirm the order, issue the invoice and send the payment link, each
    step only if the business switched it on. With ``http``, a business without pi's
    payment methods still gets a pay link from its Stripe integration; the customer is
    also emailed (best effort; the integrations sweep delivers it)."""
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
    await note_lead(
        session,
        scope,
        quote.lead_id,
        f"order {order.number} confirmed"
        + (f", invoice {invoice.number} issued" if invoice is not None else ""),
    )
    if invoice is None or not deals.auto_payment_request:
        return []
    doc, text, customer = await invoice_message(
        session,
        scope,
        settings,
        invoice,
        intro=say(
            "accepted",
            await customer_language(session, scope, quote.customer_id),
            number=order.number,
        ),
    )
    invoice_url = text.rsplit("Invoice: ", 1)[-1]
    text = await _with_card_link(session, settings, scope, invoice, text, http)
    ids = await deliver(session, scope, doc, customer, text)
    await _email_pay_link(session, scope, invoice, text, invoice_url)
    return ids


async def _with_card_link(
    session: AsyncSession,
    settings: Settings,
    scope: WorkspaceScope,
    invoice: Invoice,
    text: str,
    http: OutboundClient | None,
) -> str:
    """No pay link from pi's payment methods: add one from the Stripe integration."""
    from app.modules.pi_saas import payment_link

    if http is None or payment_link.pay_link_in(text):
        return text
    try:
        async with session.begin_nested():
            url = await payment_link.stripe_link(session, settings, http, scope, invoice)
    except Exception:  # noqa: BLE001 - the invoice still goes out without a card link
        logger.warning("deal_card_link_skipped", exc_info=True)
        return text
    return f"{text}\nPay by card: {url}" if url else text


async def _email_pay_link(
    session: AsyncSession, scope: WorkspaceScope, invoice: Invoice, text: str, invoice_url: str
) -> None:
    """The same pay link by email, when the customer has an address and the business
    an email integration. Queued; the integrations sweep sends it."""
    from app.modules.pi_saas import payment_link

    try:
        async with session.begin_nested():
            await payment_link.email_link(
                session, scope, invoice, payment_link.pay_link_in(text), invoice_url
            )
    except Exception:  # noqa: BLE001 - no email address or integration: WhatsApp only
        logger.info("deal_pay_link_email_skipped", exc_info=True)


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
        session,
        scope,
        settings,
        invoice,
        intro=say(
            "invoice",
            await customer_language(session, scope, invoice.customer_id),
            business=business,
        ),
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
            await note_lead(session, scope, quote.lead_id, f"invoice {invoice.number} paid")
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
    text = say("paid", conversation.language or "en", number=invoice.number)
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
