from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.business_settings.models import BusinessSettings
from app.shared.money import Currency, Money, Rate
from app.shared.scope import WorkspaceScope


class BusinessSettingsView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    business_type: Literal["service_business", "product_business", "hybrid_business"]
    default_currency: str
    tax_rate: Decimal
    auto_invoice_on_order_confirm: bool
    low_stock_threshold: int
    invoice_due_days: int
    quote_validity_days: int
    quote_approval_threshold: Decimal | None
    max_discount_rate: Decimal


class BusinessSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_type: Literal["service_business", "product_business", "hybrid_business"] | None = None
    default_currency: Currency | None = None
    tax_rate: Rate | None = None
    auto_invoice_on_order_confirm: bool | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    invoice_due_days: int | None = Field(default=None, ge=0, le=365)
    quote_validity_days: int | None = Field(default=None, ge=1, le=365)
    quote_approval_threshold: Money | None = None
    max_discount_rate: Rate | None = None


async def get_settings_row(session: AsyncSession, scope: WorkspaceScope) -> BusinessSettings:
    """Created with defaults on first use; the unique constraint prevents duplicates."""
    await session.execute(
        insert(BusinessSettings)
        .values(tenant_id=scope.tenant_id, environment_id=scope.environment_id)
        .on_conflict_do_nothing(constraint="uq_business_settings_scope")
    )
    row = await session.scalar(
        select(BusinessSettings).where(
            BusinessSettings.tenant_id == scope.tenant_id,
            BusinessSettings.environment_id == scope.environment_id,
        )
    )
    assert row is not None
    return row


async def update_settings(
    session: AsyncSession, scope: WorkspaceScope, data: BusinessSettingsUpdate
) -> BusinessSettings:
    scope.require("settings.manage")
    row = await get_settings_row(session, scope)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None or field == "quote_approval_threshold":
            setattr(row, field, value)
    await session.flush()
    await record(
        session,
        "settings.business_updated",
        scope=scope,
        entity_type="business_settings",
        entity_id=row.id,
        details={"fields": sorted(changes)},
    )
    return row
