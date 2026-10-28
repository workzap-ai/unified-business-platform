"""Erase what pi keeps about one person (pi Brain spec R-PRIV-06, 8.8, learning eval L11).

Removed: the problems pi noted (with their revisions, links and groups), pi's memory notes, the
encrypted quarantine copies, the learning scores and examples from their chats, and the text of
their messages and pi's replies (the rows stay so counts and audit trails still add up, but the
words go). Question-arm statistics are bare counts with no personal data, so they stay.

Kept on purpose: quotes, solution documents and payments (business and financial records the
company must be able to show), and the customer's contact record in the CRM, which the customer
module owns. The result says what was kept, so staff can tell the person plainly.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import business_profile_store
from app.modules.pi.brain_docs_models import PiBrainDocument, PiBrainPayment
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningExample
from app.modules.pi.models import PiConversation, PiMemory, PiMessage
from app.modules.pi.problem_models import (
    PiProblem,
    PiProblemGroup,
    PiProblemLink,
    PiProblemRevision,
)
from app.modules.pi.quarantine_models import PiQuarantine
from app.modules.pi.solution_models import PiIdeaFeedback, PiSolutionMemory
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.shared.scope import WorkspaceScope

ERASED = "[deleted at the customer's request]"


def _n(result: Any) -> int:
    return int(getattr(result, "rowcount", 0) or 0)


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
        await session.execute(
            delete(PiMoveLog).where(
                *mine(PiMoveLog), PiMoveLog.conversation_id.in_(conversation_ids)
            )
        )
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
    return {"removed": removed, "kept": kept, "conversations": len(conversation_ids)}
