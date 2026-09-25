"""Integration definitions, the provider adapter contract and normalized DTOs.

A definition describes what the UI can show and what a connection needs. An adapter
(`IntegrationProvider` subclass) implements it. Definitions without an adapter are
registered as `planned`: listed honestly but not connectable.

Adapters are stateless: every call receives a `ProviderContext` holding decrypted
credentials, plain configuration, the policy-enforcing outbound client and the call
context. Adapters never log or return credential values.
"""

import abc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.core.config import Settings
from app.integrations.http import CallContext, OutboundClient
from app.shared.errors import BusinessRuleViolation

Category = Literal[
    "messaging",
    "ai",
    "email",
    "storage",
    "payments",
    "calendar",
    "accounting",
    "commerce",
    "collaboration",
    "automation",
    "identity",
]
AuthType = Literal[
    "api_key",
    "bearer_token",
    "basic_auth",
    "oauth2",
    "oauth2_pkce",
    "webhook_secret",
    "signature_secret",
    "service_account",
    "none",
]
Availability = Literal["available", "beta", "planned"]
FieldType = Literal["text", "url", "email", "password", "number", "select", "boolean"]
SyncDirection = Literal["none", "pull", "push", "bidirectional"]
Mode = Literal["sandbox", "production"]


@dataclass(frozen=True, slots=True)
class ConfigField:
    key: str
    label: str
    type: FieldType = "text"
    required: bool = True
    secret: bool = False
    help: str | None = None
    options: tuple[tuple[str, str], ...] = ()
    max_length: int = 2000


@dataclass(frozen=True, slots=True)
class SyncEntityPolicy:
    """Declared per entity: which system wins on conflict and which way data flows."""

    entity: str
    direction: SyncDirection
    source_of_truth: Literal["platform", "provider"]
    description: str = ""


@dataclass(frozen=True, slots=True)
class OAuthSpec:
    authorize_url: str
    token_url: str
    revoke_url: str | None = None
    pkce: bool = True
    client_id_setting: str | None = None  # Settings attribute holding the client id
    client_secret_setting: str | None = None
    extra_authorize_params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class IntegrationDefinition:
    key: str
    name: str
    description: str
    category: Category
    provider: str
    auth_type: AuthType
    availability: Availability = "available"
    capabilities: tuple[str, ...] = ()
    supported_scopes: tuple[str, ...] = ()
    required_scopes: tuple[str, ...] = ()
    webhook_support: bool = False
    sync_support: tuple[SyncDirection, ...] = ("none",)
    sync_entities: tuple[SyncEntityPolicy, ...] = ()
    supports_sandbox: bool = False
    documentation_url: str | None = None
    version: str = "1"
    config_schema: tuple[ConfigField, ...] = ()
    oauth: OAuthSpec | None = None

    @property
    def secret_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.config_schema if f.secret)

    @property
    def config_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.config_schema if not f.secret)

    @property
    def connectable(self) -> bool:
        return self.availability != "planned"

    @property
    def syncs(self) -> bool:
        return any(d != "none" for d in self.sync_support) and bool(self.sync_entities)

    def sync_policy(self, entity: str) -> SyncEntityPolicy | None:
        return next((p for p in self.sync_entities if p.entity == entity), None)


class ConfigurationInvalid(BusinessRuleViolation):
    def __init__(self, message: str, field_key: str | None = None) -> None:
        super().__init__("INVALID_CONFIGURATION", message, 422)
        self.field_key = field_key


# --- normalized DTOs ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthResult:
    ok: bool
    message: str
    latency_ms: int | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    provider_event_id: str
    event_type: str
    data: Mapping[str, Any]
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: Sequence[str]
    subject: str
    text: str
    html: str | None = None
    from_address: str | None = None
    reply_to: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    provider_message_id: str | None
    accepted: bool = True


@dataclass(frozen=True, slots=True)
class MediaItem:
    content: bytes
    mime_type: str


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    size: int
    content_type: str | None
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True, slots=True)
class ExternalCustomer:
    """A provider customer normalized for matching; never written to CRM directly."""

    external_id: str
    email: str | None
    name: str | None
    phone: str | None
    updated_at: datetime | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PlatformCustomerReference:
    customer_id: str | None
    match: Literal["email", "none", "ambiguous"]


@dataclass(frozen=True, slots=True)
class SyncPage[T]:
    items: Sequence[T]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    id: str
    status: str
    amount_minor: int
    currency: str
    client_secret_available: bool


@dataclass(frozen=True, slots=True)
class ProviderContext:
    settings: Settings
    http: OutboundClient
    config: Mapping[str, Any]
    credentials: Mapping[str, str]
    mode: Mode = "production"
    call: CallContext = field(default_factory=CallContext)


# --- adapter contract ----------------------------------------------------------------


class IntegrationProvider(abc.ABC):
    """Base adapter. `health_check` must be safe and non-mutating (no sends/charges)."""

    key: str = ""
    capabilities: frozenset[str] = frozenset()

    def validate_configuration(  # noqa: B027 - optional hook
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        """Raise ConfigurationInvalid for bad input. Must not perform network I/O."""

    @abc.abstractmethod
    async def health_check(self, ctx: ProviderContext) -> HealthResult: ...

    async def execute(
        self, ctx: ProviderContext, operation: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        raise BusinessRuleViolation(
            "UNSUPPORTED_OPERATION", "This integration does not support that operation"
        )


class WebhookReceiver(abc.ABC):
    """Inbound webhook support for an adapter."""

    @abc.abstractmethod
    def verify_webhook(
        self,
        headers: Mapping[str, str],
        body: bytes,
        credentials: Mapping[str, str],
        settings: Settings,
        now: float,
    ) -> bool: ...

    @abc.abstractmethod
    def parse_webhook(self, body: bytes) -> list[NormalizedEvent]: ...

    def handshake(
        self, params: Mapping[str, str], credentials: Mapping[str, str], settings: Settings
    ) -> str | None:
        """Answer a GET verification challenge, or None when not applicable/invalid."""
        return None


class MessagingProvider(IntegrationProvider):
    @abc.abstractmethod
    async def send_text(self, ctx: ProviderContext, recipient: str, text: str) -> SendResult: ...


class WhatsAppProvider(MessagingProvider, WebhookReceiver):
    @abc.abstractmethod
    async def send_media(
        self,
        ctx: ProviderContext,
        recipient: str,
        media_type: str,
        link: str,
        caption: str | None = None,
    ) -> SendResult: ...

    @abc.abstractmethod
    async def get_media(self, ctx: ProviderContext, media_id: str) -> MediaItem: ...

    @abc.abstractmethod
    async def phone_identity(self, ctx: ProviderContext) -> Mapping[str, Any]: ...


class EmailProvider(IntegrationProvider):
    @abc.abstractmethod
    async def send_email(self, ctx: ProviderContext, message: EmailMessage) -> SendResult: ...

    async def send_template(
        self, ctx: ProviderContext, template: str, to: Sequence[str], variables: Mapping[str, str]
    ) -> SendResult:
        """Render a platform template (app.integrations.email) and send it."""
        from app.integrations.email import render_template

        rendered = render_template(template, variables)
        return await self.send_email(
            ctx,
            EmailMessage(to=to, subject=rendered.subject, text=rendered.text, html=rendered.html),
        )


class StorageProvider(IntegrationProvider):
    @abc.abstractmethod
    async def upload(
        self, ctx: ProviderContext, key: str, content: bytes, content_type: str
    ) -> ObjectMetadata: ...

    @abc.abstractmethod
    async def download(self, ctx: ProviderContext, key: str) -> bytes: ...

    @abc.abstractmethod
    async def delete(self, ctx: ProviderContext, key: str) -> None: ...

    @abc.abstractmethod
    async def exists(self, ctx: ProviderContext, key: str) -> bool: ...

    @abc.abstractmethod
    def signed_url(
        self, ctx: ProviderContext, key: str, expires_seconds: int, method: str = "GET"
    ) -> str: ...

    @abc.abstractmethod
    async def metadata(self, ctx: ProviderContext, key: str) -> ObjectMetadata: ...


class PaymentProvider(IntegrationProvider):
    @abc.abstractmethod
    async def create_payment_intent(
        self,
        ctx: ProviderContext,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: Mapping[str, str] | None = None,
    ) -> PaymentIntent: ...

    @abc.abstractmethod
    async def retrieve_payment_intent(
        self, ctx: ProviderContext, intent_id: str
    ) -> PaymentIntent: ...


class CustomerSyncSource(abc.ABC):
    """Implemented only by adapters that truly pull customers."""

    @abc.abstractmethod
    async def list_customers(
        self, ctx: ProviderContext, cursor: str | None, limit: int
    ) -> SyncPage[ExternalCustomer]: ...


class CalendarProvider(IntegrationProvider):
    """Interface only (no adapter yet)."""

    @abc.abstractmethod
    async def list_events(
        self, ctx: ProviderContext, start: datetime, end: datetime
    ) -> list[Mapping[str, Any]]: ...

    @abc.abstractmethod
    async def create_event(
        self, ctx: ProviderContext, event: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class AccountingProvider(IntegrationProvider):
    """Interface only (no adapter yet)."""

    @abc.abstractmethod
    async def push_invoice(
        self, ctx: ProviderContext, invoice: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    @abc.abstractmethod
    async def list_accounts(self, ctx: ProviderContext) -> list[Mapping[str, Any]]: ...


class CommerceProvider(IntegrationProvider):
    """Interface only (no adapter yet)."""

    @abc.abstractmethod
    async def list_orders(
        self, ctx: ProviderContext, cursor: str | None
    ) -> SyncPage[Mapping[str, Any]]: ...

    @abc.abstractmethod
    async def list_products(
        self, ctx: ProviderContext, cursor: str | None
    ) -> SyncPage[Mapping[str, Any]]: ...


class OutboundWebhookProvider(IntegrationProvider):
    @abc.abstractmethod
    async def deliver(
        self, ctx: ProviderContext, event_type: str, event_id: str, body: bytes
    ) -> int: ...


class IntegrationRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, IntegrationDefinition] = {}
        self._providers: dict[str, IntegrationProvider] = {}

    def register(
        self, definition: IntegrationDefinition, provider: IntegrationProvider | None = None
    ) -> IntegrationDefinition:
        if definition.key in self._definitions:
            raise ValueError(f"Integration {definition.key} is already registered")
        if provider is None and definition.availability != "planned":
            raise ValueError(f"Integration {definition.key} needs an adapter or 'planned'")
        if provider is not None and provider.key != definition.key:
            raise ValueError("Adapter key does not match its definition")
        if definition.syncs and not isinstance(provider, CustomerSyncSource):
            raise ValueError(f"Integration {definition.key} declares sync without an adapter")
        self._definitions[definition.key] = definition
        if provider is not None:
            self._providers[definition.key] = provider
        return definition

    def definition(self, key: str) -> IntegrationDefinition | None:
        return self._definitions.get(key)

    def provider(self, key: str) -> IntegrationProvider | None:
        return self._providers.get(key)

    def all(self) -> list[IntegrationDefinition]:
        order = {"available": 0, "beta": 1, "planned": 2}
        return sorted(self._definitions.values(), key=lambda d: (order[d.availability], d.name))
