from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


class Customer(WorkspaceRow):
    __tablename__ = "customers"
    __table_args__ = workspace_args(
        "customers",
        CheckConstraint("status IN ('active', 'archived')", name="status"),
        CheckConstraint("source IN ('manual', 'whatsapp', 'import')", name="source"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        CheckConstraint("phone IS NULL OR phone ~ '^\\+[0-9]{7,15}$'", name="phone_e164"),
        Index(
            "uq_customers_phone",
            "tenant_id",
            "environment_id",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        Index(
            "uq_customers_whatsapp",
            "tenant_id",
            "environment_id",
            "whatsapp_id",
            unique=True,
            postgresql_where=text("whatsapp_id IS NOT NULL"),
        ),
        Index("ix_customers_scope_created", "tenant_id", "environment_id", "created_at"),
        Index(
            "ix_customers_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    whatsapp_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CustomerNote(WorkspaceRow):
    __tablename__ = "customer_notes"
    __table_args__ = workspace_args(
        "customer_notes",
        scoped_fk("customer_notes", "customer_id", "customers"),
        CheckConstraint("length(btrim(body)) > 0", name="body_nonempty"),
        Index("ix_customer_notes_customer", "tenant_id", "environment_id", "customer_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    author_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    author_label: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)


class CustomerActivity(WorkspaceRow):
    __tablename__ = "customer_activities"
    __table_args__ = workspace_args(
        "customer_activities",
        scoped_fk("customer_activities", "customer_id", "customers"),
        Index(
            "ix_customer_activities_customer",
            "tenant_id",
            "environment_id",
            "customer_id",
            "created_at",
        ),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(240))
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(80))


FILE_SOURCES = ("whatsapp", "upload", "receipt")


class CustomerFile(WorkspaceRow):
    """A file kept for a customer in the database: documents and photos they send on
    WhatsApp, files the team uploads, and receipts. Bytes are deferred: lists never load
    them, only a download does."""

    __tablename__ = "customer_files"
    __table_args__ = workspace_args(
        "customer_files",
        scoped_fk("customer_files", "customer_id", "customers"),
        CheckConstraint("source IN ('whatsapp', 'upload', 'receipt')", name="source"),
        CheckConstraint("size > 0 AND size <= 26214400", name="size_range"),
        Index(
            "ix_customer_files_customer", "tenant_id", "environment_id", "customer_id", "created_at"
        ),
        # One saved file per WhatsApp message, however often the message is processed.
        Index(
            "uq_customer_files_message",
            "tenant_id",
            "environment_id",
            "message_id",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        Index("ix_customer_files_ref", "tenant_id", "environment_id", "ref_type", "ref_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    # What the file belongs to besides the customer (e.g. a receipt's invoice).
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    uploaded_by_label: Mapped[str] = mapped_column(String(80))
