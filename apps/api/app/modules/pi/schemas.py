from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


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


VISUALS = frozenset({"map", "map_text", "board", "progress"})


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
    # A picture pi sent (pi Customer's problem map or journey card): the team sees the
    # same image the customer got, not only its caption.
    card: dict[str, str] | None = None

    @model_validator(mode="before")
    @classmethod
    def sent_card(cls, data: Any) -> Any:
        media = data.get("media") if isinstance(data, dict) else getattr(data, "media", None)
        if not isinstance(media, dict) or not media.get("image"):
            return data
        # pi Customer's map or journey card ("card"), or a picture of the brain (the problem map,
        # the board, a progress card: "visual"): the team sees what the customer got.
        kind = media.get("card") or (media.get("visual") if media.get("visual") in VISUALS else "")
        image = str(media["image"])
        if not kind or not image.startswith("http"):
            return data
        card = {"kind": str(kind), "image": image}
        if isinstance(data, dict):
            return {**data, "card": card}
        fields = {name: getattr(data, name) for name in cls.model_fields if hasattr(data, name)}
        return {**fields, "card": card}

    @field_validator("media", mode="before")
    @classmethod
    def public_media(cls, value: Any) -> dict[str, Any] | None:
        """What the team's thread may show of a message's media. Inbound media pi processed (it
        then knows the size; a provider's file type alone, stored on arrival, is not shown) with
        its reading and its saved file; and what pi SENT: the picture of a map, a board or a
        progress card, a document link, and the buttons. Nothing else leaves the server."""
        if not isinstance(value, dict):
            return None
        out: dict[str, Any] = {}
        if value.get("mime_type") and "size" in value:
            for key in (
                "mime_type",
                "size",
                "duration_s",
                "transcript",
                "description",
                "file_id",
                "filename",
                "file_kind",
                "doc_kind",
            ):
                if key in value:
                    out[key] = value[key]
        image = value.get("image")
        if isinstance(image, str) and image.startswith("http") and value.get("visual") in VISUALS:
            out["image"] = image
            out["visual"] = value["visual"]
            if isinstance(value.get("alt"), str):
                out["alt"] = value["alt"][:300]
            if "map_version" in value:
                out["map_version"] = value["map_version"]
        document = value.get("document")
        if isinstance(document, dict) and str(document.get("link") or "").startswith("http"):
            out["document"] = {
                "link": str(document["link"]),
                "filename": str(document.get("filename") or "")[:120],
            }
        buttons = value.get("buttons")
        if isinstance(buttons, list):
            titles = [
                str(b.get("title") or b.get("text") or "")[:40]
                if isinstance(b, dict)
                else str(b)[:40]
                for b in buttons[:10]
            ]
            if any(titles):
                out["buttons"] = [t for t in titles if t]
        return out or None


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


class MessageHistory(BaseModel):
    items: list[MessageView]
    has_more: bool
    before: datetime | None = None
    before_id: UUID | None = None
