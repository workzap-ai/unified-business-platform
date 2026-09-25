from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.shared.money import Money


class OrderLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: UUID
    quantity: int = Field(ge=1, le=100_000)
    discount: Money = Decimal("0")


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    lines: list[OrderLineInput] = Field(min_length=1, max_length=100)


class OrderLinesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[OrderLineInput] = Field(min_length=1, max_length=100)


class OrderTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "start_processing", "ship", "deliver", "complete", "cancel"]


class OrderLineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    variant_id: UUID | None
    position: int
    sku: str | None
    description: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    line_total: Decimal


class OrderView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    fulfillment_type: Literal["service", "product", "hybrid"]
    id: UUID
    number: str
    customer_id: UUID
    quote_id: UUID | None
    status: str
    source: str
    currency: str
    subtotal: Decimal
    discount_total: Decimal
    tax_rate: Decimal
    tax_total: Decimal
    total: Decimal
    notes: str
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    created_by_label: str
    created_at: datetime


class OrderListItem(OrderView):
    customer_name: str | None


class OrderDetail(OrderView):
    customer_name: str | None
    lines: list[OrderLineView]
    next_actions: list[str]
    invoice_id: UUID | None
    invoice_number: str | None
