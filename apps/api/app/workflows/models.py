from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args


class WorkflowRun(WorkspaceRow):
    __tablename__ = "workflow_runs"
    __table_args__ = workspace_args(
        "workflow_runs",
        UniqueConstraint(
            "tenant_id", "environment_id", "idempotency_key", name="uq_workflow_runs_key"
        ),
        CheckConstraint(
            "status IN ('pending_approval', 'completed', 'failed', 'rejected')", name="status"
        ),
    )
    tool_key: Mapped[str] = mapped_column(String(80))
    action_class: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    requested_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
