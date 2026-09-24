from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
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
from app.shared.money import MONEY_SQL, QUANTITY_SQL

INVOICE_STATUSES = ("draft", "issued", "partially_paid", "paid", "void")
PAYMENT_METHODS = ("cash", "bank_transfer", "card", "mobile_wallet", "other")


class Invoice(WorkspaceRow):
    __tablename__ = "invoices"
    __table_args__ = workspace_args(
        "invoices",
        scoped_fk("invoices", "customer_id", "customers"),
        scoped_fk("invoices", "order_id", "orders"),
        UniqueConstraint("tenant_id", "environment_id", "number", name="uq_invoices_number"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in INVOICE_STATUSES) + ")", name="status"
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint(
            "subtotal >= 0 AND discount_total >= 0 AND tax_total >= 0 AND total >= 0",
            name="amounts_nonnegative",
        ),
        CheckConstraint("amount_paid >= 0 AND amount_paid <= total", name="paid_range"),
        Index(
            "uq_invoices_order",
            "tenant_id",
            "environment_id",
            "order_id",
            unique=True,
            postgresql_where=text("order_id IS NOT NULL AND status <> 'void'"),
        ),
        Index("ix_invoices_scope_status", "tenant_id", "environment_id", "status", "due_date"),
        Index("ix_invoices_customer", "tenant_id", "environment_id", "customer_id"),
    )
    number: Mapped[str] = mapped_column(String(20))
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    order_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    amount_paid: Mapped[Decimal] = mapped_column(
        MONEY_SQL, default=Decimal("0"), server_default="0"
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InvoiceLine(WorkspaceRow):
    __tablename__ = "invoice_lines"
    __table_args__ = workspace_args(
        "invoice_lines",
        scoped_fk("invoice_lines", "invoice_id", "invoices"),
        scoped_fk("invoice_lines", "variant_id", "catalog_variants"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND discount >= 0 AND line_total >= 0", name="amounts"),
        Index("ix_invoice_lines_invoice", "tenant_id", "environment_id", "invoice_id", "position"),
    )
    invoice_id: Mapped[UUID] = mapped_column(Uuid)
    variant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(QUANTITY_SQL)
    unit_price: Mapped[Decimal] = mapped_column(MONEY_SQL)
    discount: Mapped[Decimal] = mapped_column(MONEY_SQL, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(MONEY_SQL)


class Payment(WorkspaceRow):
    __tablename__ = "payments"
    __table_args__ = workspace_args(
        "payments",
        scoped_fk("payments", "invoice_id", "invoices"),
        UniqueConstraint("tenant_id", "environment_id", "number", name="uq_payments_number"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "method IN (" + ", ".join(f"'{m}'" for m in PAYMENT_METHODS) + ")", name="method"
        ),
        Index("ix_payments_invoice", "tenant_id", "environment_id", "invoice_id"),
        Index("ix_payments_scope_received", "tenant_id", "environment_id", "received_on"),
    )
    invoice_id: Mapped[UUID] = mapped_column(Uuid)
    number: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(MONEY_SQL)
    currency: Mapped[str] = mapped_column(String(3))
    method: Mapped[str] = mapped_column(String(20))
    received_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(120), default="", server_default="")
    recorded_by_label: Mapped[str] = mapped_column(String(80))
