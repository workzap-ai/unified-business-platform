from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.money import MONEY_SQL, RATE_SQL

ORDER_STATUSES = ("draft", "confirmed", "processing", "shipped", "delivered", "cancelled")


class Order(WorkspaceRow):
    __tablename__ = "orders"
    __table_args__ = workspace_args(
        "orders",
        scoped_fk("orders", "customer_id", "customers"),
        scoped_fk("orders", "quote_id", "quotes"),
        UniqueConstraint("tenant_id", "environment_id", "number", name="uq_orders_number"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in ORDER_STATUSES) + ")", name="status"
        ),
        CheckConstraint("source IN ('manual', 'pi', 'quote')", name="source"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name="amounts_nonnegative",
        ),
        Index(
            "uq_orders_idempotency",
            "tenant_id",
            "environment_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_orders_quote",
            "tenant_id",
            "environment_id",
            "quote_id",
            unique=True,
            postgresql_where=text("quote_id IS NOT NULL AND status <> 'cancelled'"),
        ),
        Index("ix_orders_scope_status", "tenant_id", "environment_id", "status", "created_at"),
        Index("ix_orders_customer", "tenant_id", "environment_id", "customer_id", "created_at"),
    )
    number: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    quote_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(RATE_SQL, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_label: Mapped[str] = mapped_column(String(80))


class OrderLine(WorkspaceRow):
    __tablename__ = "order_lines"
    __table_args__ = workspace_args(
        "order_lines",
        scoped_fk("order_lines", "order_id", "orders"),
        scoped_fk("order_lines", "variant_id", "catalog_variants"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND discount >= 0 AND line_total >= 0", name="amounts"),
        Index("ix_order_lines_order", "tenant_id", "environment_id", "order_id", "position"),
        Index("ix_order_lines_variant", "tenant_id", "environment_id", "variant_id"),
    )
    order_id: Mapped[UUID] = mapped_column(Uuid)
    variant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(MONEY_SQL)
    discount: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(MONEY_SQL)
