"""Payments a business collects from its own WhatsApp customers.

Separate from the Pi subscription (``payment_models``/``billing``): these rows belong to
the business's environment, are paid into the business's own Stripe account, bank or
wallet, and settle the business's own invoices in the core billing module.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

METHODS = ("stripe", "bank_transfer", "mobile_wallet", "cash")
REQUEST_STATES = ("open", "awaiting_verification", "paid", "cancelled", "expired", "needs_review")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class PiCustomerPaymentSettings(WorkspaceRow):
    __tablename__ = "pi_customer_payment_settings"
    __table_args__ = workspace_args(
        "pi_customer_payment_settings",
        UniqueConstraint("tenant_id", "environment_id", name="uq_pi_customer_payment_settings"),
    )
    stripe_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    bank_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # [{"bank": "Meezan Bank", "account_title": "...", "account_number": "...",
    #   "iban": "PK..", "branch": "..."}]
    bank_accounts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    wallet_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # [{"provider": "jazzcash", "account_title": "...", "number": "03xxxxxxxxx"}]
    wallets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    cash_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cash_instructions: Mapped[str] = mapped_column(Text, default="", server_default="")
    payment_note: Mapped[str] = mapped_column(Text, default="", server_default="")


class PiPaymentRequest(WorkspaceRow):
    """One request to pay (part of) an issued invoice through one method."""

    __tablename__ = "pi_payment_requests"
    __table_args__ = workspace_args(
        "pi_payment_requests",
        scoped_fk("pi_payment_requests", "invoice_id", "invoices"),
        UniqueConstraint("reference", name="uq_pi_payment_requests_reference"),
        UniqueConstraint(
            "tenant_id", "environment_id", "idempotency_key", name="uq_pi_payment_requests_key"
        ),
        UniqueConstraint("link_token_hash", name="uq_pi_payment_requests_link_token"),
        CheckConstraint(_in("method", METHODS), name="method"),
        CheckConstraint(_in("status", REQUEST_STATES), name="status"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )
    invoice_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="open", server_default="open")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reference: Mapped[str] = mapped_column(String(24))
    # Instructions exactly as shown to the customer (bank details can change later).
    instructions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    checkout_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    integration_operation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    proof_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    proof_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80), default="", server_default="")
    # Public pay-by-link/QR access: only the digest is stored, same pattern as
    # auth_sessions.token_hash / password_reset_tokens.token_hash.
    link_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    link_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
