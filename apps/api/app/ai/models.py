from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args


class AIUsageEvent(WorkspaceRow):
    """One provider attempt through the AI gateway (success, fallback or failure)."""

    __tablename__ = "ai_usage_events"
    __table_args__ = workspace_args(
        "ai_usage_events",
        CheckConstraint("status IN ('success', 'failed')", name="status"),
        Index("ix_ai_usage_events_scope_created", "tenant_id", "environment_id", "created_at"),
        Index("ix_ai_usage_events_run", "tenant_id", "environment_id", "run_id"),
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    alias: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16))
    fallback: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    attempt: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    error_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
