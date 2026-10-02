"""Platform subscription collection; never a client's customer-payment account."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record, TenantRow


class PiCollectionSettings(Record, Base):
    __tablename__ = "pi_collection_settings"
    key: Mapped[str] = mapped_column(String(20), unique=True, default="platform")
    # No API secrets are stored here. Bank details are provided by the platform owner.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class PiManualPayment(TenantRow):
    __tablename__ = "pi_manual_payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_key", name="uq_pi_manual_payment_request"),
        UniqueConstraint("reference_key", name="uq_pi_manual_payment_reference"),
        UniqueConstraint("receipt_number", name="uq_pi_manual_payment_receipt"),
        UniqueConstraint("link_token_hash", name="uq_pi_manual_payment_link_token"),
        CheckConstraint("amount > 0 AND currency = 'PKR'", name="amount_currency"),
        CheckConstraint("months IN (1, 3, 6, 12)", name="months"),
        CheckConstraint("method IN ('bank_transfer', 'cash')", name="method"),
        CheckConstraint(
            "status IN ('awaiting_payment', 'submitted', 'approved', "
            "'rejected', 'cancelled', 'refunded')",
            name="status",
        ),
    )
    request_key: Mapped[UUID] = mapped_column(Uuid)
    plan_key: Mapped[str] = mapped_column(ForeignKey("pi_plans.key", ondelete="RESTRICT"))
    plan_name: Mapped[str] = mapped_column(String(80))
    method: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment")
    months: Mapped[int] = mapped_column(default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="PKR")
    instructions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    payer_name: Mapped[str] = mapped_column(String(160), default="", server_default="")
    reference: Mapped[str] = mapped_column(String(120), default="", server_default="")
    reference_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    proof: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    proof_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    proof_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    review_note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    receipt_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("pi_platform_invoices.id", ondelete="RESTRICT")
    )
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    refund_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Public pay-by-link/QR access: only the digest is stored, same pattern as
    # auth_sessions.token_hash / password_reset_tokens.token_hash.
    link_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    link_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiCheckoutAttempt(TenantRow):
    __tablename__ = "pi_checkout_attempts"
    plan_key: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="creating")
    form: Mapped[dict[str, str]] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
