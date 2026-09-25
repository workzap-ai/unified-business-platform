from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionInput(Input):
    phone_number_id: str = Field(pattern=r"^[0-9]{5,32}$")
    display_phone_number: str = Field(max_length=32)
    business_account_id: str = Field(default="", max_length=32)
    display_name: str = Field(default="", max_length=120)
    access_token: SecretStr | None = None


class StatusInput(Input):
    status: Literal["active", "disabled"]


class BodyInput(Input):
    body: str = Field(min_length=1, max_length=4000)


class HandoffInput(Input):
    reason: Literal[
        "customer_request",
        "low_confidence",
        "provider_failure",
        "policy",
        "tool_failure",
        "complaint",
        "sensitive",
        "manual",
    ] = "manual"
    summary: str = Field(default="", max_length=2000)


class HandoffAction(Input):
    action: Literal["assign", "start", "resolve", "close", "reopen"]
    assignee: UUID | None = None
    note: str = Field(default="", max_length=500)


class ConversationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    customer_name: str
    customer_phone: str | None
    status: str
    mode: str
    assigned_label: str | None = None
    last_message_at: datetime
    last_message_preview: str
    last_sender: str = "customer"
    unread_count: int
    language: str | None
    handoff_id: UUID | None = None
    handoff_status: str | None = None
    last_intent: str | None = None
    summary: str
    pending_confirmation: bool = False


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    direction: str
    sender_type: str
    message_type: str
    body: str
    media: dict[str, Any] | None
    status: str
    error_code: str | None
    agent_key: str | None
    sent_by_label: str | None
    created_at: datetime
    tool_events: list[dict[str, Any]] = Field(default_factory=list)
    confirmation: dict[str, Any] | None = None

    @field_validator("media", mode="before")
    @classmethod
    def public_media(cls, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict) or not value.get("mime_type"):
            return None
        return {
            key: value[key]
            for key in ("mime_type", "size", "duration_s", "transcript", "description")
            if key in value
        }


class HandoffView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    customer_id: UUID
    customer_name: str
    status: str
    reason: str
    priority: str
    summary: str
    assigned_label: str | None
    created_by_label: str
    created_at: datetime
    assigned_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str
