from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    code: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
        ),
    ]
    branch_id: UUID | None = None


class LocationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    code: str
    branch_id: UUID | None
    is_default: bool
    status: str


class StockAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant_id: UUID
    location_id: UUID | None = None
    quantity: int = Field(ge=-1_000_000, le=1_000_000)
    kind: Literal["receipt", "adjustment", "return"]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=240)]


class StockLevelView(BaseModel):
    variant_id: UUID
    product_id: UUID
    product_name: str
    variant_name: str
    sku: str
    location_id: UUID
    location_name: str
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int | None
    is_low: bool


class MovementView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    variant_id: UUID
    location_id: UUID
    quantity: int
    kind: str
    reason: str
    balance_after: int
    ref_type: str | None
    ref_id: UUID | None
    actor_label: str
    created_at: datetime


class Availability(BaseModel):
    variant_id: UUID
    on_hand: int
    reserved: int
    available: int
    tracked: bool
