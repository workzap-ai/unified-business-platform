"""The deal flow's own records: customer-facing proposal and invoice documents, and the
business's automation switches.

A document is one link a customer opens (in the pi app, at /d/{token}) to read a
proposal or an invoice, accept the proposal, ask for changes, or pay. Only a hash of
the token is stored. ``delivery`` says how it reached the customer:

- ``sent``: posted in their WhatsApp chat (inside the 24-hour window);
- ``waiting``: a template asked them to reply; the link goes out the moment they do;
- ``manual``: no way to message them first; the team shares the link themselves.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args

DOCUMENT_KINDS = ("proposal", "invoice")
DELIVERIES = ("pending", "sent", "waiting", "manual", "failed")
RESPONSES = ("accepted", "changes", "rejected")
PAYMENT_DEFAULTS = ("auto", "stripe", "bank_transfer", "mobile_wallet", "cash")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiDocument(WorkspaceRow):
    __tablename__ = "pi_documents"
    __table_args__ = workspace_args(
        "pi_documents",
        UniqueConstraint("token_hash", name="uq_pi_documents_token_hash"),
        Index("ix_pi_documents_quote", "tenant_id", "environment_id", "quote_id"),
        Index("ix_pi_documents_waiting", "tenant_id", "customer_id", "delivery"),
        CheckConstraint(_in("kind", DOCUMENT_KINDS), name="kind"),
        CheckConstraint(_in("delivery", DELIVERIES), name="delivery"),
        CheckConstraint(f"response IS NULL OR {_in('response', RESPONSES)}", name="response"),
    )
    kind: Mapped[str] = mapped_column(String(16))
    quote_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    invoice_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    lead_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    message_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response: Mapped[str | None] = mapped_column(String(16), nullable=True)
    response_note: Mapped[str] = mapped_column(Text, default="", server_default="")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiDealSettings(WorkspaceRow):
    """One row per business: which steps after "accepted" run on their own."""

    __tablename__ = "pi_deal_settings"
    __table_args__ = workspace_args(
        "pi_deal_settings",
        UniqueConstraint("tenant_id", "environment_id", name="uq_pi_deal_settings_scope"),
        CheckConstraint(_in("payment_method", PAYMENT_DEFAULTS), name="payment_method"),
    )
    # Brief confirmed in the chat → proposal made (catalog prices) → sent when fully priced.
    auto_proposal: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Proposal accepted → order confirmed → invoice issued → payment link sent.
    auto_order: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_invoice: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    auto_payment_request: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    thank_you_on_paid: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    payment_method: Mapped[str] = mapped_column(String(16), default="auto", server_default="auto")
    # An approved WhatsApp template with no variables ("Your document is ready, reply to
    # see it") for customers outside the 24-hour window. Empty = share the link manually.
    template_name: Mapped[str] = mapped_column(String(512), default="", server_default="")
    template_language: Mapped[str] = mapped_column(String(16), default="", server_default="")
