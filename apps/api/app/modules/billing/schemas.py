from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.shared.money import Money

Method = Literal["cash", "bank_transfer", "card", "mobile_wallet", "other"]


class InvoiceLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    unit_price: Money
    discount: Money = Decimal("0")


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: UUID
    due_date: date | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    lines: list[InvoiceLineInput] = Field(min_length=1, max_length=100)


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    method: Method
    received_on: date | None = None
    reference: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""


class InvoiceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["issue", "void"]


class InvoiceLineView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    variant_id: UUID | None
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    line_total: Decimal


class PaymentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    invoice_id: UUID
    number: str
    amount: Decimal
    currency: str
    method: str
    received_on: date
    reference: str
    recorded_by_label: str
    created_at: datetime


class InvoiceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    customer_id: UUID
    order_id: UUID | None
    status: str
    issue_date: date | None
    due_date: date | None
    currency: str
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    total: Decimal
    amount_paid: Decimal
    notes: str
    created_at: datetime


class InvoiceListItem(InvoiceView):
    customer_name: str | None
    balance_due: Decimal
    is_overdue: bool


class InvoiceDetail(InvoiceListItem):
    lines: list[InvoiceLineView]
    payments: list[PaymentView]
    next_actions: list[str]


class BillingSummary(BaseModel):
    currency: str
    outstanding: Decimal
    overdue: Decimal
    overdue_count: int
    collected_this_month: Decimal
    draft_count: int
