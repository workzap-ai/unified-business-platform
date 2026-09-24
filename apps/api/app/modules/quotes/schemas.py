from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.shared.money import Money

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


class QuoteLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: UUID | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )
    quantity: Quantity
    # Only for custom (non-catalog) service lines; catalog lines always use the catalog price.
    unit_price: Money | None = None
    discount: Money = Decimal("0")

    @model_validator(mode="after")
    def _custom_line(self) -> "QuoteLineInput":
        if self.variant_id is None and (self.unit_price is None or not self.description):
            raise ValueError("Custom lines need a description and a unit price")
        if self.variant_id is not None and self.unit_price is not None:
            raise ValueError("Catalog lines use the approved catalog price")
        return self


class QuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    lead_id: UUID | None = None
    valid_until: date | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=100)


class QuoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_until: date | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None
    lines: list[QuoteLineInput] | None = Field(default=None, min_length=1, max_length=100)


class QuoteLineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    variant_id: UUID | None
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    line_total: Decimal


class QuoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    customer_id: UUID
    lead_id: UUID | None
    status: str
    source: str
    currency: str
    subtotal: Decimal
    discount_total: Decimal
    tax_rate: Decimal
    tax_total: Decimal
    total: Decimal
    requires_approval: bool
    valid_until: date
    notes: str
    approved_at: datetime | None
    sent_at: datetime | None
    order_id: UUID | None
    created_at: datetime


class QuoteListItem(QuoteView):
    customer_name: str | None


class QuoteDetail(QuoteView):
    customer_name: str | None
    lines: list[QuoteLineView]
    next_actions: list[str]
