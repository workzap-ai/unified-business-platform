from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record


class AuditEvent(Record, Base):
    """Append-only structured audit record. Details are redacted before insert."""

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            ondelete="RESTRICT",
            name="fk_audit_events_environment",
        ),
        CheckConstraint("actor_type IN ('user', 'system', 'anonymous')", name="actor_type"),
        CheckConstraint("outcome IN ('success', 'denied', 'failure')", name="outcome"),
        Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_events_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_events_actor_created", "actor_user_id", "created_at"),
    )
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True
    )
    environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_label: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success", server_default="success")
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
