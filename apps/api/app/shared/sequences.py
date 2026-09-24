from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args
from app.shared.scope import WorkspaceScope


class DocumentSequence(WorkspaceRow):
    __tablename__ = "document_sequences"
    __table_args__ = workspace_args(
        "document_sequences",
        UniqueConstraint("tenant_id", "environment_id", "kind", name="uq_document_sequences_kind"),
        CheckConstraint("next_value > 0", name="next_positive"),
    )
    kind: Mapped[str] = mapped_column(String(32))
    next_value: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


PREFIXES = {"order": "ORD", "quote": "QUO", "invoice": "INV", "payment": "PAY", "expense": "EXP"}


async def next_number(session: AsyncSession, scope: WorkspaceScope, kind: str) -> str:
    """Collision-free numbering: the row lock serializes concurrent callers."""
    await session.execute(
        insert(DocumentSequence)
        .values(tenant_id=scope.tenant_id, environment_id=scope.environment_id, kind=kind)
        .on_conflict_do_nothing(constraint="uq_document_sequences_kind")
    )
    row = await session.scalar(
        select(DocumentSequence)
        .where(
            DocumentSequence.tenant_id == scope.tenant_id,
            DocumentSequence.environment_id == scope.environment_id,
            DocumentSequence.kind == kind,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:  # pragma: no cover - the insert above guarantees presence
        raise RuntimeError("Sequence unavailable")
    value = row.next_value
    row.next_value = value + 1
    await session.flush()
    return f"{PREFIXES.get(kind, kind.upper()[:3])}-{value:06d}"
