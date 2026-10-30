"""Erase what pi keeps about one person (pi Brain spec R-PRIV-06, 8.8, learning eval L11; platform
spec X5, ST12).

Removed: the problems pi noted (with their revisions, links and groups), the problem map (every
version), the Solution Boxes and their move history, the offer log, the Business Profile, pi's
open items, the move log, pi's memory notes, the encrypted quarantine copies, the learning scores
and examples from their chats, and the text of their messages and pi's replies (the rows stay so
counts and audit trails still add up, but the words go). Question-arm statistics are bare counts
with no personal data, so they stay.

Kept on purpose (platform spec 4.9 item 10, ST12: the box history follows the retention rules;
here only the box's own words and history go, never a quote): quotes, solution documents and
payments (business and financial records the company must be able to show), and the customer's
contact record in the CRM, which the customer module owns. The result says what was kept
(`kept`, `kept_reasons`), so staff can tell the person plainly.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import business_profile_store
from app.modules.pi.box_models import PiBoxTransition, PiMapVersion, PiOfferLog, PiSolutionBox
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningExample
from app.modules.pi.models import (
    PiConversation,
    PiHandoff,
    PiMemory,
    PiMessage,
    PiPendingAction,
)
from app.modules.pi.open_item_models import PiOpenItem
from app.modules.pi.problem_models import (
    PiProblem,
    PiProblemGroup,
    PiProblemLink,
    PiProblemRevision,
)
from app.modules.pi.quarantine_models import PiQuarantine
from app.modules.pi.solution_models import PiIdeaFeedback, PiSolutionMemory
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.modules.pi_customer.models import CustomerShareLink
from app.modules.pi_saas.deal_models import PiDocument
from app.modules.pi_saas.models import (
    PiBooking,
    PiConversationNote,
    PiConversationTag,
    PiStaffRequest,
    PiTask,
    PiTicket,
)
from app.shared.scope import WorkspaceScope

ERASED = "[deleted at the customer's request]"
# customer_share_links.phone is String(20): a marker, not a number (the column is not unique)
PHONE_ERASED = "erased"


def _n(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


async def _erase_conversation_extras(
    session: AsyncSession, scope: WorkspaceScope, conversation_ids: list[UUID]
) -> dict[str, int]:
    """Offer log and open items of these conversations (tables from migrations 0047 and 0052)."""
    out: dict[str, int] = {}
    for key, model in (("offer_log", PiOfferLog), ("open_items", PiOpenItem)):
        try:
            async with session.begin_nested():
                out[key] = _n(
                    await session.execute(
                        delete(model).where(
                            model.tenant_id == scope.tenant_id,
                            model.environment_id == scope.environment_id,
                            model.conversation_id.in_(conversation_ids),
                        )
                    )
                )
        except ProgrammingError:
            pass
    return out


def _digits(value: str | None) -> str:
    return "".join(ch for ch in value or "" if ch.isdigit())


async def _erase_workspace_texts(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, conversation_ids: list[UUID]
) -> dict[str, int]:
    """Gaps G1 to G9 (docs/pi-saas/pi-erase-gaps-g1-g14.md): staff notes, tags, tickets, staff
    requests, handoffs, pending drafts, bookings, tasks and deal documents. Rows that carry no
    record value go (tags, pending drafts); the others keep their row so counts, SLAs and audit
    trails still add up, and lose the customer's words, the same shape as the messages. Quotes,
    invoices and payments are not touched, and neither is a Knowledge document made from a staff
    answer."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    def of_customer(model: Any) -> Any:
        return or_(model.customer_id == customer_id, model.conversation_id.in_(conversation_ids))

    steps = (
        (
            "conversation_notes_cleared",
            update(PiConversationNote)
            .where(
                *mine(PiConversationNote), PiConversationNote.conversation_id.in_(conversation_ids)
            )
            .values(body=ERASED),
        ),
        (
            "conversation_tags",
            delete(PiConversationTag).where(
                *mine(PiConversationTag), PiConversationTag.conversation_id.in_(conversation_ids)
            ),
        ),
        (
            "tickets_cleared",
            update(PiTicket)
            .where(*mine(PiTicket), of_customer(PiTicket))
            .values(subject=ERASED, summary=""),
        ),
        (
            "staff_requests_cleared",
            update(PiStaffRequest)
            .where(*mine(PiStaffRequest), PiStaffRequest.customer_id == customer_id)
            .values(question=ERASED, context_summary="", answer=None),
        ),
        (
            "handoffs_cleared",
            update(PiHandoff)
            .where(*mine(PiHandoff), PiHandoff.customer_id == customer_id)
            .values(summary="", resolution_note=""),
        ),
        (
            "pending_actions",
            delete(PiPendingAction).where(
                *mine(PiPendingAction), PiPendingAction.conversation_id.in_(conversation_ids)
            ),
        ),
        (
            "bookings_cleared",
            update(PiBooking).where(*mine(PiBooking), of_customer(PiBooking)).values(notes=""),
        ),
        (
            "tasks_cleared",
            update(PiTask)
            .where(*mine(PiTask), of_customer(PiTask))
            .values(title=ERASED, description="", customer_visible_status=""),
        ),
        (
            "documents_text_cleared",
            update(PiDocument)
            .where(*mine(PiDocument), of_customer(PiDocument))
            .values(message_text="", response_note=""),
        ),
    )
    out: dict[str, int] = {}
    for key, statement in steps:
        try:
            async with session.begin_nested():
                out[key] = _n(await session.execute(statement))
        except ProgrammingError:
            pass
    return out


async def _erase_share_links(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, conversation_ids: list[UUID]
) -> dict[str, int]:
    """Gap G10: the portal share links keep the customer's phone number and have no workspace or
    customer key. Links to the erased chats are deleted. A link to all of the customer's chats
    spans other businesses too, so it is revoked and its phone removed instead (the customer can
    make a new one): that ends sharing in the customer's other businesses as well, which is the
    point."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    customer = await session.scalar(
        select(Customer).where(*mine(Customer), Customer.id == customer_id)
    )
    numbers: set[str | None] = (
        {customer.phone, customer.whatsapp_id} if customer is not None else set()
    )
    if conversation_ids:
        numbers |= set(
            await session.scalars(
                select(PiConversation.contact_wa_id).where(
                    *mine(PiConversation), PiConversation.id.in_(conversation_ids)
                )
            )
        )
    phones = {digits for digits in (_digits(number) for number in numbers) if digits}
    out: dict[str, int] = {}
    try:
        async with session.begin_nested():
            if conversation_ids:
                out["share_links_deleted"] = _n(
                    await session.execute(
                        delete(CustomerShareLink).where(
                            CustomerShareLink.conversation_id.in_(conversation_ids)
                        )
                    )
                )
            if phones:
                out["share_links_revoked"] = _n(
                    await session.execute(
                        update(CustomerShareLink)
                        .where(
                            CustomerShareLink.conversation_id.is_(None),
                            CustomerShareLink.phone.in_(phones),
                        )
                        .values(
                            revoked_at=func.coalesce(
                                CustomerShareLink.revoked_at, datetime.now(UTC)
                            ),
                            phone=PHONE_ERASED,
                        )
                    )
                )
    except ProgrammingError:
        pass
    return out


async def _erase_map_and_boxes(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[str, int]:
    """The map (every version), the Solution Boxes and their move history (spec X5, ST12). A box
    points at a map version and at its parent box, so the order is: moves, links between boxes,
    boxes, map versions."""
    out: dict[str, int] = {}
    try:  # the map and box tables arrive with migrations 0047 and 0051
        async with session.begin_nested():

            def mine(model: Any) -> tuple[Any, ...]:
                return (
                    model.tenant_id == scope.tenant_id,
                    model.environment_id == scope.environment_id,
                )

            box_ids = list(
                await session.scalars(
                    select(PiSolutionBox.id).where(
                        *mine(PiSolutionBox), PiSolutionBox.customer_id == customer_id
                    )
                )
            )
            if box_ids:
                out["box_transitions"] = _n(
                    await session.execute(
                        delete(PiBoxTransition).where(
                            *mine(PiBoxTransition), PiBoxTransition.box_id.in_(box_ids)
                        )
                    )
                )
                await session.execute(
                    update(PiSolutionBox)
                    .where(*mine(PiSolutionBox), PiSolutionBox.id.in_(box_ids))
                    .values(parent_box_id=None, map_version_id=None)
                )
            out["solution_boxes"] = _n(
                await session.execute(
                    delete(PiSolutionBox).where(
                        *mine(PiSolutionBox), PiSolutionBox.customer_id == customer_id
                    )
                )
            )
            out["map_versions"] = _n(
                await session.execute(
                    delete(PiMapVersion).where(
                        *mine(PiMapVersion), PiMapVersion.customer_id == customer_id
                    )
                )
            )
    except ProgrammingError:
        pass
    return out


async def erase_customer(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> dict[str, Any]:
    """Erase the customer's brain data in this workspace. Returns what was removed and kept."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    problem_ids = list(
        await session.scalars(
            select(PiProblem.id).where(*mine(PiProblem), PiProblem.customer_id == customer_id)
        )
    )
    removed: dict[str, int] = {}
    try:  # the solution tables arrive with migration 0043
        async with session.begin_nested():
            removed["solution_memory"] = _n(
                await session.execute(
                    delete(PiSolutionMemory).where(
                        *mine(PiSolutionMemory), PiSolutionMemory.customer_id == customer_id
                    )
                )
            )
            removed["idea_feedback"] = _n(
                await session.execute(
                    delete(PiIdeaFeedback).where(
                        *mine(PiIdeaFeedback), PiIdeaFeedback.customer_id == customer_id
                    )
                )
            )
    except ProgrammingError:
        pass
    if problem_ids:
        removed["links"] = _n(
            await session.execute(
                delete(PiProblemLink).where(
                    *mine(PiProblemLink),
                    or_(
                        PiProblemLink.from_id.in_(problem_ids),
                        PiProblemLink.to_id.in_(problem_ids),
                    ),
                )
            )
        )
        removed["revisions"] = _n(
            await session.execute(
                delete(PiProblemRevision).where(
                    *mine(PiProblemRevision), PiProblemRevision.problem_id.in_(problem_ids)
                )
            )
        )
    removed["problems"] = _n(
        await session.execute(
            delete(PiProblem).where(*mine(PiProblem), PiProblem.customer_id == customer_id)
        )
    )
    removed["groups"] = _n(
        await session.execute(
            delete(PiProblemGroup).where(
                *mine(PiProblemGroup), PiProblemGroup.customer_id == customer_id
            )
        )
    )
    removed["learning_examples"] = _n(
        await session.execute(
            delete(PiLearningExample).where(
                *mine(PiLearningExample),
                PiLearningExample.source_contacts.contains([str(customer_id)]),
            )
        )
    )
    removed["memories"] = _n(
        await session.execute(
            delete(PiMemory).where(*mine(PiMemory), PiMemory.customer_id == customer_id)
        )
    )

    conversation_ids = list(
        await session.scalars(
            select(PiConversation.id).where(
                *mine(PiConversation), PiConversation.customer_id == customer_id
            )
        )
    )
    message_ids: list[UUID] = []
    if conversation_ids:
        message_ids = list(
            await session.scalars(
                select(PiMessage.id).where(
                    *mine(PiMessage), PiMessage.conversation_id.in_(conversation_ids)
                )
            )
        )
        removed["experiences"] = _n(
            await session.execute(
                delete(PiExperience).where(
                    *mine(PiExperience), PiExperience.conversation_id.in_(conversation_ids)
                )
            )
        )
        # the thinking step's notes about the chat (hypotheses hold the owner's own words)
        await session.execute(
            delete(PiHypothesis).where(
                *mine(PiHypothesis), PiHypothesis.conversation_id.in_(conversation_ids)
            )
        )
        removed["move_log"] = _n(
            await session.execute(
                delete(PiMoveLog).where(
                    *mine(PiMoveLog), PiMoveLog.conversation_id.in_(conversation_ids)
                )
            )
        )
        removed.update(await _erase_conversation_extras(session, scope, conversation_ids))
        removed["quarantine"] = _n(
            await session.execute(
                delete(PiQuarantine).where(
                    *mine(PiQuarantine), PiQuarantine.message_id.in_(message_ids)
                )
            )
        )
        removed["messages_cleared"] = _n(
            await session.execute(
                update(PiMessage)
                .where(*mine(PiMessage), PiMessage.conversation_id.in_(conversation_ids))
                .values(body=ERASED, media={})
            )
        )
        await session.execute(
            update(PiConversation)
            .where(*mine(PiConversation), PiConversation.id.in_(conversation_ids))
            # The summary and preview are words from their chats, read back to the model every
            # turn: they go too (R-PRIV-06), or pi would keep remembering what was deleted.
            .values(
                service_brief={"erased": True},
                followup_due_at=None,
                summary="",
                last_message_preview=ERASED,
            )
        )
    removed.update(await _erase_map_and_boxes(session, scope, customer_id))
    removed.update(await _erase_workspace_texts(session, scope, customer_id, conversation_ids))
    removed.update(await _erase_share_links(session, scope, customer_id, conversation_ids))
    # the Business Profile (facts, page snapshots) is what the owner told pi about their business
    try:  # the profile tables arrive with migration 0050
        async with session.begin_nested():
            removed["business_profiles"] = await business_profile_store.erase_for_customer(
                session, scope, customer_id
            )
    except ProgrammingError:
        pass
    # What pi inferred onto the customer record (industry) is brain data, not CRM contact data.
    await session.execute(
        update(Customer)
        .where(*mine(Customer), Customer.id == customer_id)
        .values(industry_primary=None, industry_secondary=[], industry_confidence=None)
    )
    kept = {
        "documents": len(
            list(
                await session.scalars(
                    select(PiBrainDocument.id).where(
                        *mine(PiBrainDocument), PiBrainDocument.customer_id == customer_id
                    )
                )
            )
        ),
        "payments": len(
            list(
                await session.scalars(
                    select(PiBrainPayment.id).where(
                        *mine(PiBrainPayment), PiBrainPayment.customer_id == customer_id
                    )
                )
            )
        ),
    }
    return {
        "removed": removed,
        "kept": kept,
        "kept_reasons": {
            "documents": "business records the company must be able to show",
            "payments": "financial records the company must be able to show",
            "customer_contact": "the CRM contact record belongs to the customer module",
            "message_rows": "the rows stay so counts and audit trails add up; the words are gone",
            "text_only_rows": (
                "tickets, handoffs, staff requests, tasks, bookings, staff notes and deal "
                "documents keep their rows for counts and audit trails; the customer's words "
                "are gone"
            ),
        },
        "conversations": len(conversation_ids),
    }
