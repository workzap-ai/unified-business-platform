from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args
from app.shared.money import MONEY_SQL

EXPENSE_CATEGORIES = (
    "rent",
    "payroll",
    "utilities",
    "inventory",
    "marketing",
    "software",
    "travel",
    "taxes",
    "professional_services",
    "other",
)


class Expense(WorkspaceRow):
    __tablename__ = "expenses"
    __table_args__ = workspace_args(
        "expenses",
        UniqueConstraint("tenant_id", "environment_id", "number", name="uq_expenses_number"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("status IN ('recorded', 'void')", name="status"),
        CheckConstraint(
            "category IN (" + ", ".join(f"'{c}'" for c in EXPENSE_CATEGORIES) + ")",
            name="category",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        Index("ix_expenses_scope_incurred", "tenant_id", "environment_id", "incurred_on"),
    )
    number: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(300))
    vendor: Mapped[str] = mapped_column(String(160), default="", server_default="")
    amount: Mapped[Decimal] = mapped_column(MONEY_SQL)
    currency: Mapped[str] = mapped_column(String(3))
    incurred_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="recorded", server_default="recorded")
    recorded_by_label: Mapped[str] = mapped_column(String(80))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
