from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args


class WorkspaceAgentAction(WorkspaceRow):
    __tablename__ = "workspace_agent_actions"
    __table_args__ = workspace_args(
        __tablename__,
        CheckConstraint("status IN ('pending', 'applied', 'cancelled')", name="status"),
        Index("ix_workspace_agent_actions_owner", "tenant_id", "environment_id", "user_id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="RESTRICT"))
    operation: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    required_permissions: Mapped[list[str]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class WorkspaceTask(WorkspaceRow):
    __tablename__ = "workspace_tasks"
    __table_args__ = workspace_args(
        __tablename__,
        ForeignKeyConstraint(
            ["tenant_id", "assignee_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="RESTRICT",
            name="fk_workspace_tasks_assignee",
        ),
        CheckConstraint("status IN ('todo', 'in_progress', 'done', 'cancelled')", name="status"),
        CheckConstraint("priority IN ('low', 'normal', 'high')", name="priority"),
        CheckConstraint("specialist IN ('operations', 'hr', 'finance', 'crm')", name="specialist"),
        Index("ix_workspace_tasks_scope_status", "tenant_id", "environment_id", "status"),
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="RESTRICT"))
    assignee_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    specialist: Mapped[str] = mapped_column(
        String(16), default="operations", server_default="operations"
    )
    status: Mapped[str] = mapped_column(String(16), default="todo", server_default="todo")
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
