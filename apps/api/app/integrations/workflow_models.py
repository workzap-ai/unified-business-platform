"""Durable, workspace-scoped integration routing and business operations."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


class IntegrationWorkflow(WorkspaceRow):
    __tablename__ = "integration_workflows"
    __table_args__ = workspace_args(
        __tablename__,
        scoped_fk(__tablename__, "connection_id", "integration_connections"),
        UniqueConstraint("connection_id", name="uq_integration_workflows_connection"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    event_types: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    recipients: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    # Only events produced after enablement are eligible; old business events are never sent.
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntegrationOperation(WorkspaceRow):
    __tablename__ = "integration_operations"
    __table_args__ = workspace_args(
        __tablename__,
        scoped_fk(__tablename__, "connection_id", "integration_connections"),
        scoped_fk(__tablename__, "outbox_event_id", "outbox_events"),
        UniqueConstraint(
            "tenant_id", "environment_id", "dedupe_key", name="uq_integration_operations_dedupe"
        ),
        UniqueConstraint(
            "connection_id", "kind", "external_id", name="uq_integration_operations_external"
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','needs_review','cancelled')",
            name="status",
        ),
        CheckConstraint("kind IN ('notification','file','checkout')", name="kind"),
        Index("ix_integration_operations_due", "kind", "status", "next_attempt_at"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    outbox_event_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
