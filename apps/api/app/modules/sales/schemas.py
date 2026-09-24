from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.shared.money import Currency, Money

Stage = Literal["new", "qualified", "proposal", "won", "lost"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class LeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    customer_id: UUID | None = None
    estimated_value: Money | None = None
    currency: Currency | None = None
    source: Literal["manual", "website", "referral"] = "manual"
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    customer_id: UUID | None = None
    estimated_value: Money | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None = None


class LeadStageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Stage


class LeadView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID | None
    title: str
    stage: str
    source: str
    estimated_value: Decimal | None
    currency: str
    requirements: dict[str, Any]
    missing_information: list[str]
    notes: str
    conversation_id: UUID | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadListItem(LeadView):
    customer_name: str | None
    next_stages: list[str] = Field(default_factory=list)


class PipelineStage(BaseModel):
    stage: str
    count: int
    value: Decimal
