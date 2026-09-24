from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.money import MONEY_SQL, QUANTITY_SQL, RATE_SQL

QUOTE_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "sent",
    "accepted",
    "rejected",
    "expired",
    "cancelled",
)


class Quote(WorkspaceRow):
    __tablename__ = "quotes"
    __table_args__ = workspace_args(
        "quotes",
        scoped_fk("quotes", "customer_id", "customers"),
        scoped_fk("quotes", "lead_id", "sales_leads"),
        UniqueConstraint("tenant_id", "environment_id", "number", name="uq_quotes_number"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in QUOTE_STATUSES) + ")", name="status"
        ),
        CheckConstraint("source IN ('manual', 'pi')", name="source"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name="amounts_nonnegative",
        ),
        Index("ix_quotes_scope_status", "tenant_id", "environment_id", "status", "created_at"),
        Index("ix_quotes_customer", "tenant_id", "environment_id", "customer_id"),
    )
    number: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    lead_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(RATE_SQL, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    valid_until: Mapped[date] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    approved_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class QuoteLine(WorkspaceRow):
    __tablename__ = "quote_lines"
    __table_args__ = workspace_args(
        "quote_lines",
        scoped_fk("quote_lines", "quote_id", "quotes"),
        scoped_fk("quote_lines", "variant_id", "catalog_variants"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND discount >= 0 AND line_total >= 0", name="amounts"),
        Index("ix_quote_lines_quote", "tenant_id", "environment_id", "quote_id", "position"),
    )
    quote_id: Mapped[UUID] = mapped_column(Uuid)
    variant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_SQL)
    unit_price: Mapped[Decimal] = mapped_column(MONEY_SQL)
    discount: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(MONEY_SQL)
