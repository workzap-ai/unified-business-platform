"""Automatic follow-ups: pi nudges the customer when a deal goes quiet.

    proposal sent, not opened after 2 days      → "your proposal is waiting"
    proposal opened, no answer after 3 days     → "any questions? reply to accept"
    invoice unpaid, due tomorrow                → reminder with a fresh pay link
    invoice unpaid, 3 days past its due date    → overdue reminder with the pay link

Each nudge goes once (an idempotency key per document and kind), in the customer's
language, and is written into the lead's notes. A proposal nudge stops once the customer
has written since the proposal went out, and no nudge goes while the team has taken the
chat over. WhatsApp's rules apply: inside the 24-hour window the text goes in the chat;
outside it only the business's approved "your document is ready" template can go; with
neither, nothing is sent. The business switches this off with ``auto_followups``.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.billing.models import Invoice
from app.modules.customers.models import Customer
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas import deals
from app.modules.pi_saas.deal_models import PiDocument
from app.modules.quotes.models import Quote
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

UNOPENED_AFTER = timedelta(days=2)
UNANSWERED_AFTER = timedelta(days=3)
OVERDUE_AFTER = timedelta(days=3)
BATCH = 200

TEXTS: dict[str, dict[str, str]] = {
    "proposal_unopened": {
        "en": "Hi{hi}, a gentle reminder: your proposal {number} from {business} ({total}) "
        "is in our earlier message. Reply here to accept it or to ask for changes.",
        "roman_ur": "Assalam o alaikum{hi}, yaad dehani: {business} ka proposal {number} "
        "({total}) pichle message mein hai. Yahin reply kar ke accept karein ya changes "
        "batayein.",
    },
    "proposal_unanswered": {
        "en": "Hi{hi}, any questions about proposal {number}? Reply here to accept it, or "
        "tell us what you'd like changed.",
        "roman_ur": "Assalam o alaikum{hi}, proposal {number} ke baare mein koi sawal? Yahin "
        "reply kar ke accept karein, ya batayein kya change karna hai.",
    },
    "invoice_due": {
        "en": "Hi{hi}, a reminder that invoice {number} ({amount}) is due on {due}.{pay}",
        "roman_ur": "Assalam o alaikum{hi}, yaad dehani: invoice {number} ({amount}) ki "
        "aakhri tareekh {due} hai.{pay}",
    },
    "invoice_overdue": {
        "en": "Hi{hi}, invoice {number} ({amount}) was due on {due} and is still open.{pay} "
        "Reply here if anything is unclear.",
        "roman_ur": "Assalam o alaikum{hi}, invoice {number} ({amount}) ki tareekh {due} thi "
        "aur payment abhi baqi hai.{pay} Koi masla ho to yahin batayein.",
    },
    "pay": {"en": "\nPay here: {url}", "roman_ur": "\nYahan pay karein: {url}"},
}
NOTES = {
    "proposal_unopened": "reminded the customer about unopened proposal {number}",
    "proposal_unanswered": "asked the customer about proposal {number} (opened, no answer)",
    "invoice_due": "reminded the customer that invoice {number} is due {due}",
    "invoice_overdue": "reminded the customer that invoice {number} is overdue",
}


def text(key: str, language: str, **values: str) -> str:
    found = TEXTS[key]
    return found.get(language, found["en"]).format(**values)


def key_for(kind: str, doc_id: UUID) -> str:
    return f"pi-nudge:{kind}:{doc_id}"


def due_nudge(
    doc: PiDocument, quote: Quote | None, invoice: Invoice | None, now: datetime
) -> str | None:
    """Which nudge this document needs now, if any (pure; the caller checks history)."""
    today = now.date()
    if doc.kind == "proposal":
        if quote is None or quote.status != "sent" or doc.response is not None:
            return None
        if quote.valid_until < today or doc.delivery not in {"sent", "waiting"}:
            return None
        if doc.viewed_at is None:
            return "proposal_unopened" if doc.created_at <= now - UNOPENED_AFTER else None
        return "proposal_unanswered" if doc.viewed_at <= now - UNANSWERED_AFTER else None
    if invoice is None or invoice.status not in {"issued", "partially_paid"}:
        return None
    due: date | None = invoice.due_date
    if due is None:
        return None
    if today >= due + OVERDUE_AFTER:
        return "invoice_overdue"
    if due - timedelta(days=1) <= today <= due:
        return "invoice_due"
    return None


async def _already(session: AsyncSession, key: str) -> bool:
    return (
        await session.scalar(select(PiMessage.id).where(PiMessage.idempotency_key == key).limit(1))
    ) is not None


async def _queue_nudge(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    doc: PiDocument,
    body: str,
    key: str,
    now: datetime,
) -> str | None:
    """Inside the 24-hour window: the text. Outside: the approved template, or nothing."""
    if conversation.last_inbound_at and conversation.last_inbound_at > now - deals.WINDOW:
        return await deals._queue(session, scope, conversation, body, key)
    settings = await deals.deal_settings(session, scope)
    if not (settings.template_name and settings.template_language):
        return None
    template = {"name": settings.template_name, "language": settings.template_language}
    return await deals._queue(
        session,
        scope,
        conversation,
        "",
        key,
        {"document_notice": {"template": template, "document_id": str(doc.id)}},
    )


async def nudge(
    session: AsyncSession, app_settings: Settings, doc: PiDocument, now: datetime
) -> str | None:
    """Send the nudge one document needs now; returns the message id to enqueue."""
    scope = await deals.system_scope_for(session, doc.tenant_id, doc.environment_id)
    if not (await deals.deal_settings(session, scope)).auto_followups:
        return None
    quote = (
        await WorkspaceRepository(session, Quote, scope).find(Quote.id == doc.quote_id)
        if doc.quote_id
        else None
    )
    invoice = (
        await WorkspaceRepository(session, Invoice, scope).find(Invoice.id == doc.invoice_id)
        if doc.invoice_id
        else None
    )
    kind = due_nudge(doc, quote, invoice, now)
    if kind is None or doc.conversation_id is None:
        return None
    key = key_for(kind, doc.id)
    if await _already(session, key):
        return None
    conversation = await WorkspaceRepository(session, PiConversation, scope).find(
        PiConversation.id == doc.conversation_id
    )
    if conversation is None or conversation.mode == "human":
        return None  # The team is handling this chat.
    since = doc.viewed_at or doc.created_at
    if (
        doc.kind == "proposal"
        and conversation.last_inbound_at
        and conversation.last_inbound_at > since
    ):
        return None  # They wrote since: pi answers them in the chat instead.
    customer = await WorkspaceRepository(session, Customer, scope).get(doc.customer_id)
    language = str(conversation.language or "en")
    first = "" if customer.name.startswith("WhatsApp") else customer.name.split(" ")[0]
    values: dict[str, str] = {"hi": f" {first}" if first else ""}
    lead_id = doc.lead_id
    if quote is not None and doc.kind == "proposal":
        values |= {
            "number": quote.number,
            "business": await deals._business_name(session, scope),
            "total": deals.money(quote.total, quote.currency),
        }
    elif invoice is not None:
        pay = await deals._open_pay_link(session, scope, app_settings, invoice)
        values |= {
            "number": invoice.number,
            "amount": deals.money(invoice.total - invoice.amount_paid, invoice.currency),
            "due": f"{invoice.due_date:%d %b %Y}" if invoice.due_date else "",
            "pay": text("pay", language, url=pay) if pay else "",
        }
        if lead_id is None and invoice.order_id:
            lead_id = await session.scalar(
                WorkspaceRepository(session, Quote, scope)
                .select()
                .with_only_columns(Quote.lead_id)
                .where(Quote.order_id == invoice.order_id)
                .limit(1)
            )
    body = text(kind, language, **values)
    message_id = await _queue_nudge(session, scope, conversation, doc, body, key, now)
    if message_id is None:
        return None
    await deals.note_lead(session, scope, lead_id, NOTES[kind].format(**values))
    return message_id


async def candidates(session: AsyncSession, now: datetime) -> list[PiDocument]:
    """Documents that could need a nudge, across every business (cheap filter only)."""
    return list(
        await session.scalars(
            select(PiDocument)
            .where(
                PiDocument.expires_at > now,
                PiDocument.conversation_id.is_not(None),
                or_(
                    (PiDocument.kind == "proposal") & PiDocument.response.is_(None),
                    PiDocument.kind == "invoice",
                ),
                PiDocument.created_at <= now - timedelta(hours=12),
            )
            .order_by(PiDocument.created_at)
            .limit(BATCH)
        )
    )


async def sweep(
    session: AsyncSession, app_settings: Settings, now: datetime | None = None
) -> list[str]:
    """Send every nudge that's due. Each document runs in its own savepoint, so one bad
    row never blocks the rest. Returns the message ids to enqueue (caller commits)."""
    now = now or datetime.now(UTC)
    ids: list[str] = []
    for doc in await candidates(session, now):
        try:
            async with session.begin_nested():
                sent = await nudge(session, app_settings, doc, now)
        except (DBAPIError, BusinessRuleViolation, ResourceNotFound):
            logger.warning("deal_followup_skipped", exc_info=True)
            continue
        if sent:
            ids.append(sent)
    return ids


def next_reminder(
    doc: PiDocument | None, quote: Quote | None, invoice: Invoice | None, now: datetime
) -> dict[str, Any] | None:
    """The next nudge pi will send for this deal, for the journey page: {kind, at}."""
    if invoice is not None:
        if invoice.status not in {"issued", "partially_paid"} or not invoice.due_date:
            return None
        if now.date() <= invoice.due_date:
            return {"kind": "invoice_due", "at": invoice.due_date - timedelta(days=1)}
        return {"kind": "invoice_overdue", "at": invoice.due_date + OVERDUE_AFTER}
    if doc is None or doc.kind != "proposal" or quote is None:
        return None
    if quote.status != "sent" or doc.response is not None:
        return None
    if doc.viewed_at is None:
        return {"kind": "proposal_unopened", "at": doc.created_at + UNOPENED_AFTER}
    return {"kind": "proposal_unanswered", "at": doc.viewed_at + UNANSWERED_AFTER}
