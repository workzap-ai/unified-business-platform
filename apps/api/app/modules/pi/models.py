"""PI product data. All rows are tenant + environment scoped except raw webhook receipts,
which arrive before a tenant can be resolved and are linked once routing succeeds.

PI never duplicates business data: customers, products, stock, orders, quotes and
invoices stay in their modules and are reached only through controlled tools.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record, WorkspaceRow, scoped_fk, workspace_args


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


AGENT_KEYS = ("router", "customer_memory", "support", "requirement", "sales_order", "handoff")
HANDOFF_STATUSES = ("open", "assigned", "in_progress", "resolved", "closed")
HANDOFF_REASONS = (
    "customer_request",
    "low_confidence",
    "provider_failure",
    "policy",
    "tool_failure",
    "complaint",
    "sensitive",
    "manual",
)


class PiSettings(WorkspaceRow):
    __tablename__ = "pi_settings"
    __table_args__ = workspace_args(
        "pi_settings",
        UniqueConstraint("tenant_id", "environment_id", name="uq_pi_settings_scope"),
    )
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    business_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    response_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    provider_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tool_permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    handoff_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    knowledge_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    whatsapp_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PiAgent(WorkspaceRow):
    __tablename__ = "pi_agents"
    __table_args__ = workspace_args(
        "pi_agents",
        UniqueConstraint("tenant_id", "environment_id", "key", name="uq_pi_agents_key"),
        CheckConstraint(_in("key", AGENT_KEYS), name="key"),
    )
    key: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class PiAgentVersion(WorkspaceRow):
    __tablename__ = "pi_agent_versions"
    __table_args__ = workspace_args(
        "pi_agent_versions",
        scoped_fk("pi_agent_versions", "agent_id", "pi_agents"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "agent_id",
            "version",
            name="uq_pi_agent_versions_version",
        ),
        CheckConstraint("temperature >= 0 AND temperature <= 1", name="temperature_range"),
        CheckConstraint(_in("model_alias", ("fast", "balanced", "reasoning")), name="alias"),
    )
    agent_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    # Tenant guidance appended to the centralized prompt template; cannot replace rules.
    instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    model_alias: Mapped[str] = mapped_column(String(20))
    temperature: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    note: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_by_label: Mapped[str] = mapped_column(String(80))


class PiAgentTool(WorkspaceRow):
    __tablename__ = "pi_agent_tools"
    __table_args__ = workspace_args(
        "pi_agent_tools",
        scoped_fk("pi_agent_tools", "agent_id", "pi_agents"),
        UniqueConstraint(
            "tenant_id", "environment_id", "agent_id", "tool_key", name="uq_pi_agent_tools_entry"
        ),
    )
    agent_id: Mapped[UUID] = mapped_column(Uuid)
    tool_key: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class WhatsAppConnection(WorkspaceRow):
    __tablename__ = "whatsapp_connections"
    __table_args__ = workspace_args(
        "whatsapp_connections",
        # Globally unique: inbound webhooks are routed to a tenant by phone number id.
        UniqueConstraint("provider", "phone_number_id", name="uq_whatsapp_connections_number"),
        CheckConstraint(_in("status", ("pending", "active", "disabled", "error")), name="status"),
        CheckConstraint(_in("provider", ("meta_cloud",)), name="provider"),
        CheckConstraint("phone_number_id ~ '^[0-9]{5,32}$'", name="phone_number_id_format"),
    )
    provider: Mapped[str] = mapped_column(String(20), default="meta_cloud")
    phone_number_id: Mapped[str] = mapped_column(String(32))
    display_phone_number: Mapped[str] = mapped_column(String(32))
    business_account_id: Mapped[str] = mapped_column(String(32), default="", server_default="")
    display_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsAppWebhookEvent(Record, Base):
    """Raw receipt log for dedup/replay visibility. Tenant is linked after routing."""

    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_key", name="uq_whatsapp_webhook_events_key"),
        ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            ondelete="RESTRICT",
            name="fk_whatsapp_webhook_events_environment",
        ),
        CheckConstraint(_in("kind", ("message", "status", "unknown")), name="kind"),
        CheckConstraint(
            _in("status", ("received", "queued", "processed", "ignored", "failed")), name="status"
        ),
        Index(
            "ix_whatsapp_webhook_events_scope_created", "tenant_id", "environment_id", "created_at"
        ),
        Index("ix_whatsapp_webhook_events_status", "status", "created_at"),
    )
    provider: Mapped[str] = mapped_column(String(20))
    event_key: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="received", server_default="received")
    tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True
    )
    environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    connection_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    phone_number_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiConversation(WorkspaceRow):
    __tablename__ = "pi_conversations"
    __table_args__ = workspace_args(
        "pi_conversations",
        scoped_fk("pi_conversations", "customer_id", "customers"),
        scoped_fk("pi_conversations", "connection_id", "whatsapp_connections"),
        CheckConstraint(_in("status", ("open", "closed")), name="status"),
        CheckConstraint(_in("mode", ("ai", "human")), name="mode"),
        CheckConstraint("unread_count >= 0", name="unread_nonnegative"),
        Index(
            "uq_pi_conversations_open_contact",
            "tenant_id",
            "environment_id",
            "connection_id",
            "contact_wa_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_pi_conversations_scope_last", "tenant_id", "environment_id", "last_message_at"),
        Index("ix_pi_conversations_customer", "tenant_id", "environment_id", "customer_id"),
        Index("ix_pi_conversations_followup_due", "followup_due_at"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp", server_default="whatsapp")
    contact_wa_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    mode: Mapped[str] = mapped_column(String(16), default="ai", server_default="ai")
    assigned_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_preview: Mapped[str] = mapped_column(String(200), default="", server_default="")
    unread_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    summary_message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    service_brief: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    followup_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    clarification_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class PiMessage(WorkspaceRow):
    __tablename__ = "pi_messages"
    __table_args__ = workspace_args(
        "pi_messages",
        scoped_fk("pi_messages", "conversation_id", "pi_conversations"),
        CheckConstraint(_in("direction", ("inbound", "outbound")), name="direction"),
        CheckConstraint(_in("sender_type", ("customer", "ai", "human", "system")), name="sender"),
        CheckConstraint(
            _in("message_type", ("text", "audio", "image", "video", "interactive", "other")),
            name="type",
        ),
        CheckConstraint(
            _in(
                "status",
                (
                    "received",
                    "processing",
                    "processed",
                    "skipped",
                    "failed",
                    "queued",
                    "sent",
                    "delivered",
                    "read",
                ),
            ),
            name="status",
        ),
        Index(
            "uq_pi_messages_provider_id",
            "tenant_id",
            "environment_id",
            "provider_message_id",
            unique=True,
            postgresql_where=text("provider_message_id IS NOT NULL"),
        ),
        Index(
            "uq_pi_messages_idempotency",
            "tenant_id",
            "environment_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_pi_messages_conversation",
            "tenant_id",
            "environment_id",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_pi_messages_body_trgm",
            "body",
            postgresql_using="gin",
            postgresql_ops={"body": "gin_trgm_ops"},
        ),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    direction: Mapped[str] = mapped_column(String(16))
    sender_type: Mapped[str] = mapped_column(String(16))
    message_type: Mapped[str] = mapped_column(String(16), default="text", server_default="text")
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    media: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    provider_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    sent_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    sent_by_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiAgentRun(WorkspaceRow):
    __tablename__ = "pi_agent_runs"
    __table_args__ = workspace_args(
        "pi_agent_runs",
        scoped_fk("pi_agent_runs", "conversation_id", "pi_conversations"),
        scoped_fk("pi_agent_runs", "message_id", "pi_messages"),
        # Exactly one run per inbound message: retries cannot double-process.
        UniqueConstraint(
            "tenant_id", "environment_id", "message_id", name="uq_pi_agent_runs_message"
        ),
        CheckConstraint(
            _in("status", ("running", "completed", "failed", "handoff", "skipped")), name="status"
        ),
        CheckConstraint("transfers >= 0 AND transfers <= 3", name="transfer_limit"),
        Index("ix_pi_agent_runs_scope_created", "tenant_id", "environment_id", "created_at"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    message_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    agent_path: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    transfers: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiToolCall(WorkspaceRow):
    __tablename__ = "pi_tool_calls"
    __table_args__ = workspace_args(
        "pi_tool_calls",
        scoped_fk("pi_tool_calls", "run_id", "pi_agent_runs"),
        CheckConstraint(
            _in("status", ("success", "denied", "invalid", "error", "confirmation_required")),
            name="status",
        ),
        Index("ix_pi_tool_calls_scope_created", "tenant_id", "environment_id", "created_at"),
        Index("ix_pi_tool_calls_run", "tenant_id", "environment_id", "run_id"),
    )
    run_id: Mapped[UUID] = mapped_column(Uuid)
    agent_key: Mapped[str] = mapped_column(String(32))
    tool_key: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(24))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PiPendingAction(WorkspaceRow):
    """A draft awaiting explicit customer confirmation. Never auto-executed."""

    __tablename__ = "pi_pending_actions"
    __table_args__ = workspace_args(
        "pi_pending_actions",
        scoped_fk("pi_pending_actions", "conversation_id", "pi_conversations"),
        CheckConstraint(_in("kind", ("confirm_order",)), name="kind"),
        CheckConstraint(
            _in("status", ("pending", "confirmed", "cancelled", "expired", "failed")), name="status"
        ),
        Index(
            "uq_pi_pending_actions_one_pending",
            "tenant_id",
            "environment_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiHandoff(WorkspaceRow):
    __tablename__ = "pi_handoffs"
    __table_args__ = workspace_args(
        "pi_handoffs",
        scoped_fk("pi_handoffs", "conversation_id", "pi_conversations"),
        scoped_fk("pi_handoffs", "customer_id", "customers"),
        CheckConstraint(_in("status", HANDOFF_STATUSES), name="status"),
        CheckConstraint(_in("reason", HANDOFF_REASONS), name="reason"),
        CheckConstraint(_in("priority", ("normal", "high", "urgent")), name="priority"),
        Index(
            "uq_pi_handoffs_one_active",
            "tenant_id",
            "environment_id",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'assigned', 'in_progress')"),
        ),
        Index("ix_pi_handoffs_scope_status", "tenant_id", "environment_id", "status", "created_at"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    reason: Mapped[str] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(16), default="normal", server_default="normal")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    assigned_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assigned_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80))
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str] = mapped_column(String(500), default="", server_default="")


class PiMemory(WorkspaceRow):
    """Useful long-term customer facts only (preferences, recurring needs)."""

    __tablename__ = "pi_memories"
    __table_args__ = workspace_args(
        "pi_memories",
        scoped_fk("pi_memories", "customer_id", "customers"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "customer_id",
            "content_hash",
            name="uq_pi_memories_entry",
        ),
        CheckConstraint(_in("kind", ("preference", "requirement", "context")), name="kind"),
        CheckConstraint(_in("status", ("active", "archived")), name="status"),
        Index("ix_pi_memories_customer", "tenant_id", "environment_id", "customer_id", "status"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeSource(WorkspaceRow):
    __tablename__ = "knowledge_sources"
    __table_args__ = workspace_args(
        "knowledge_sources",
        CheckConstraint(
            _in("kind", ("company_info", "faq", "policy", "catalog", "approved_answer", "file")),
            name="kind",
        ),
        CheckConstraint(_in("status", ("active", "disabled")), name="status"),
    )
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")


class KnowledgeDocument(WorkspaceRow):
    __tablename__ = "knowledge_documents"
    __table_args__ = workspace_args(
        "knowledge_documents",
        scoped_fk("knowledge_documents", "source_id", "knowledge_sources"),
        CheckConstraint(_in("status", ("pending", "processing", "ready", "failed")), name="status"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "source_id",
            "content_hash",
            name="uq_knowledge_documents_content",
        ),
        Index("ix_knowledge_documents_source", "tenant_id", "environment_id", "source_id"),
    )
    source_id: Mapped[UUID] = mapped_column(Uuid)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(60), default="text/plain")
    byte_size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(WorkspaceRow):
    __tablename__ = "knowledge_chunks"
    __table_args__ = workspace_args(
        "knowledge_chunks",
        scoped_fk("knowledge_chunks", "document_id", "knowledge_documents"),
        scoped_fk("knowledge_chunks", "source_id", "knowledge_sources"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "document_id",
            "ordinal",
            name="uq_knowledge_chunks_ordinal",
        ),
        Index("ix_knowledge_chunks_search", "search_vector", postgresql_using="gin"),
        Index("ix_knowledge_chunks_scope", "tenant_id", "environment_id", "source_id"),
    )
    document_id: Mapped[UUID] = mapped_column(Uuid)
    source_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    # 'simple' config: no language stemming, which suits mixed English/Roman Urdu text.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True)
    )
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Portable storage; optional pgvector cosine operations are enabled by the operator.
    embedding_values: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
