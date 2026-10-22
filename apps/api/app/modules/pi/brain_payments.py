"""Payment and kickoff in brain mode (pi Brain spec 5.6, R-PAY-05, R-PAY-06, R-KICK-01 to 03).

The money moves by bank transfer, outside the chat, to the account printed on the approved quote.
pi never confirms it: a customer who says they paid, or sends a screenshot, only makes the payment
`claimed`; Workzap staff `confirm` it (a person with billing rights, from the review screen or API).
Confirming moves the chat to S11 and tells the customer; a kickoff slot then moves it to S12.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import brain_docs, decisions, flow
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.models import PiConversation
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger("platform")


async def open_for(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation, quote_ref: str
) -> PiBrainPayment | None:
    """One pending payment for the quote the person approved (none if it already exists)."""
    docs = WorkspaceRepository(session, PiBrainDocument, scope)
    for quote in await _quotes(session, docs, conversation):
        if quote.ref != quote_ref:
            continue
        payments = WorkspaceRepository(session, PiBrainPayment, scope)
        found = await payments.find(PiBrainPayment.quote_id == quote.id)
        if found is not None:
            return found
        return await payments.add(
            payments.new(
                customer_id=quote.customer_id,
                conversation_id=conversation.id,
                quote_id=quote.id,
                status="pending",
            )
        )
    return None


async def _quotes(
    session: AsyncSession, docs: WorkspaceRepository[PiBrainDocument], conversation: PiConversation
) -> list[PiBrainDocument]:
    rows = await session.scalars(
        docs.select().where(
            PiBrainDocument.conversation_id == conversation.id, PiBrainDocument.kind == "quote"
        )
    )
    return list(rows)


async def open_payment(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation
) -> PiBrainPayment | None:
    """The payment still waiting for this chat (pending or claimed), newest first."""
    payments = WorkspaceRepository(session, PiBrainPayment, scope)
    rows = await session.scalars(
        payments.select()
        .where(
            PiBrainPayment.conversation_id == conversation.id,
            PiBrainPayment.status.in_(("pending", "claimed")),
        )
        .order_by(PiBrainPayment.created_at.desc())
        .limit(1)
    )
    return rows.first()


async def claim(
    session: AsyncSession, scope: WorkspaceScope, conversation: PiConversation
) -> PiBrainPayment | None:
    """The person says they paid. This never confirms anything (R-PAY-06)."""
    payment = await open_payment(session, scope, conversation)
    if payment is not None and payment.status == "pending":
        payment.status = "claimed"
        payment.claimed_at = datetime.now(UTC)
    return payment


async def confirm(
    session: AsyncSession,
    scope: WorkspaceScope,
    payment_id: UUID,
    user_id: UUID | None,
    reference: str = "",
    note: str = "",
) -> list[str]:
    """Staff confirm the transfer arrived (R-PAY-05). Moves the chat to S11 and tells the person.
    Returns the queued message ids for the caller to enqueue."""
    payments = WorkspaceRepository(session, PiBrainPayment, scope)
    payment = await payments.get(payment_id, for_update=True)
    if payment.status == "confirmed":
        raise BusinessRuleViolation("ALREADY_CONFIRMED", "This payment was already confirmed", 409)
    payment.status = "confirmed"
    payment.confirmed_by = user_id
    payment.confirmed_at = datetime.now(UTC)
    payment.reference = reference[:120]
    payment.note = note[:1000]
    if payment.conversation_id is None:
        return []
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        payment.conversation_id
    )
    now = datetime.now(UTC)
    state = flow.parse(conversation.flow_state)
    if state in (flow.State.S9_APPROVED, flow.State.S10_AWAITING_PAYMENT):
        for step in flow.path(state, flow.State.S11_PAYMENT_CONFIRMED) or []:
            state = flow.advance(state, step)
        conversation.flow_state = flow.State.S11_PAYMENT_CONFIRMED.value
        conversation.flow_state_since = now
    brief = dict(conversation.service_brief or {})
    brief["payment"] = {"status": "confirmed", "at": now.isoformat(), "reference": reference[:120]}
    language = (
        conversation.language
        if conversation.language in decisions.TEXT["payment_confirmed"]
        else "en"
    )
    ids: list[str] = []
    if conversation.last_inbound_at and conversation.last_inbound_at > now - brain_docs.WINDOW:
        ids.append(
            await brain_docs.queue_message(
                session,
                scope,
                conversation,
                decisions.text("payment_confirmed", language),
                f"pi-brain-paid:{payment.id}",
                {},
            )
        )
    else:
        # Outside WhatsApp's 24 hours a free message cannot go: tell them when they next write.
        brief["payment_notice_due"] = True
    conversation.service_brief = brief
    return ids


def kickoff_booked(conversation: PiConversation) -> bool:
    """A kickoff slot was booked after payment was confirmed: S11 to S12 (R-KICK-02)."""
    state = flow.parse(conversation.flow_state)
    if state != flow.State.S11_PAYMENT_CONFIRMED:
        return False
    conversation.flow_state = flow.advance(state, flow.State.S12_KICKOFF).value
    conversation.flow_state_since = datetime.now(UTC)
    brief = dict(conversation.service_brief or {})
    brief["kickoff"] = {"booked_at": datetime.now(UTC).isoformat()}
    conversation.service_brief = brief
    return True


def view(payment: PiBrainPayment, quote: PiBrainDocument | None = None) -> dict[str, Any]:
    return {
        "id": payment.id,
        "status": payment.status,
        "quote_id": payment.quote_id,
        "quote_ref": quote.ref if quote else None,
        "total": str(quote.total) if quote and quote.total is not None else None,
        "currency": quote.currency if quote else None,
        "customer_id": payment.customer_id,
        "conversation_id": payment.conversation_id,
        "claimed_at": payment.claimed_at,
        "confirmed_at": payment.confirmed_at,
        "reference": payment.reference,
        "created_at": payment.created_at,
    }
