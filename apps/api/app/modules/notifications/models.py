from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow, WorkspaceRow, workspace_args


class Notification(WorkspaceRow):
    """Delivered to one user, or to every member holding required_permission."""

    __tablename__ = "notifications"
    __table_args__ = workspace_args(
        "notifications",
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="severity"),
        CheckConstraint(
            "recipient_user_id IS NOT NULL OR required_permission IS NOT NULL", name="audience"
        ),
        Index(
            "uq_notifications_dedupe",
            "tenant_id",
            "environment_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_notifications_scope_created", "tenant_id", "environment_id", "created_at"),
    )
    recipient_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=True
    )
    required_permission: Mapped[str | None] = mapped_column(String(60), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="info", server_default="info")
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(500), default="", server_default="")
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)


class NotificationRead(TenantRow):
    __tablename__ = "notification_reads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            ondelete="CASCADE",
            name="fk_notification_reads_notification",
        ),
        UniqueConstraint("notification_id", "user_id", name="uq_notification_reads_entry"),
    )
    notification_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
