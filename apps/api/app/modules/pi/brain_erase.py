"""Erase what pi keeps about one person (pi Brain spec R-PRIV-06, 8.8, learning eval L11; platform
spec X5, ST12).

Removed: the problems pi noted (with their revisions, links and groups), the problem map (every
version), the Solution Boxes and their move history, the offer log, the Business Profile, pi's
open items, the move log, pi's memory notes, the encrypted quarantine copies, the learning scores
and examples from their chats, and the text of their messages and pi's replies (the rows stay so
counts and audit trails still add up, but the words go). Question-arm statistics are bare counts
with no personal data, so they stay.

Cleared in place (gaps G1 to G9, docs/pi-saas/pi-erase-gaps-g1-g14.md on origin/main): staff notes,
tickets, staff requests, handoffs, bookings, tasks and deal documents keep their row (counts, SLAs
and audit trails still add up) and lose the customer's words. Tags and the unresolved pending draft
are deleted; a confirmed or cancelled draft keeps a blank audit row. Gap G10: portal share links
scoped to the erased chats are deleted.

Residual risk, erase decision R1 (share links) is open: `customer_share_links` has no workspace key,
so a link to ALL of a customer's chats (it carries the phone and spans businesses) is NOT touched
here. Gaps G11 to G14 (CRM notes, activities, files, leads) wait for the retention decision.

Kept on purpose (platform spec 4.9 item 10, ST12: the box history follows the retention rules;
here only the box's own words and history go, never a quote): quotes, solution documents and
payments (business and financial records the company must be able to show), and the customer's
contact record in the CRM, which the customer module owns. The result says what was kept
(`kept`, `kept_reasons`), so staff can tell the person plainly.

Every step runs in its own savepoint. A step that cannot run (a table missing in this database) is
named in removed["_skipped"] and logged, computed at the very end from every step, so a successful
response never hides a step that did not erase.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select, update
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

logger = logging.getLogger(__name__)

ERASED = "[deleted at the customer's request]"

# Every count `erase_customer` can report: always present, 0 when nothing matched, so a caller or a
# test never meets a missing key. A step that could not run is named in removed["_skipped"].
REMOVED_KEYS = (
    "solution_memory",
    "idea_feedback",
    "links",
    "revisions",
    "problems",
    "groups",
    "learning_examples",
    "memories",
    "experiences",
    "hypotheses",
    "move_log",
    "offer_log",
    "open_items",
    "quarantine",
    "messages_cleared",
    "box_transitions",
    "solution_boxes",
    "map_versions",
    "box_links_cleared",
    "business_profiles",
    "conversation_notes_cleared",
    "conversation_tags",
    "tickets_cleared",
    "staff_requests_cleared",
    "handoffs_cleared",
    "pending_actions",
    "pending_actions_cleared",
    "bookings_cleared",
    "tasks_cleared",
    "documents_text_cleared",
    "share_links_deleted",
)


def _n(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


async def _erase_conversation_extras(
    session: AsyncSession, scope: WorkspaceScope, conversation_ids: list[UUID]
) -> tuple[dict[str, int], list[str]]:
    """Offer log and open items of these conversations (tables from migrations 0047 and 0052)."""
    steps: list[tuple[str, Any]] = []
    for key, model in (("offer_log", PiOfferLog), ("open_items", PiOpenItem)):
        steps.append(
            (
                key,
                delete(model).where(
                    model.tenant_id == scope.tenant_id,
                    model.environment_id == scope.environment_id,
                    model.conversation_id.in_(conversation_ids),
                ),
            )
        )
    return await _run_steps(session, tuple(steps))


UNDEFINED_TABLE = "42P01"  # PostgreSQL SQLSTATE: the only error a step may be skipped for


def _sqlstate(exc: ProgrammingError) -> str | None:
    """The SQLSTATE of a database error (asyncpg and psycopg variants), or None if unreadable."""
    for carrier in (exc.orig, getattr(exc.orig, "__cause__", None)):
        for name in ("sqlstate", "pgcode"):
            value = getattr(carrier, name, None)
            if isinstance(value, str) and value:
                return value
    return None


async def _run_steps(
    session: AsyncSession, steps: tuple[tuple[str, Any], ...]
) -> tuple[dict[str, int], list[str]]:
    """Run each step in its own savepoint. A step is a statement, or a function returning an
    awaitable count (the profile store). Only an undefined table (SQLSTATE 42P01: the migration
    that creates it has not run in this database) skips a step: it is named and logged, never
    dropped silently, and the caller reports it. Any other error, including a ProgrammingError
    whose SQLSTATE is another code or cannot be read, propagates: the request's transaction rolls
    back, nothing is committed and the caller sees a failure, never a partial erase."""
    counts = {key: 0 for key, _ in steps}
    skipped: list[str] = []
    for key, step in steps:
        try:
            async with session.begin_nested():
                if hasattr(step, "compile"):
                    counts[key] = _n(await session.execute(step))
                else:
                    counts[key] = int(await step())
        except ProgrammingError as exc:
            sqlstate = _sqlstate(exc)
            if sqlstate != UNDEFINED_TABLE:
                raise  # not a missing table (or unreadable): fail the request, erase nothing
            skipped.append(key)
            logger.warning("pi_erase_step_skipped", extra={"step": key, "sqlstate": sqlstate})
    return counts, skipped


async def _erase_workspace_texts(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, conversation_ids: list[UUID]
) -> tuple[dict[str, int], list[str]]:
    """Gaps G1 to G9 (docs/pi-saas/pi-erase-gaps-g1-g14.md on origin/main): staff notes, tags,
    tickets, staff requests, handoffs, pending drafts, bookings, tasks and deal documents. Rows
    that carry no record value go (tags and the one unresolved pending draft); the others keep
    their row so counts, SLAs and audit trails still add up, and lose the customer's words, the
    same shape as the messages (a confirmed or cancelled draft keeps its small audit row, text
    blanked). Quotes, invoices and payments are not touched, and neither is a Knowledge document
    made from a staff answer."""

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
                *mine(PiPendingAction),
                PiPendingAction.conversation_id.in_(conversation_ids),
                PiPendingAction.status == "pending",
            ),
        ),
        (
            "pending_actions_cleared",
            update(PiPendingAction)
            .where(
                *mine(PiPendingAction),
                PiPendingAction.conversation_id.in_(conversation_ids),
                PiPendingAction.status != "pending",
            )
            .values(payload={}, summary=""),
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
    return await _run_steps(session, steps)


async def _erase_share_links(
    session: AsyncSession, scope: WorkspaceScope, conversation_ids: list[UUID]
) -> tuple[dict[str, int], list[str]]:
    """Gap G10, the part that is safe today: portal share links scoped to the erased chats are
    deleted, and the statement can only match conversation ids of THIS workspace (a subquery on
    the conversations with the tenant and environment, on top of the ids already being ours).

    Residual risk, erase decision R1 (share links) open: `customer_share_links` has no tenant,
    environment or customer key. A link to ALL of the customer's chats (conversation_id empty)
    carries the customer's phone and spans other businesses, so it is left untouched here;
    revoking it or blanking its phone would act across businesses. Options: add tenant_id and
    environment_id by a migration, revoke only, or a customer-initiated revoke in the pi
    Customer portal."""

    ours = select(PiConversation.id).where(
        PiConversation.tenant_id == scope.tenant_id,
        PiConversation.environment_id == scope.environment_id,
        PiConversation.id.in_(conversation_ids),
    )
    steps = (
        (
            "share_links_deleted",
            delete(CustomerShareLink).where(CustomerShareLink.conversation_id.in_(ours)),
        ),
    )
    return await _run_steps(session, steps)


async def _erase_map_and_boxes(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> tuple[dict[str, int], list[str]]:
    """The map (every version), the Solution Boxes and their move history (spec X5, ST12). A box
    points at a map version and at its parent box, so the order is: moves, links between boxes,
    boxes, map versions. Tables from migrations 0047 and 0051; each step has its own savepoint."""

    def mine(model: Any) -> tuple[Any, ...]:
        return (
            model.tenant_id == scope.tenant_id,
            model.environment_id == scope.environment_id,
        )

    box_ids = select(PiSolutionBox.id).where(
        *mine(PiSolutionBox), PiSolutionBox.customer_id == customer_id
    )
    steps = (
        (
            "box_transitions",
            delete(PiBoxTransition).where(
                *mine(PiBoxTransition), PiBoxTransition.box_id.in_(box_ids)
            ),
        ),
        (
            "box_links_cleared",
            update(PiSolutionBox)
            .where(*mine(PiSolutionBox), PiSolutionBox.id.in_(box_ids))
            .values(parent_box_id=None, map_version_id=None),
        ),
        (
            "solution_boxes",
            delete(PiSolutionBox).where(
                *mine(PiSolutionBox), PiSolutionBox.customer_id == customer_id
            ),
        ),
        (
            "map_versions",
            delete(PiMapVersion).where(
                *mine(PiMapVersion), PiMapVersion.customer_id == customer_id
            ),
        ),
    )
    return await _run_steps(session, steps)


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
    removed: dict[str, Any] = {key: 0 for key in REMOVED_KEYS}
    skipped: list[str] = []

    def absorb(result: tuple[dict[str, int], list[str]]) -> None:
        removed.update(result[0])
        skipped.extend(result[1])

    # the solution tables arrive with migration 0043
    absorb(
        await _run_steps(
            session,
            (
                (
                    "solution_memory",
                    delete(PiSolutionMemory).where(
                        *mine(PiSolutionMemory), PiSolutionMemory.customer_id == customer_id
                    ),
                ),
                (
                    "idea_feedback",
                    delete(PiIdeaFeedback).where(
                        *mine(PiIdeaFeedback), PiIdeaFeedback.customer_id == customer_id
                    ),
                ),
            ),
        )
    )
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
        removed["hypotheses"] = _n(
            await session.execute(
                delete(PiHypothesis).where(
                    *mine(PiHypothesis), PiHypothesis.conversation_id.in_(conversation_ids)
                )
            )
        )
        removed["move_log"] = _n(
            await session.execute(
                delete(PiMoveLog).where(
                    *mine(PiMoveLog), PiMoveLog.conversation_id.in_(conversation_ids)
                )
            )
        )
        absorb(await _erase_conversation_extras(session, scope, conversation_ids))
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
    absorb(await _erase_map_and_boxes(session, scope, customer_id))
    absorb(await _erase_workspace_texts(session, scope, customer_id, conversation_ids))
    absorb(await _erase_share_links(session, scope, conversation_ids))
    # the Business Profile (facts, page snapshots) is what the owner told pi about their business;
    # its tables arrive with migration 0050
    absorb(
        await _run_steps(
            session,
            (
                (
                    "business_profiles",
                    lambda: business_profile_store.erase_for_customer(session, scope, customer_id),
                ),
            ),
        )
    )
    # What pi inferred onto the customer record (industry) is brain data, not CRM contact data.
    await session.execute(
        update(Customer)
        .where(*mine(Customer), Customer.id == customer_id)
        .values(industry_primary=None, industry_secondary=[], industry_confidence=None)
    )
    # computed last, from every step above: a success never hides a step that did not run
    removed["_skipped"] = skipped
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
            "share_links_all_chats": (
                "needs owner decision, erase decision R1 (share links): links to all of a "
                "customer's chats carry no workspace key, so they are left untouched"
            ),
            "text_only_rows": (
                "tickets, handoffs, staff requests, tasks, bookings, staff notes and deal "
                "documents keep their rows for counts and audit trails; the customer's words "
                "are gone"
            ),
        },
        "conversations": len(conversation_ids),
        # false when a step was skipped (its table is missing): the erase is INCOMPLETE
        "complete": not skipped,
        "skipped": skipped,
    }
