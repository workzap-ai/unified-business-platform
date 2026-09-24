from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.money import MONEY_SQL


class SalesLead(WorkspaceRow):
    """Lead/opportunity. PI stores structured service requirements here for human follow-up."""

    __tablename__ = "sales_leads"
    __table_args__ = workspace_args(
        "sales_leads",
        scoped_fk("sales_leads", "customer_id", "customers"),
        CheckConstraint("stage IN ('new', 'qualified', 'proposal', 'won', 'lost')", name="stage"),
        CheckConstraint("source IN ('manual', 'pi', 'website', 'referral')", name="source"),
        CheckConstraint(
            "estimated_value IS NULL OR estimated_value >= 0", name="value_nonnegative"
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        Index("ix_sales_leads_scope_stage", "tenant_id", "environment_id", "stage", "created_at"),
        Index("ix_sales_leads_conversation", "tenant_id", "environment_id", "conversation_id"),
    )
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    stage: Mapped[str] = mapped_column(String(16), default="new", server_default="new")
    source: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    estimated_value: Mapped[Decimal | None] = mapped_column(MONEY_SQL, nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    missing_information: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, server_default="{}"
    )
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
