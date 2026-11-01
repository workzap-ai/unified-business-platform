"""The delivered and verified markers on an approved solution document or quote (migration 0056).

They are set ONLY here, and only a named staff member can set them: `staff_user_id` is required and
the one caller is the staff route in `brain_doc_routes` (permission `quotes.write`). Nothing in the
conversation, the model or the learning code imports this module (a test keeps it so). "Verified"
needs "delivered" first. A document that was never approved cannot be marked.

The columns are deferred on the model, so the update is an explicit statement and code deployed
before 0056 is unaffected.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.brain_docs_models import PiBrainDocument
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope


def _refuse(message: str) -> BusinessRuleViolation:
    return BusinessRuleViolation("DELIVERY_MARK_REFUSED", message, 409)


async def _row(session: AsyncSession, scope: WorkspaceScope, doc_id: UUID) -> PiBrainDocument:
    doc = await session.scalar(
        select(PiBrainDocument).where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.id == doc_id,
        )
    )
    if doc is None:
        raise BusinessRuleViolation("NOT_FOUND", "Document not found", 404)
    if doc.status not in ("approved", "sent"):
        raise _refuse("only an approved or sent document can be marked delivered")
    return doc


async def mark_delivered(
    session: AsyncSession,
    scope: WorkspaceScope,
    doc_id: UUID,
    staff_user_id: UUID | None,
    *,
    now: datetime | None = None,
) -> datetime:
    """Staff say the work was delivered. Idempotent: the first time stays."""
    if staff_user_id is None:
        raise _refuse("a staff member must mark delivery")
    await _row(session, scope, doc_id)
    stamp = now or datetime.now(UTC)
    current = await session.scalar(
        select(PiBrainDocument.delivered_at).where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.id == doc_id,
        )
    )
    if current is not None:
        return current
    await session.execute(
        update(PiBrainDocument)
        .where(
            PiBrainDocument.tenant_id == scope.tenant_id,
            PiBrainDocument.environment_id == scope.environment_id,
            PiBrainDocument.id == doc_id,
            PiBrainDocument.delivered_at.is_(None),
        )
        .values(delivered_at=stamp)
    )
    return stamp


async def mark_verified(
    session: AsyncSession,
    scope: WorkspaceScope,
    doc_id: UUID,
    staff_user_id: UUID | None,
    *,
    now: datetime | None = None,
) -> datetime:
    """Staff verified the delivery (Level 3 evidence). Needs `delivered_at` first."""
    if staff_user_id is None:
        raise _refuse("a staff member must verify delivery")
    await _row(session, scope, doc_id)
    where = (
        PiBrainDocument.tenant_id == scope.tenant_id,
        PiBrainDocument.environment_id == scope.environment_id,
        PiBrainDocument.id == doc_id,
    )
    delivered, verified = (
        await session.execute(
            select(PiBrainDocument.delivered_at, PiBrainDocument.verified_at).where(*where)
        )
    ).one()
    if delivered is None:
        raise _refuse("mark the work delivered before verifying it")
    if verified is not None:
        return verified  # type: ignore[no-any-return]
    stamp = now or datetime.now(UTC)
    await session.execute(
        update(PiBrainDocument).where(*where).values(verified_at=stamp, verified_by=staff_user_id)
    )
    return stamp
