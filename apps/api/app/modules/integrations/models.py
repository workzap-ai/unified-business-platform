"""Integration platform tables. All are environment-scoped (ADR 0005): a sandbox
connection, its events and its keys can never reach another environment or tenant, and
child rows reference parents through (tenant_id, environment_id, id).
"""

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
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

CONNECTION_STATUSES = (
    "draft",
    "connecting",
    "connected",
    "degraded",
    "expired",
    "revoked",
    "disabled",
    "error",
)
EVENT_STATUSES = (
    "received",
    "queued",
    "processing",
    "processed",
    "ignored",
    "failed",
    "dead_letter",
)
JOB_STATUSES = ("pending", "running", "succeeded", "failed", "dead_letter", "cancelled", "paused")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _ts(nullable: bool = True) -> Any:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class IntegrationConnection(WorkspaceRow):
    __tablename__ = "integration_connections"
    __table_args__ = workspace_args(
        "integration_connections",
        CheckConstraint(_in("status", CONNECTION_STATUSES), name="status"),
        CheckConstraint("mode IN ('sandbox', 'production')", name="mode"),
        CheckConstraint("health IN ('healthy', 'degraded', 'failing', 'unknown')", name="health"),
        CheckConstraint("circuit_state IN ('closed', 'open', 'half_open')", name="circuit_state"),
        CheckConstraint(
            "sync_direction IN ('none', 'pull', 'push', 'bidirectional')", name="sync_direction"
        ),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_nonempty"),
        Index(
            "ix_integration_connections_scope_key", "tenant_id", "environment_id", "integration_key"
        ),
        Index(
            "uq_integration_connections_webhook_token",
            "webhook_token_hash",
            unique=True,
            postgresql_where=text("webhook_token_hash IS NOT NULL"),
        ),
    )
    integration_key: Mapped[str] = mapped_column(String(60))
    display_name: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_hints: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
    sync_direction: Mapped[str] = mapped_column(String(16), default="none", server_default="none")
    health: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    circuit_state: Mapped[str] = mapped_column(
        String(16), default="closed", server_default="closed"
    )
    circuit_failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    circuit_opened_at: Mapped[datetime | None] = _ts()
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_success_at: Mapped[datetime | None] = _ts()
    last_failure_at: Mapped[datetime | None] = _ts()
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_health_check_at: Mapped[datetime | None] = _ts()
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limited_until: Mapped[datetime | None] = _ts()
    connected_at: Mapped[datetime | None] = _ts()
    expires_at: Mapped[datetime | None] = _ts()
    disabled_at: Mapped[datetime | None] = _ts()
    revoked_at: Mapped[datetime | None] = _ts()
    webhook_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class IntegrationActivity(WorkspaceRow):
    __tablename__ = "integration_activities"
    __table_args__ = workspace_args(
        "integration_activities",
        scoped_fk("integration_activities", "connection_id", "integration_connections"),
        CheckConstraint("outcome IN ('success', 'failure', 'info')", name="outcome"),
        Index(
            "ix_integration_activities_connection",
            "tenant_id",
            "environment_id",
            "connection_id",
            "created_at",
        ),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(300))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OAuthState(WorkspaceRow):
    __tablename__ = "integration_oauth_states"
    __table_args__ = workspace_args(
        "integration_oauth_states",
        scoped_fk("integration_oauth_states", "connection_id", "integration_connections"),
        UniqueConstraint("state_hash", name="uq_integration_oauth_states_state_hash"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    state_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[UUID] = mapped_column(Uuid)
    code_verifier_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_uri: Mapped[str] = mapped_column(String(500))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = _ts()


class InboundEvent(WorkspaceRow):
    __tablename__ = "integration_inbound_events"
    __table_args__ = workspace_args(
        "integration_inbound_events",
        scoped_fk("integration_inbound_events", "connection_id", "integration_connections"),
        UniqueConstraint(
            "connection_id",
            "provider_event_id",
            name="uq_integration_inbound_events_provider_event",
        ),
        CheckConstraint(_in("status", EVENT_STATUSES), name="status"),
        Index(
            "ix_integration_inbound_events_scope_status",
            "tenant_id",
            "environment_id",
            "status",
            "received_at",
        ),
        Index("ix_integration_inbound_events_received", "received_at"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    integration_key: Mapped[str] = mapped_column(String(60))
    provider_event_id: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="received", server_default="received")
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    payload_truncated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = _ts()
    next_attempt_at: Mapped[datetime | None] = _ts()
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class OutboxEvent(WorkspaceRow):
    __tablename__ = "outbox_events"
    __table_args__ = workspace_args(
        "outbox_events",
        CheckConstraint("status IN ('pending', 'dispatched', 'failed')", name="status"),
        Index("ix_outbox_events_pending", "status", "available_at"),
        Index("ix_outbox_events_scope_created", "tenant_id", "environment_id", "created_at"),
    )
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = _ts()
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    origin: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))


class WebhookSubscription(WorkspaceRow):
    __tablename__ = "integration_webhook_subscriptions"
    __table_args__ = workspace_args(
        "integration_webhook_subscriptions",
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        Index(
            "ix_integration_webhook_subscriptions_scope", "tenant_id", "environment_id", "enabled"
        ),
    )
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2048))
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)), default=list, server_default="{}"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    secret_encrypted: Mapped[str] = mapped_column(Text)
    secret_hint: Mapped[str] = mapped_column(String(8))
    last_delivery_at: Mapped[datetime | None] = _ts()
    last_delivery_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    deleted_at: Mapped[datetime | None] = _ts()
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class Delivery(WorkspaceRow):
    __tablename__ = "integration_deliveries"
    __table_args__ = workspace_args(
        "integration_deliveries",
        scoped_fk("integration_deliveries", "subscription_id", "integration_webhook_subscriptions"),
        scoped_fk("integration_deliveries", "outbox_event_id", "outbox_events"),
        UniqueConstraint(
            "subscription_id", "outbox_event_id", name="uq_integration_deliveries_event"
        ),
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        Index("ix_integration_deliveries_due", "status", "next_attempt_at"),
        Index(
            "ix_integration_deliveries_subscription",
            "tenant_id",
            "environment_id",
            "subscription_id",
            "created_at",
        ),
    )
    subscription_id: Mapped[UUID] = mapped_column(Uuid)
    outbox_event_id: Mapped[UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt_at: Mapped[datetime | None] = _ts()
    delivered_at: Mapped[datetime | None] = _ts()
    idempotency_key: Mapped[str] = mapped_column(String(120))


class SyncJob(WorkspaceRow):
    __tablename__ = "integration_sync_jobs"
    __table_args__ = workspace_args(
        "integration_sync_jobs",
        scoped_fk("integration_sync_jobs", "connection_id", "integration_connections"),
        CheckConstraint(_in("status", JOB_STATUSES), name="status"),
        CheckConstraint("mode IN ('incremental', 'full')", name="mode"),
        CheckConstraint("direction IN ('pull', 'push', 'bidirectional')", name="direction"),
        Index(
            "uq_integration_sync_jobs_active",
            "connection_id",
            "entity",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
        Index("ix_integration_sync_jobs_scope", "tenant_id", "environment_id", "created_at"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    integration_key: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    cursor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    started_at: Mapped[datetime | None] = _ts()
    finished_at: Mapped[datetime | None] = _ts()
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    requested_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class SyncCursor(WorkspaceRow):
    __tablename__ = "integration_sync_cursors"
    __table_args__ = workspace_args(
        "integration_sync_cursors",
        scoped_fk("integration_sync_cursors", "connection_id", "integration_connections"),
        UniqueConstraint("connection_id", "entity", name="uq_integration_sync_cursors_entity"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    entity: Mapped[str] = mapped_column(String(40))
    cursor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_success_at: Mapped[datetime | None] = _ts()


class SyncAttempt(WorkspaceRow):
    __tablename__ = "integration_sync_attempts"
    __table_args__ = workspace_args(
        "integration_sync_attempts",
        scoped_fk("integration_sync_attempts", "job_id", "integration_sync_jobs"),
        UniqueConstraint("job_id", "attempt", name="uq_integration_sync_attempts_attempt"),
    )
    job_id: Mapped[UUID] = mapped_column(Uuid)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = _ts()
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class SyncConflict(WorkspaceRow):
    __tablename__ = "integration_sync_conflicts"
    __table_args__ = workspace_args(
        "integration_sync_conflicts",
        scoped_fk("integration_sync_conflicts", "job_id", "integration_sync_jobs"),
        scoped_fk("integration_sync_conflicts", "connection_id", "integration_connections"),
        CheckConstraint("status IN ('open', 'resolved', 'ignored')", name="status"),
    )
    job_id: Mapped[UUID] = mapped_column(Uuid)
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    entity: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class ExternalReference(WorkspaceRow):
    __tablename__ = "integration_external_refs"
    __table_args__ = workspace_args(
        "integration_external_refs",
        scoped_fk("integration_external_refs", "connection_id", "integration_connections"),
        UniqueConstraint(
            "connection_id", "entity", "external_id", name="uq_integration_external_refs_external"
        ),
        CheckConstraint("last_write_origin IN ('provider', 'platform')", name="origin"),
    )
    connection_id: Mapped[UUID] = mapped_column(Uuid)
    entity: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(200))
    platform_entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    last_write_origin: Mapped[str] = mapped_column(String(16))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApiKey(WorkspaceRow):
    __tablename__ = "api_keys"
    __table_args__ = workspace_args(
        "api_keys",
        UniqueConstraint("prefix", name="uq_api_keys_prefix"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        Index("ix_api_keys_scope", "tenant_id", "environment_id", "created_at"),
    )
    name: Mapped[str] = mapped_column(String(120))
    prefix: Mapped[str] = mapped_column(String(40))
    secret_hash: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(60)), default=list, server_default="{}")
    expires_at: Mapped[datetime | None] = _ts()
    revoked_at: Mapped[datetime | None] = _ts()
    last_used_at: Mapped[datetime | None] = _ts()
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_membership_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
