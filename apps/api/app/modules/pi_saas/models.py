"""Pi SaaS data. Account/billing rows are tenant-scoped (one Pi business = one tenant);
connections, usage and domain records that differ between test and production are
tenant + environment scoped. Operator rows are platform-level and never grant tenant data
access by themselves: customer-content access needs an explicit support grant.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record, TenantRow, WorkspaceRow, scoped_fk, workspace_args


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


SETUP_STATES = (
    "draft",
    "awaiting_connection",
    "pending_approval",
    "ready",
    "active",
    "paused",
    "action_required",
)
OFFER_TYPES = ("services", "products", "both")
AUTOMATION_MODES = ("human_approved", "mixed", "ai_led")
SUBSCRIPTION_STATES = ("trialing", "active", "past_due", "canceled", "suspended")
OPERATOR_ROLES = (
    "owner",
    "operations_admin",
    "onboarding_specialist",
    "support",
    "billing",
    "analyst",
)
GRANT_SCOPES = ("configuration", "conversations", "full_support")
USAGE_METRICS = (
    "messages_in",
    "messages_out",
    "template_messages",
    "ai_tokens",
    "ai_cost",
    "media_items",
    "media_seconds",
    "storage_bytes",
)


class PiPlan(Record, Base):
    """Commercial plan. Prices are operator-configured; a plan without a price cannot be
    purchased through checkout (it can be granted manually by an operator)."""

    __tablename__ = "pi_plans"
    __table_args__ = (
        CheckConstraint(_in("status", ("draft", "available", "retired")), name="status"),
        CheckConstraint(_in("visibility", ("public", "private")), name="visibility"),
        CheckConstraint("monthly_price IS NULL OR monthly_price >= 0", name="price_nonnegative"),
        CheckConstraint(
            "manual_monthly_price_pkr IS NULL OR manual_monthly_price_pkr > 0",
            name="manual_price_positive",
        ),
    )
    key: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    monthly_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    trial_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    # {"messages": 1000, "ai_tokens": ..., "media_items": ..., "storage_mb": ..., "seats": 3,
    #  "numbers": 1}. Null value = not included; absent = no separate limit.
    allowances: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    features: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), default=list, server_default="{}"
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # "private" plans are never listed to businesses; only an operator assigns them
    # (e.g. a free plan for partners).
    visibility: Mapped[str] = mapped_column(String(16), default="public", server_default="public")
    manual_monthly_price_pkr: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class PiBusinessAccount(TenantRow):
    """The customer-facing business. Maps to exactly one tenant and its environments."""

    __tablename__ = "pi_business_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_pi_business_accounts_tenant"),
        CheckConstraint(_in("setup_state", SETUP_STATES), name="setup_state"),
        CheckConstraint(_in("offer_type", OFFER_TYPES), name="offer_type"),
        CheckConstraint(_in("automation_mode", AUTOMATION_MODES), name="automation_mode"),
        CheckConstraint(_in("status", ("active", "suspended", "closed")), name="status"),
        CheckConstraint("onboarding_step BETWEEN 1 AND 5", name="onboarding_step"),
    )
    name: Mapped[str] = mapped_column(String(160))
    business_category: Mapped[str] = mapped_column(String(60), default="", server_default="")
    language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    country: Mapped[str] = mapped_column(String(2), default="", server_default="")
    website: Mapped[str] = mapped_column(String(300), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    offer_type: Mapped[str] = mapped_column(
        String(16), default="services", server_default="services"
    )
    goals: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, server_default="{}")
    automation_mode: Mapped[str] = mapped_column(
        String(20), default="human_approved", server_default="human_approved"
    )
    setup_state: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    onboarding_step: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    onboarding_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    production_environment_id: Mapped[UUID] = mapped_column(Uuid)
    test_environment_id: Mapped[UUID] = mapped_column(Uuid)
    help_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Weekly summary by email to the owner, only when they turn it on (in-app always).
    digest_email: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # True when the suspension came from suspending the whole workspace, so reactivating
    # the workspace only undoes its own suspension (never a separate business one).
    suspended_by_workspace: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Email on/off per notification category ({"verification": true, ...}); in-app is
    # always on. Missing categories use lifecycle_notify.EMAIL_DEFAULTS.
    notification_prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    # Last lifecycle facts notified about (gate reason, subscription status, plan), so the
    # sweep only reacts to real changes, whichever code path made them.
    lifecycle_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}"
    )
    lifecycle_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PiSubscription(TenantRow):
    """The business's own Pi subscription (not payments from its WhatsApp customers)."""

    __tablename__ = "pi_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_pi_subscriptions_tenant"),
        CheckConstraint(_in("status", SUBSCRIPTION_STATES), name="status"),
        CheckConstraint(_in("billing_provider", ("manual", "stripe")), name="billing_provider"),
        CheckConstraint("spend_limit IS NULL OR spend_limit >= 0", name="spend_limit"),
        Index("ix_pi_subscriptions_external", "external_subscription_id"),
    )
    plan_key: Mapped[str] = mapped_column(ForeignKey("pi_plans.key", ondelete="RESTRICT"))
    pending_plan_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="trialing", server_default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_provider: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual"
    )
    external_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    spend_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Staged dunning reminders while past_due (0 = none sent yet; see billing.DUNNING_STAGES).
    dunning_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    dunning_last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PiPlatformInvoice(TenantRow):
    """Invoices for the Pi subscription, mirrored from the billing provider."""

    __tablename__ = "pi_platform_invoices"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_pi_platform_invoices_external"),
        CheckConstraint(
            _in("status", ("draft", "open", "paid", "void", "uncollectible")), name="status"
        ),
    )
    number: Mapped[str] = mapped_column(String(60), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16))
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3))
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hosted_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiBillingEvent(Record, Base):
    """Verified billing-provider webhook receipts (deduplicated by provider event id)."""

    __tablename__ = "pi_billing_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_pi_billing_events_event"),
        CheckConstraint(
            _in("status", ("received", "processed", "ignored", "failed")), name="status"
        ),
    )
    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(80))
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="received", server_default="received")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PiUsageCounter(WorkspaceRow):
    """Metered usage per environment and UTC month. Test-environment usage is recorded
    separately and never counted against production allowances."""

    __tablename__ = "pi_usage_counters"
    __table_args__ = workspace_args(
        "pi_usage_counters",
        UniqueConstraint(
            "tenant_id", "environment_id", "period", "metric", name="uq_pi_usage_counters_metric"
        ),
        CheckConstraint(_in("metric", USAGE_METRICS), name="metric"),
    )
    period: Mapped[date] = mapped_column(Date)
    metric: Mapped[str] = mapped_column(String(24))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), default=0, server_default="0")


class PiProviderConnection(WorkspaceRow):
    """A business's WhatsApp provider onboarding record (Kapso or direct Meta).

    The provider project key is server-held configuration, never stored here; this row
    only holds the business's own provider customer id, setup state and number mapping.
    Once connected it is linked to a ``whatsapp_connections`` row, which routes inbound
    events into the shared PI pipeline.
    """

    __tablename__ = "pi_provider_connections"
    __table_args__ = workspace_args(
        "pi_provider_connections",
        scoped_fk("pi_provider_connections", "whatsapp_connection_id", "whatsapp_connections"),
        CheckConstraint(_in("provider", ("kapso", "meta_cloud")), name="provider"),
        CheckConstraint(
            _in(
                "status",
                ("draft", "setup_pending", "connected", "action_required", "disconnected"),
            ),
            name="status",
        ),
        CheckConstraint(
            "connection_type IS NULL OR connection_type IN ('coexistence', 'dedicated')",
            name="connection_type",
        ),
        Index("ix_pi_provider_connections_number", "provider", "phone_number_id"),
    )
    provider: Mapped[str] = mapped_column(String(16), default="kapso", server_default="kapso")
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    external_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    setup_link_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    setup_link_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    setup_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    setup_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    connection_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone_number_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_account_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    whatsapp_connection_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    health: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    health_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # A request for a new number: country, notes and the customer's explicit confirmation
    # of any rental/deposit shown by the provider. Nothing is purchased automatically.
    number_request: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PiProviderEvent(Record, Base):
    """Verified provider webhook receipts (project and connection lifecycle events)."""

    __tablename__ = "pi_provider_events"
    __table_args__ = (
        UniqueConstraint("provider", "idempotency_key", name="uq_pi_provider_events_key"),
        CheckConstraint(
            _in("status", ("received", "processed", "ignored", "failed")), name="status"
        ),
    )
    provider: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(80))
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="received", server_default="received")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PiOperatorMember(Record, Base):
    """Platform operator team member (Owner OS side). Grants operator capabilities over
    Pi business *operations*; never implicit access to customer conversations."""

    __tablename__ = "pi_operator_members"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_pi_operator_members_user"),
        CheckConstraint(_in("role", OPERATOR_ROLES), name="role"),
        CheckConstraint(_in("status", ("active", "revoked")), name="status"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    # Extra capabilities beyond the role preset, or removed ones ("-capability").
    overrides: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, server_default="{}"
    )
    added_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiOperatorAssignment(Record, Base):
    """Accounts an operator is assigned to (roles limited to assigned accounts)."""

    __tablename__ = "pi_operator_assignments"
    __table_args__ = (
        UniqueConstraint("operator_id", "tenant_id", name="uq_pi_operator_assignments_entry"),
    )
    operator_id: Mapped[UUID] = mapped_column(
        ForeignKey("pi_operator_members.id", ondelete="CASCADE")
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))


class PiSupportGrant(TenantRow):
    """Time-limited, revocable operator access to one business, granted by the business.

    ``configuration`` lets an operator prepare settings/knowledge; ``conversations`` adds
    reading customer conversations; ``full_support`` adds replying. Every use is audited.
    """

    __tablename__ = "pi_support_grants"
    __table_args__ = (
        CheckConstraint(_in("scope", GRANT_SCOPES), name="scope"),
        CheckConstraint(
            _in("status", ("requested", "active", "revoked", "expired", "declined")),
            name="status",
        ),
        Index("ix_pi_support_grants_operator", "operator_user_id", "status"),
    )
    operator_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    scope: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), default="requested", server_default="requested")
    reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    requested_by: Mapped[str] = mapped_column(String(16), default="client", server_default="client")
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


REQUEST_KINDS = ("question", "price", "review_document", "approve", "meeting", "other")
REQUEST_STATUSES = ("open", "answered", "published", "resolved", "dismissed")


class PiStaffRequest(WorkspaceRow):
    """A request pi raises for the team (the request desk): a question it can't answer,
    a proposal to price or approve, a document to review, a meeting to arrange. The team
    answers with a note for pi; pi then replies to the customer itself, in their
    language. "Ask Owner" questions are the ``question`` kind."""

    __tablename__ = "pi_staff_requests"
    __table_args__ = workspace_args(
        "pi_staff_requests",
        scoped_fk("pi_staff_requests", "conversation_id", "pi_conversations"),
        CheckConstraint(_in("status", REQUEST_STATUSES), name="status"),
        CheckConstraint(_in("kind", REQUEST_KINDS), name="kind"),
        CheckConstraint(_in("priority", ("normal", "high")), name="priority"),
        Index("ix_pi_staff_requests_open", "tenant_id", "environment_id", "status"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    question: Mapped[str] = mapped_column(Text)
    context_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reply_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    knowledge_document_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="question", server_default="question")
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    lead_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    quote_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    file_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiKnowledgeDraft(WorkspaceRow):
    """ "Teach Pi": a proposed knowledge change awaiting review. Nothing becomes
    customer-visible knowledge until an authorized member publishes it."""

    __tablename__ = "pi_knowledge_drafts"
    __table_args__ = workspace_args(
        "pi_knowledge_drafts",
        CheckConstraint(_in("status", ("draft", "published", "discarded")), name="status"),
        CheckConstraint(
            _in("origin", ("owner_text", "owner_upload", "owner_audio", "ask_owner", "website")),
            name="origin",
        ),
    )
    origin: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    published_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    published_document_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    staff_request_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiBookableService(WorkspaceRow):
    """A bookable service with duration, buffers and working hours (native booking)."""

    __tablename__ = "pi_bookable_services"
    __table_args__ = workspace_args(
        "pi_bookable_services",
        CheckConstraint("duration_minutes BETWEEN 5 AND 720", name="duration"),
        CheckConstraint("buffer_minutes BETWEEN 0 AND 240", name="buffer"),
        CheckConstraint(_in("status", ("active", "archived")), name="status"),
    )
    name: Mapped[str] = mapped_column(String(160))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # {"mon": [["09:00","17:00"]], ...} in the business timezone.
    working_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    staff_user_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default="{}"
    )
    calendar_connection_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")


class PiBooking(WorkspaceRow):
    """A booking. The booking service serialises writes per service with a transaction
    advisory lock and re-checks overlap inside it, so concurrent requests for the same
    slot cannot both be confirmed; the idempotency key makes retries return one booking."""

    __tablename__ = "pi_bookings"
    __table_args__ = workspace_args(
        "pi_bookings",
        scoped_fk("pi_bookings", "service_id", "pi_bookable_services"),
        CheckConstraint(
            _in("status", ("pending", "confirmed", "cancelled", "completed", "no_show")),
            name="status",
        ),
        CheckConstraint("ends_at > starts_at", name="interval"),
        UniqueConstraint(
            "tenant_id", "environment_id", "idempotency_key", name="uq_pi_bookings_idempotency"
        ),
    )
    service_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    staff_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    external_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_sync: Mapped[str] = mapped_column(
        String(16), default="none", server_default="none"
    )  # none | pending | synced | failed | unknown
    created_by_label: Mapped[str] = mapped_column(String(80), default="", server_default="")


class PiTask(WorkspaceRow):
    """A bounded task/project brief linked to a customer or conversation."""

    __tablename__ = "pi_tasks"
    __table_args__ = workspace_args(
        "pi_tasks",
        CheckConstraint(
            _in("status", ("open", "in_progress", "blocked", "done", "cancelled")), name="status"
        ),
        CheckConstraint(_in("priority", ("low", "normal", "high", "urgent")), name="priority"),
        UniqueConstraint(
            "tenant_id", "environment_id", "idempotency_key", name="uq_pi_tasks_idempotency"
        ),
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assignee_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customer_visible_status: Mapped[str] = mapped_column(String(300), default="", server_default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PiTicket(WorkspaceRow):
    """Support ticket with priority and response-time tracking."""

    __tablename__ = "pi_tickets"
    __table_args__ = workspace_args(
        "pi_tickets",
        CheckConstraint(
            _in("status", ("open", "pending_customer", "resolved", "closed")), name="status"
        ),
        CheckConstraint(_in("priority", ("low", "normal", "high", "urgent")), name="priority"),
        UniqueConstraint(
            "tenant_id", "environment_id", "idempotency_key", name="uq_pi_tickets_idempotency"
        ),
    )
    subject: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    team: Mapped[str] = mapped_column(String(60), default="support", server_default="support")
    assignee_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    first_response_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PiConversationNote(WorkspaceRow):
    """Internal inbox note (never sent to the customer)."""

    __tablename__ = "pi_conversation_notes"
    __table_args__ = workspace_args(
        "pi_conversation_notes",
        scoped_fk("pi_conversation_notes", "conversation_id", "pi_conversations"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    author_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    author_label: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)


class PiSavedReply(WorkspaceRow):
    __tablename__ = "pi_saved_replies"
    __table_args__ = workspace_args(
        "pi_saved_replies",
        UniqueConstraint("tenant_id", "environment_id", "title", name="uq_pi_saved_replies_title"),
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)


class PiConversationTag(WorkspaceRow):
    __tablename__ = "pi_conversation_tags"
    __table_args__ = workspace_args(
        "pi_conversation_tags",
        scoped_fk("pi_conversation_tags", "conversation_id", "pi_conversations"),
        UniqueConstraint(
            "tenant_id", "environment_id", "conversation_id", "tag", name="uq_pi_conversation_tag"
        ),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    tag: Mapped[str] = mapped_column(String(40))


class PiCampaign(WorkspaceRow):
    """Template campaign to opted-in customers. Sends are individually rechecked."""

    __tablename__ = "pi_campaigns"
    __table_args__ = workspace_args(
        "pi_campaigns",
        CheckConstraint(
            _in("status", ("draft", "scheduled", "sending", "completed", "cancelled")),
            name="status",
        ),
    )
    name: Mapped[str] = mapped_column(String(120))
    template_name: Mapped[str] = mapped_column(String(512))
    template_language: Mapped[str] = mapped_column(String(16))
    audience_tag: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_recipients: Mapped[int] = mapped_column(Integer, default=500, server_default="500")
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Sending controls: at most ``daily_limit`` messages per local day, never during
    # quiet hours [quiet_start, quiet_end) in the business's time zone.
    daily_limit: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    quiet_start: Mapped[int] = mapped_column(Integer, default=21, server_default="21")
    quiet_end: Mapped[int] = mapped_column(Integer, default=9, server_default="9")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiCampaignRecipient(WorkspaceRow):
    """One customer in a campaign, snapshotted when sending starts. Each send is
    re-checked (consent, campaign still running, quiet hours) at delivery time."""

    __tablename__ = "pi_campaign_recipients"
    __table_args__ = workspace_args(
        "pi_campaign_recipients",
        scoped_fk("pi_campaign_recipients", "campaign_id", "pi_campaigns"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "campaign_id",
            "customer_id",
            name="uq_pi_campaign_recipient",
        ),
        CheckConstraint(
            _in("status", ("pending", "queued", "sent", "skipped", "failed")), name="status"
        ),
        Index("ix_pi_campaign_recipients_pending", "campaign_id", "status"),
    )
    campaign_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PiCustomerConsent(WorkspaceRow):
    """Marketing/reminder consent per customer, with source evidence."""

    __tablename__ = "pi_customer_consents"
    __table_args__ = workspace_args(
        "pi_customer_consents",
        UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "purpose", name="uq_pi_consent_purpose"
        ),
        CheckConstraint(_in("purpose", ("reminders", "marketing")), name="purpose"),
        CheckConstraint(_in("status", ("granted", "withdrawn")), name="status"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    purpose: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(300), default="", server_default="")
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiDigest(WorkspaceRow):
    """A weekly business summary (Monday to Sunday, business time zone), built from real
    counts and kept so owners can look back. One per business environment and week."""

    __tablename__ = "pi_digests"
    __table_args__ = workspace_args(
        "pi_digests",
        UniqueConstraint("tenant_id", "environment_id", "period_start", name="uq_pi_digest_week"),
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    delivery: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class PiPoolNumber(Record, Base):
    """A WhatsApp number in the platform's Kapso pool, offered to businesses and Owner OS
    workspaces. Kapso can't move a number between its customers, so pool numbers stay
    under one platform customer and the tenant mapping lives here (routing is by
    phone_number_id)."""

    __tablename__ = "pi_pool_numbers"
    __table_args__ = (
        CheckConstraint(
            _in("status", ("available", "reserved", "assigned", "retired")), name="status"
        ),
        Index("ix_pi_pool_numbers_status", "status"),
    )
    phone_number_id: Mapped[str] = mapped_column(String(32), unique=True)
    display_phone_number: Mapped[str] = mapped_column(String(32), default="", server_default="")
    business_account_id: Mapped[str] = mapped_column(String(32), default="", server_default="")
    kapso_customer_id: Mapped[str] = mapped_column(String(120), default="", server_default="")
    country: Mapped[str] = mapped_column(String(2), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="available", server_default="available")
    quality_rating: Mapped[str | None] = mapped_column(String(16), nullable=True)
    name_status: Mapped[str] = mapped_column(String(40), default="", server_default="")
    verified_name: Mapped[str] = mapped_column(String(120), default="", server_default="")
    is_coexistence: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    webhook_status: Mapped[str] = mapped_column(String(16), default="", server_default="")
    # Shown to businesses as-is (operator-entered); never computed or invented.
    price_label: Mapped[str] = mapped_column(String(80), default="", server_default="")
    notes: Mapped[str] = mapped_column(String(300), default="", server_default="")
    assigned_tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assigned_environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A business chose this number before it could connect (not yet approved or paid).
    # It connects automatically once allowed, or goes back to the pool after this time.
    held_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiPlatformState(Base):
    """Small platform-wide values that aren't configuration (e.g. the Kapso pool
    customer id created on first use)."""

    __tablename__ = "pi_platform_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


VERIFICATION_STATES = ("not_started", "submitted", "changes_requested", "approved", "rejected")


class PiBusinessVerification(TenantRow):
    """A business's review by the platform operator: its business details and the
    operator's decision. WhatsApp can connect only after approval."""

    __tablename__ = "pi_business_verifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_pi_business_verifications_tenant"),
        CheckConstraint(_in("status", VERIFICATION_STATES), name="status"),
        Index("ix_pi_business_verifications_status", "status", "submitted_at"),
    )
    status: Mapped[str] = mapped_column(
        String(20), default="not_started", server_default="not_started"
    )
    # legal_name, address, city, category, website, contact_phone, about
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Shown to the business (why changes are needed or why it was declined).
    decision_note: Mapped[str] = mapped_column(String(500), default="", server_default="")


class PiPlatformSetting(Base):
    """A platform setting the operator saved in the dashboard (overrides the server's
    .env value). Secrets are Fernet-encrypted and never returned, only a hint."""

    __tablename__ = "pi_platform_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    hint: Mapped[str] = mapped_column(String(16), default="", server_default="")
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
