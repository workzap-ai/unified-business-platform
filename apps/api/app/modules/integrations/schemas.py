"""Request/response schemas for docs/contracts/integrations-api.md.

No response schema has a field that can carry a credential value; credentials appear
only as {key, set, hint}. The one-time secrets (webhook signing secret, API key secret)
exist only on the *Created responses.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
FieldKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,59}$")]
ConfigValue = str | int | float | bool | None
Mode = Literal["sandbox", "production"]
EventStatus = Literal[
    "received", "queued", "processing", "processed", "ignored", "failed", "dead_letter"
]
JobStatus = Literal[
    "pending", "running", "succeeded", "failed", "dead_letter", "cancelled", "paused"
]
ConnectionStatus = Literal[
    "draft", "connecting", "connected", "degraded", "expired", "revoked", "disabled", "error"
]


def _bounded_config(value: dict[str, Any]) -> dict[str, Any]:
    if len(value) > 40:
        raise ValueError("Too many fields")
    for item in value.values():
        if isinstance(item, str) and len(item) > 2048:
            raise ValueError("Value too long")
    return value


def _bounded_credentials(value: dict[str, str]) -> dict[str, str]:
    if len(value) > 20:
        raise ValueError("Too many fields")
    if any(len(v) > 8192 for v in value.values()):
        raise ValueError("Value too long")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- directory --------------------------------------------------------------------------


class OptionView(BaseModel):
    value: str
    label: str


class ConfigFieldView(BaseModel):
    key: str
    label: str
    type: str
    required: bool
    secret: bool
    help: str | None
    options: list[OptionView] | None = None


class DefinitionView(BaseModel):
    key: str
    name: str
    description: str
    category: str
    provider: str
    availability: str
    auth_type: str
    capabilities: list[str]
    supported_scopes: list[str]
    required_scopes: list[str]
    webhook_support: bool
    sync_support: list[str]
    supports_sandbox: bool
    documentation_url: str | None
    version: str
    config_schema: list[ConfigFieldView]
    connection_count: int


# --- connections ------------------------------------------------------------------------


class ConnectionCreate(Strict):
    integration_key: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{2,60}$")]
    display_name: Name
    mode: Mode = "production"
    config: dict[FieldKey, ConfigValue] = Field(default_factory=dict)
    credentials: dict[FieldKey, Annotated[str, StringConstraints(max_length=8192)]] = Field(
        default_factory=dict
    )

    check_config = field_validator("config")(_bounded_config)
    check_credentials = field_validator("credentials")(_bounded_credentials)


class ConnectionUpdate(Strict):
    display_name: Name | None = None
    config: dict[FieldKey, ConfigValue] | None = None

    @field_validator("config")
    @classmethod
    def _config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _bounded_config(value) if value is not None else None


class CredentialsUpdate(Strict):
    credentials: dict[FieldKey, Annotated[str, StringConstraints(min_length=1, max_length=8192)]]

    check_credentials = field_validator("credentials")(_bounded_credentials)


class ConnectionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    integration_key: str
    display_name: str
    status: str
    mode: str
    environment_id: UUID
    health: str
    circuit_state: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None
    last_health_check_at: datetime | None
    connected_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CredentialView(BaseModel):
    key: str
    set: bool
    hint: str | None


class HealthDetail(BaseModel):
    latency_ms: int | None
    consecutive_failures: int
    rate_limited_until: datetime | None


class ActivityView(BaseModel):
    at: datetime
    kind: str
    outcome: str
    message: str


class ConnectionDetail(ConnectionView):
    config: dict[str, Any]
    credentials: list[CredentialView]
    scopes: list[str]
    sync_direction: str
    health_detail: HealthDetail
    recent_activity: list[ActivityView]
    # Additive to the v1 contract: where to point the provider's webhook (null if n/a).
    webhook_url: str | None = None


class TestResult(BaseModel):
    ok: bool
    status: str
    latency_ms: int | None
    message: str
    checked_at: datetime


class OAuthStart(BaseModel):
    authorization_url: str


# --- outbound webhooks --------------------------------------------------------------------


class EventTypeView(BaseModel):
    key: str
    description: str


EventTypes = Annotated[
    list[Annotated[str, StringConstraints(pattern=r"^[a-z]+(\.[a-z_]+){1,3}$")]],
    Field(min_length=1, max_length=50),
]


class WebhookCreate(Strict):
    name: Name
    url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2048)]
    event_types: EventTypes
    enabled: bool = True


class WebhookUpdate(Strict):
    name: Name | None = None
    url: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=2048)]
        | None
    ) = None
    event_types: EventTypes | None = None
    enabled: bool | None = None


class WebhookView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    url: str
    event_types: list[str]
    enabled: bool
    secret_hint: str
    last_delivery_at: datetime | None
    last_delivery_status: str | None
    failure_count: int
    created_at: datetime
    updated_at: datetime


class WebhookCreated(WebhookView):
    signing_secret: str


class DeliveryView(BaseModel):
    id: UUID
    subscription_id: UUID
    event_type: str
    event_id: UUID
    status: str
    attempt_count: int
    response_status: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    created_at: datetime
    delivered_at: datetime | None


# --- inbound events / jobs / failures / health -------------------------------------------


class InboundEventView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connection_id: UUID
    integration_key: str
    provider_event_id: str
    event_type: str
    status: str
    signature_verified: bool
    attempt_count: int
    received_at: datetime
    processed_at: datetime | None
    error_code: str | None
    correlation_id: str | None


class SyncRequest(Strict):
    entity: Annotated[str, StringConstraints(pattern=r"^[a-z_]{2,40}$")]
    mode: Literal["incremental", "full"] = "incremental"


class SyncStats(BaseModel):
    discovered: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    conflicts: int = 0


class SyncJobView(BaseModel):
    id: UUID
    connection_id: UUID
    integration_key: str
    entity: str
    direction: str
    mode: str
    status: str
    cursor: str | None
    stats: SyncStats
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    created_at: datetime


class FailureView(BaseModel):
    id: UUID
    kind: Literal["delivery", "event", "job"]
    connection_id: UUID | None
    integration_key: str
    summary: str
    error_code: str | None
    attempt_count: int
    status: str
    occurred_at: datetime
    can_retry: bool


class HealthSummary(BaseModel):
    connected: int
    degraded: int
    failing: int
    disabled: int


class ConnectionHealth(BaseModel):
    id: UUID
    display_name: str
    integration_key: str
    status: str
    health: str
    circuit_state: str
    latency_ms: int | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    rate_limited_until: datetime | None
    webhook_state: Literal["healthy", "failing", "not_applicable"]
    sync_state: Literal["idle", "running", "failing", "not_applicable"]


class HealthView(BaseModel):
    summary: HealthSummary
    connections: list[ConnectionHealth]


# --- API keys --------------------------------------------------------------------------------


class ApiKeyCreate(Strict):
    name: Name
    scopes: list[Annotated[str, StringConstraints(max_length=60)]] = Field(max_length=100)
    expires_in_days: Annotated[int, Field(ge=1, le=3650)] | None = None


class ApiKeyView(BaseModel):
    id: UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_by_name: str


class ApiKeyCreated(ApiKeyView):
    secret: str
