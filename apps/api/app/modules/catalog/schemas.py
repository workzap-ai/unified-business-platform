from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.shared.money import Currency, Money

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"
    ),
]
Sku = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"),
]
Status = Literal["active", "inactive"]
OfferingType = Literal["service", "product", "hybrid", "package"]


def _attributes(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > 30:
        raise ValueError("Too many attributes")
    for k, v in value.items():
        if len(str(k)) > 60 or not isinstance(v, str | int | bool) or len(str(v)) > 200:
            raise ValueError("Attributes must be short text, number or boolean values")
    return value


Attributes = Annotated[dict[str, Any], AfterValidator(_attributes)]


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    slug: Slug
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class CategoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    description: str


class VariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Sku
    name: Name
    price: Money
    currency: Currency
    track_inventory: bool = False
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    attributes: Attributes = Field(default_factory=dict)


class VariantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    price: Money | None = None
    status: Status | None = None
    track_inventory: bool | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0, le=1_000_000)
    attributes: Attributes | None = None


class VariantView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    sku: str
    name: str
    price: Money
    currency: str
    status: str
    track_inventory: bool
    low_stock_threshold: int | None
    attributes: dict[str, Any]


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offering_type: OfferingType = "service"
    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""
    category_id: UUID | None = None
    pi_visible: bool = True
    attributes: Attributes = Field(default_factory=dict)
    variants: list[VariantCreate] = Field(min_length=1, max_length=50)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None
    ) = None
    category_id: UUID | None = None
    status: Status | None = None
    pi_visible: bool | None = None
    attributes: Attributes | None = None


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    offering_type: OfferingType
    id: UUID
    name: str
    description: str
    category_id: UUID | None
    status: str
    pi_visible: bool
    attributes: dict[str, Any]
    created_at: datetime


class ProductListItem(ProductView):
    category_name: str | None
    variant_count: int
    min_price: Money | None
    max_price: Money | None
    currency: str | None


class ProductDetail(ProductView):
    category_name: str | None
    variants: list[VariantView]
