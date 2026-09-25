from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args
from app.shared.money import MONEY_SQL, RATE_SQL


class BusinessSettings(WorkspaceRow):
    __tablename__ = "business_settings"
    __table_args__ = workspace_args(
        "business_settings",
        CheckConstraint(
            "business_type IN ('service_business', 'product_business', 'hybrid_business')",
            name="business_type",
        ),
        UniqueConstraint("tenant_id", "environment_id", name="uq_business_settings_scope"),
        CheckConstraint("default_currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 1", name="tax_rate_range"),
        CheckConstraint("low_stock_threshold >= 0", name="threshold_nonnegative"),
        CheckConstraint("invoice_due_days BETWEEN 0 AND 365", name="due_days_range"),
        CheckConstraint("quote_validity_days BETWEEN 1 AND 365", name="validity_range"),
        CheckConstraint("max_discount_rate >= 0 AND max_discount_rate <= 1", name="discount_range"),
    )
    business_type: Mapped[str] = mapped_column(
        String(24), default="service_business", server_default="service_business"
    )
    default_currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    tax_rate: Mapped[Decimal] = mapped_column(RATE_SQL, default=Decimal("0"), server_default="0")
    auto_invoice_on_order_confirm: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    invoice_due_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    quote_validity_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    # Quotes above this total, or with discounts above max_discount_rate, need approval.
    quote_approval_threshold: Mapped[Decimal | None] = mapped_column(MONEY_SQL, nullable=True)
    max_discount_rate: Mapped[Decimal] = mapped_column(
        RATE_SQL, default=Decimal("0.1"), server_default="0.1"
    )
