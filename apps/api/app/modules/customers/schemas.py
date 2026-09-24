import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Tag = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=40)
]
_PHONE_CHARS = re.compile(r"[\s\-().]")


def normalize_phone(value: str | None) -> str | None:
    """Normalize to E.164 (+ and 7–15 digits). Raises ValueError when not plausible."""
    if value is None:
        return None
    raw = _PHONE_CHARS.sub("", value.strip())
    if not raw:
        return None
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if not raw.startswith("+"):
        raw = "+" + raw
    if not re.fullmatch(r"\+[0-9]{7,15}", raw):
        raise ValueError("Enter a phone number in international format")
    return raw


class CustomerFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    company: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=20)

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return normalize_phone(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None


class CustomerCreate(CustomerFields):
    name: Name


class CustomerUpdate(CustomerFields):
    name: Name | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)  # type: ignore[assignment]


class CustomerStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "archived"]


class CustomerView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: str | None
    phone: str | None
    company: str | None
    status: str
    source: str
    tags: list[str]
    last_contacted_at: datetime | None
    created_at: datetime


class CustomerSummary(BaseModel):
    order_count: int
    open_quote_count: int
    outstanding_balance: Decimal | None  # None when the viewer lacks billing.read
    currency: str | None
    open_conversations: int


class CustomerDetail(CustomerView):
    summary: CustomerSummary


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class NoteView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    author_label: str
    body: str
    created_at: datetime


class ActivityView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    kind: str
    summary: str
    ref_type: str | None
    ref_id: UUID | None
    actor_label: str
    created_at: datetime
