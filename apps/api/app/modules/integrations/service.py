"""Integration module services. Every query is tenant + environment scoped through
WorkspaceRepository; every connect/disconnect/rotate/test/replay is audited (redacted).
"""

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.pagination import Page, Pagination
from app.integrations import circuit, oauth
from app.integrations.catalog import REGISTRY
from app.integrations.circuit import Circuit
from app.integrations.crypto import CredentialManager, hint
from app.integrations.errors import CredentialsUnavailable, IntegrationError
from app.integrations.events import EVENT_TYPES, is_known
from app.integrations.http import CallContext, OutboundClient, validate_outbound_url
from app.integrations.outbox import delivery_job_id, emit
from app.integrations.providers.base import EMAIL
from app.integrations.providers.stripe import StripeProvider
from app.integrations.registry import (
    ConfigurationInvalid,
    IntegrationDefinition,
    ProviderContext,
    WebhookReceiver,
)
from app.integrations.runtime import CONNECTION_STATES, ConnectionRuntime, transition
from app.integrations.sync import SYNC_STATES, sync_job_id
from app.integrations.webhooks import inbound_job_id, new_endpoint_token
from app.modules.audit.service import record
from app.modules.integrations.models import (
    Delivery,
    InboundEvent,
    IntegrationActivity,
    IntegrationConnection,
    SyncJob,
    WebhookSubscription,
)
from app.modules.integrations.schemas import (
    ActivityView,
    ConfigFieldView,
    ConnectionCreate,
    ConnectionDetail,
    ConnectionHealth,
    ConnectionUpdate,
    ConnectionView,
    CredentialView,
    DefinitionView,
    DeliveryView,
    FailureView,
    HealthDetail,
    HealthSummary,
    HealthView,
    InboundEventView,
    OptionView,
    SyncJobView,
    SyncRequest,
    SyncStats,
    TestResult,
    WebhookCreate,
    WebhookCreated,
    WebhookUpdate,
    WebhookView,
)
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository, to_page

ENDPOINT_TOKEN_KEY = "__endpoint_token"
MAX_CONNECTIONS = 100
MAX_SUBSCRIPTIONS = 25


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Runtime:
    """Request-bound infrastructure handed to the service by the route layer."""

    settings: Settings
    http: OutboundClient
    queue: Any = None
    redis: Any = None


def definition_view(definition: IntegrationDefinition, count: int) -> DefinitionView:
    return DefinitionView(
        key=definition.key,
        name=definition.name,
        description=definition.description,
        category=definition.category,
        provider=definition.provider,
        availability=definition.availability,
        auth_type=definition.auth_type,
        capabilities=list(definition.capabilities),
        supported_scopes=list(definition.supported_scopes),
        required_scopes=list(definition.required_scopes),
        webhook_support=definition.webhook_support,
        sync_support=list(definition.sync_support),
        supports_sandbox=definition.supports_sandbox,
        documentation_url=definition.documentation_url,
        version=definition.version,
        config_schema=[
            ConfigFieldView(
                key=f.key,
                label=f.label,
                type=f.type,
                required=f.required,
                secret=f.secret,
                help=f.help,
                options=[OptionView(value=v, label=lbl) for v, lbl in f.options]
                if f.type == "select"
                else None,
            )
            for f in definition.config_schema
        ],
        connection_count=count,
    )


def _coerce_config(
    definition: IntegrationDefinition,
    config: dict[str, Any],
    settings: Settings,
    *,
    partial: bool = False,
) -> dict[str, Any]:
    fields = {f.key: f for f in definition.config_schema}
    result: dict[str, Any] = {}
    for key, value in config.items():
        spec = fields.get(key)
        if spec is None:
            raise ConfigurationInvalid("Unknown configuration field", key)
        if spec.secret:
            # Secrets never travel in plain configuration (would be stored unencrypted).
            raise ConfigurationInvalid("Send this field as a credential", key)
        if value is None or value == "":
            if spec.required and not partial:
                raise ConfigurationInvalid(f"{spec.label} is required", key)
            continue
        if spec.type == "number":
            try:
                value = int(value) if float(value).is_integer() else float(value)
            except (TypeError, ValueError):
                raise ConfigurationInvalid(f"{spec.label} must be a number", key) from None
        elif spec.type == "boolean":
            if not isinstance(value, bool):
                raise ConfigurationInvalid(f"{spec.label} must be true or false", key)
        else:
            value = str(value).strip()
            if len(value) > spec.max_length:
                raise ConfigurationInvalid(f"{spec.label} is too long", key)
            if spec.type == "url":
                parts = urlsplit(value)
                allowed = ("https",) if settings.app_env == "production" else ("https", "http")
                if parts.scheme not in allowed or not parts.hostname or parts.username:
                    raise ConfigurationInvalid(f"{spec.label} must be an HTTPS URL", key)
            if spec.type == "email" and not EMAIL.fullmatch(value):
                raise ConfigurationInvalid(f"{spec.label} must be an email address", key)
            if spec.type == "select" and value not in {v for v, _ in spec.options}:
                raise ConfigurationInvalid(f"Choose a valid {spec.label.lower()}", key)
        result[key] = value
    if not partial:
        for spec in definition.config_schema:
            if spec.required and not spec.secret and spec.key not in result:
                raise ConfigurationInvalid(f"{spec.label} is required", spec.key)
    return result


def _check_credentials(
    definition: IntegrationDefinition, credentials: dict[str, str], *, require_all: bool
) -> None:
    secret_fields = {f.key: f for f in definition.config_schema if f.secret}
    for key in credentials:
        if key not in secret_fields:
            raise ConfigurationInvalid("Unknown credential field", key)
    if require_all and definition.auth_type not in ("oauth2", "oauth2_pkce"):
        for key, spec in secret_fields.items():
            if spec.required and not credentials.get(key):
                raise ConfigurationInvalid(f"{spec.label} is required", key)


class IntegrationService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope, runtime: Runtime) -> None:
        self.session, self.scope, self.rt = session, scope, runtime
        self.settings = runtime.settings
        self.connections = WorkspaceRepository(session, IntegrationConnection, scope)
        self.subscriptions = WorkspaceRepository(session, WebhookSubscription, scope)
        self.deliveries = WorkspaceRepository(session, Delivery, scope)
        self.events = WorkspaceRepository(session, InboundEvent, scope)
        self.jobs = WorkspaceRepository(session, SyncJob, scope)
        self.activities = WorkspaceRepository(session, IntegrationActivity, scope)
        self.credentials = CredentialManager(runtime.settings)
        self._after_commit: list[tuple[str, str, str]] = []

    # --- helpers -------------------------------------------------------------------------

    def definition(self, key: str) -> IntegrationDefinition:
        definition = REGISTRY.definition(key)
        if definition is None:
            raise ResourceNotFound
        return definition

    def runtime(self) -> ConnectionRuntime:
        return ConnectionRuntime(self.session, self.settings, self.rt.http, redis=self.rt.redis)

    async def audit(
        self,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        outcome: str = "success",
        **details: Any,
    ) -> None:
        await record(
            self.session,
            action,
            scope=self.scope,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            details=details,
        )

    def webhook_url(self, connection: IntegrationConnection) -> str | None:
        if not connection.webhook_token_hash or not connection.credentials_encrypted:
            return None
        base = self.settings.integrations_public_base_url
        if not base or not self.credentials.configured:
            return None
        try:
            token = self.credentials.decrypt_json(connection.credentials_encrypted).get(
                ENDPOINT_TOKEN_KEY
            )
        except IntegrationError:
            return None
        if not token:
            return None
        return f"{base.rstrip('/')}/api/v1/webhooks/{connection.integration_key}/{token}"

    async def detail(self, connection: IntegrationConnection) -> ConnectionDetail:
        # Server-side onupdate timestamps are expired after a flush; reload them.
        await self.session.refresh(connection)
        definition = REGISTRY.definition(connection.integration_key)
        hints = connection.credential_hints or {}
        creds = [
            CredentialView(key=f.key, set=f.key in hints, hint=hints.get(f.key))
            for f in (definition.config_schema if definition else ())
            if f.secret
        ]
        activity = await self.session.scalars(
            self.activities.select()
            .where(IntegrationActivity.connection_id == connection.id)
            .order_by(IntegrationActivity.created_at.desc())
            .limit(10)
        )
        base = ConnectionView.model_validate(connection).model_dump()
        return ConnectionDetail(
            **base,
            config=dict(connection.config),
            credentials=creds,
            scopes=list(connection.scopes),
            sync_direction=connection.sync_direction,
            health_detail=HealthDetail(
                latency_ms=connection.last_latency_ms,
                consecutive_failures=connection.consecutive_failures,
                rate_limited_until=connection.rate_limited_until,
            ),
            recent_activity=[
                ActivityView(at=a.created_at, kind=a.kind, outcome=a.outcome, message=a.message)
                for a in activity
            ],
            webhook_url=self.webhook_url(connection),
        )

    # --- directory -------------------------------------------------------------------------

    async def definitions(self) -> list[DefinitionView]:
        counts = dict(
            (
                await self.session.execute(
                    select(IntegrationConnection.integration_key, func.count())
                    .where(self.connections.predicate(), IntegrationConnection.status != "revoked")
                    .group_by(IntegrationConnection.integration_key)
                )
            )
            .tuples()
            .all()
        )
        return [definition_view(d, int(counts.get(d.key, 0))) for d in REGISTRY.all()]

    # --- connections -----------------------------------------------------------------------

    async def list_connections(
        self, page: Pagination, integration_key: str | None, status: str | None
    ) -> Page[ConnectionView]:
        statement = self.connections.select()
        if integration_key:
            statement = statement.where(IntegrationConnection.integration_key == integration_key)
        if status:
            statement = statement.where(IntegrationConnection.status == status)
        rows, total = await self.connections.page(
            statement.order_by(IntegrationConnection.created_at.desc(), IntegrationConnection.id),
            page,
        )
        return to_page(ConnectionView, rows, total, page)

    async def get(self, connection_id: UUID, *, for_update: bool = False) -> IntegrationConnection:
        return await self.connections.get(connection_id, for_update=for_update)

    def _store_credentials(self, connection: IntegrationConnection, creds: dict[str, str]) -> None:
        public = {k: v for k, v in creds.items() if not k.startswith("__")}
        if not creds:
            connection.credentials_encrypted, connection.credential_hints = None, {}
            return
        connection.credentials_encrypted = self.credentials.encrypt_json(creds)
        connection.credential_hints = {k: hint(v) for k, v in public.items()}

    async def create(self, data: ConnectionCreate) -> IntegrationConnection:
        self.scope.require("integrations.manage")
        definition = self.definition(data.integration_key)
        if not definition.connectable:
            raise BusinessRuleViolation("NOT_CONNECTABLE", "This integration is not available yet")
        provider = REGISTRY.provider(definition.key)
        assert provider is not None
        if data.mode == "sandbox" and not definition.supports_sandbox:
            raise BusinessRuleViolation(
                "SANDBOX_UNSUPPORTED", "This integration has no sandbox mode"
            )
        count = await self.session.scalar(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(self.connections.predicate(), IntegrationConnection.status != "revoked")
        )
        if int(count or 0) >= MAX_CONNECTIONS:
            raise BusinessRuleViolation("LIMIT_REACHED", "Connection limit reached")
        config = _coerce_config(definition, dict(data.config), self.settings)
        credentials = {k: v for k, v in data.credentials.items() if v}
        _check_credentials(definition, credentials, require_all=True)
        provider.validate_configuration(config, credentials, self.settings)
        if isinstance(provider, StripeProvider) and credentials.get("secret_key"):
            provider.check_mode(credentials["secret_key"], data.mode)
        token_hash: str | None = None
        if definition.webhook_support and isinstance(provider, WebhookReceiver):
            token, token_hash = new_endpoint_token()
            credentials[ENDPOINT_TOKEN_KEY] = token
        if credentials and not self.credentials.configured:
            raise CredentialsUnavailable
        connection = self.connections.new(
            integration_key=definition.key,
            display_name=data.display_name,
            mode=data.mode,
            status="draft",
            config=config,
            scopes=list(definition.required_scopes),
            sync_direction=next((d for d in definition.sync_support if d != "none"), "none"),
            webhook_token_hash=token_hash,
            created_by_user_id=self.scope.user_id,
        )
        self._store_credentials(connection, credentials)
        await self.connections.add(connection)
        await self.audit(
            "integration.connection.created",
            "integration_connection",
            connection.id,
            integration=definition.key,
            mode=data.mode,
            credential_fields=sorted(k for k in credentials if not k.startswith("__")),
        )
        return connection

    def can_test(self, connection: IntegrationConnection) -> bool:
        definition = REGISTRY.definition(connection.integration_key)
        if definition is None or not definition.connectable:
            return False
        if definition.auth_type in ("oauth2", "oauth2_pkce"):
            return (
                bool(connection.credential_hints.get("access_token"))
                or connection.status == "connected"
            )
        return True

    async def test(self, connection_id: UUID) -> TestResult:
        self.scope.require("integrations.operate")
        return await self.run_test(await self.get(connection_id, for_update=True))

    async def run_test(self, connection: IntegrationConnection) -> TestResult:
        """Safe, non-mutating provider check; records health and transitions status."""
        if connection.status in ("revoked", "disabled"):
            raise BusinessRuleViolation(
                "CONNECTION_INACTIVE", "Enable this connection before testing it", 409
            )
        runtime = self.runtime()
        provider = runtime.provider(connection)
        before = connection.status
        call = CallContext(request_id=self.scope.request_id)
        try:
            if isinstance(provider, StripeProvider):
                creds = runtime.context(connection).credentials
                if creds.get("secret_key"):
                    provider.check_mode(creds["secret_key"], connection.mode)

            async def check(ctx: ProviderContext) -> Any:
                return await provider.health_check(ctx)

            if connection.status == "draft":
                transition(connection, "connecting")
            health, latency = await runtime.call(
                connection, check, kind="test", call=call, enforce_status=False
            )
            message, ok = health.message, True
            connection.last_latency_ms = latency
        except IntegrationError as error:
            message, ok, latency = error.message, False, None
        except ConfigurationInvalid as error:
            message, ok, latency = error.message, False, None
            await runtime.record_failure(
                connection,
                IntegrationError(error.code, error.message, kind="configuration"),
                runtime_circuit(connection, self.settings),
                kind="test",
            )
        if connection.status == "connecting":
            transition(connection, "connected" if ok else "error")
        await self._status_events(connection, before)
        await self.audit(
            "integration.connection.tested",
            "integration_connection",
            connection.id,
            "success" if ok else "failure",
            integration=connection.integration_key,
        )
        return TestResult(
            ok=ok,
            status=connection.status,
            latency_ms=latency,
            message=message[:300],
            checked_at=now(),
        )

    async def _status_events(self, connection: IntegrationConnection, before: str) -> None:
        payload = {
            "connection_id": str(connection.id),
            "integration_key": connection.integration_key,
            "status": connection.status,
        }
        if connection.status == "connected" and before != "connected":
            connection.connected_at = connection.connected_at or now()
            await emit(
                self.session,
                self.scope,
                "integration.connected",
                payload,
                origin=f"integration:{connection.id}",
            )
        elif connection.status in ("error", "degraded", "expired") and before == "connected":
            await emit(
                self.session,
                self.scope,
                "integration.failed",
                payload,
                origin=f"integration:{connection.id}",
            )

    async def update(self, connection_id: UUID, data: ConnectionUpdate) -> IntegrationConnection:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        if connection.status == "revoked":
            raise BusinessRuleViolation(
                "CONNECTION_REVOKED", "This connection was disconnected", 409
            )
        definition = self.definition(connection.integration_key)
        changed: list[str] = []
        if data.display_name is not None:
            connection.display_name = data.display_name
            changed.append("display_name")
        if data.config is not None:
            merged = {
                **connection.config,
                **_coerce_config(definition, dict(data.config), self.settings, partial=True),
            }
            for key, value in data.config.items():
                if value in (None, ""):
                    merged.pop(key, None)
            merged = _coerce_config(definition, merged, self.settings)
            provider = REGISTRY.provider(definition.key)
            if provider is not None:
                creds = (
                    self.credentials.decrypt_json(connection.credentials_encrypted)
                    if connection.credentials_encrypted
                    else {}
                )
                creds.pop(ENDPOINT_TOKEN_KEY, None)
                provider.validate_configuration(merged, creds, self.settings)
            connection.config = merged
            changed.append("config")
        await self.session.flush()
        await self.audit(
            "integration.connection.updated",
            "integration_connection",
            connection.id,
            fields=changed,
        )
        return connection

    async def rotate(
        self, connection_id: UUID, credentials: dict[str, str]
    ) -> IntegrationConnection:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        if connection.status == "revoked":
            raise BusinessRuleViolation(
                "CONNECTION_REVOKED", "This connection was disconnected", 409
            )
        definition = self.definition(connection.integration_key)
        _check_credentials(definition, credentials, require_all=False)
        existing = self.credentials.decrypt_json(connection.credentials_encrypted)
        merged = {**existing, **credentials}
        provider = REGISTRY.provider(definition.key)
        if provider is not None:
            provider.validate_configuration(
                connection.config,
                {k: v for k, v in merged.items() if not k.startswith("__")},
                self.settings,
            )
        if isinstance(provider, StripeProvider) and merged.get("secret_key"):
            provider.check_mode(str(merged["secret_key"]), connection.mode)
        self._store_credentials(connection, {k: str(v) for k, v in merged.items()})
        # New credentials reset failure state; the follow-up test decides the status.
        connection.consecutive_failures, connection.circuit_failure_count = 0, 0
        connection.circuit_state, connection.circuit_opened_at = "closed", None
        connection.rate_limited_until = None
        if connection.status not in ("disabled", "draft", "connecting"):
            transition(connection, "connecting")
        await self.session.flush()
        await self.audit(
            "integration.credentials.rotated",
            "integration_connection",
            connection.id,
            fields=sorted(credentials),
        )
        return connection

    async def enable(self, connection_id: UUID) -> IntegrationConnection:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        if connection.status != "disabled":
            if connection.status == "revoked":
                raise BusinessRuleViolation(
                    "CONNECTION_REVOKED", "This connection was disconnected", 409
                )
            return connection
        transition(connection, "connecting")
        connection.disabled_at = None
        await self.session.flush()
        await self.audit("integration.connection.enabled", "integration_connection", connection.id)
        return connection

    async def disable(self, connection_id: UUID) -> IntegrationConnection:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        if connection.status == "disabled":
            return connection
        transition(connection, "disabled")
        connection.disabled_at = now()
        await self.session.flush()
        await self.audit("integration.connection.disabled", "integration_connection", connection.id)
        return connection

    async def disconnect(self, connection_id: UUID) -> None:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        if connection.status == "revoked":
            return
        definition = REGISTRY.definition(connection.integration_key)
        if definition and definition.oauth and connection.credentials_encrypted:
            try:
                await oauth.revoke(self.settings, self.rt.http, connection, definition)
            except Exception:
                pass  # best effort: local credentials are destroyed regardless
        transition(connection, "revoked")
        connection.revoked_at = now()
        connection.credentials_encrypted, connection.credential_hints = None, {}
        connection.webhook_token_hash = None
        connection.health = "unknown"
        await self.session.execute(
            update(SyncJob)
            .where(
                self.jobs.predicate(),
                SyncJob.connection_id == connection.id,
                SyncJob.status.in_(("pending", "running", "paused", "failed")),
            )
            .values(status="cancelled", finished_at=now())
        )
        await self.session.flush()
        await emit(
            self.session,
            self.scope,
            "integration.disconnected",
            {"connection_id": str(connection.id), "integration_key": connection.integration_key},
            origin=f"integration:{connection.id}",
        )
        await self.audit(
            "integration.connection.disconnected",
            "integration_connection",
            connection.id,
            integration=connection.integration_key,
        )

    async def oauth_start(self, connection_id: UUID) -> str:
        self.scope.require("integrations.manage")
        connection = await self.get(connection_id, for_update=True)
        definition = self.definition(connection.integration_key)
        if not definition.connectable:
            raise BusinessRuleViolation("NOT_CONNECTABLE", "This integration is not available yet")
        if connection.status in ("revoked", "disabled"):
            raise BusinessRuleViolation("CONNECTION_INACTIVE", "This connection is not active", 409)
        url = await oauth.start(self.session, self.settings, self.scope, connection, definition)
        if connection.status in ("draft", "error", "expired"):
            transition(connection, "connecting")
        await self.audit("integration.oauth.started", "integration_connection", connection.id)
        return url

    # --- outbound webhooks -------------------------------------------------------------------

    def event_types(self) -> list[tuple[str, str]]:
        return sorted(EVENT_TYPES.items())

    async def list_webhooks(self, page: Pagination) -> Page[WebhookView]:
        statement = self.subscriptions.select().where(WebhookSubscription.deleted_at.is_(None))
        rows, total = await self.subscriptions.page(
            statement.order_by(WebhookSubscription.created_at.desc(), WebhookSubscription.id),
            page,
        )
        return to_page(WebhookView, rows, total, page)

    async def _subscription(
        self, subscription_id: UUID, *, lock: bool = False
    ) -> WebhookSubscription:
        row = await self.subscriptions.get(subscription_id, for_update=lock)
        if row.deleted_at is not None:
            raise ResourceNotFound
        return row

    async def _check_url(self, url: str) -> str:
        validated = await validate_outbound_url(url, self.settings, resolver=self.rt.http.resolver)
        return validated.url

    @staticmethod
    def _event_types(types: Sequence[str]) -> list[str]:
        unique = list(dict.fromkeys(types))
        if any(not is_known(t) for t in unique):
            raise BusinessRuleViolation("UNKNOWN_EVENT_TYPE", "Unknown event type")
        return unique

    def _new_secret(self) -> tuple[str, str, str]:
        secret = "whsec_" + secrets.token_urlsafe(32)
        return secret, self.credentials.encrypt(secret), hint(secret)

    async def create_webhook(self, data: WebhookCreate) -> WebhookCreated:
        self.scope.require("integrations.manage")
        count = await self.session.scalar(
            select(func.count())
            .select_from(WebhookSubscription)
            .where(self.subscriptions.predicate(), WebhookSubscription.deleted_at.is_(None))
        )
        if int(count or 0) >= MAX_SUBSCRIPTIONS:
            raise BusinessRuleViolation("LIMIT_REACHED", "Webhook limit reached")
        url = await self._check_url(data.url)
        types = self._event_types(data.event_types)
        secret, encrypted, secret_hint = self._new_secret()
        row = self.subscriptions.new(
            name=data.name,
            url=url,
            event_types=types,
            enabled=data.enabled,
            secret_encrypted=encrypted,
            secret_hint=secret_hint,
            created_by_user_id=self.scope.user_id,
        )
        await self.subscriptions.add(row)
        await self.audit(
            "integration.webhook.created", "webhook_subscription", row.id, event_types=types
        )
        return WebhookCreated(**WebhookView.model_validate(row).model_dump(), signing_secret=secret)

    async def update_webhook(self, subscription_id: UUID, data: WebhookUpdate) -> WebhookView:
        self.scope.require("integrations.manage")
        row = await self._subscription(subscription_id, lock=True)
        if data.name is not None:
            row.name = data.name
        if data.url is not None:
            row.url = await self._check_url(data.url)
        if data.event_types is not None:
            row.event_types = self._event_types(data.event_types)
        if data.enabled is not None:
            row.enabled = data.enabled
        await self.session.flush()
        await self.audit(
            "integration.webhook.updated",
            "webhook_subscription",
            row.id,
            fields=sorted(data.model_dump(exclude_none=True)),
        )
        await self.session.refresh(row)
        return WebhookView.model_validate(row)

    async def rotate_webhook_secret(self, subscription_id: UUID) -> WebhookCreated:
        self.scope.require("integrations.manage")
        row = await self._subscription(subscription_id, lock=True)
        secret, encrypted, secret_hint = self._new_secret()
        row.secret_encrypted, row.secret_hint = encrypted, secret_hint
        await self.session.flush()
        await self.audit("integration.webhook.secret_rotated", "webhook_subscription", row.id)
        await self.session.refresh(row)
        return WebhookCreated(**WebhookView.model_validate(row).model_dump(), signing_secret=secret)

    async def delete_webhook(self, subscription_id: UUID) -> None:
        self.scope.require("integrations.manage")
        row = await self._subscription(subscription_id, lock=True)
        row.deleted_at, row.enabled = now(), False
        await self.session.execute(
            update(Delivery)
            .where(
                self.deliveries.predicate(),
                Delivery.subscription_id == row.id,
                Delivery.status.in_(("pending", "failed")),
            )
            .values(status="cancelled", next_attempt_at=None)
        )
        await self.session.flush()
        await self.audit("integration.webhook.deleted", "webhook_subscription", row.id)

    @staticmethod
    def delivery_view(row: Delivery) -> DeliveryView:
        return DeliveryView(
            id=row.id,
            subscription_id=row.subscription_id,
            event_type=row.event_type,
            event_id=row.outbox_event_id,
            status=row.status,
            attempt_count=row.attempt_count,
            response_status=row.response_status,
            last_error=row.last_error,
            next_attempt_at=row.next_attempt_at,
            created_at=row.created_at,
            delivered_at=row.delivered_at,
        )

    async def list_deliveries(self, subscription_id: UUID, page: Pagination) -> Page[DeliveryView]:
        await self._subscription(subscription_id)
        rows, total = await self.deliveries.page(
            self.deliveries.select()
            .where(Delivery.subscription_id == subscription_id)
            .order_by(Delivery.created_at.desc(), Delivery.id),
            page,
        )
        return Page(
            items=[self.delivery_view(r) for r in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def retry_delivery(self, delivery_id: UUID) -> DeliveryView:
        self.scope.require("integrations.operate")
        row = await self.deliveries.get(delivery_id, for_update=True)
        subscription = await self.subscriptions.get(row.subscription_id)
        if subscription.deleted_at is not None or not subscription.enabled:
            raise BusinessRuleViolation(
                "SUBSCRIPTION_DISABLED", "Enable the webhook before retrying", 409
            )
        if row.status in ("failed", "dead_letter"):
            row.status, row.next_attempt_at = "pending", None
            row.max_attempts = row.attempt_count + self.settings.delivery_max_attempts
            await self.session.flush()
            await self.audit("integration.delivery.retried", "integration_delivery", row.id)
            self._after_commit.append(
                ("deliver_webhook", str(row.id), delivery_job_id(row.id, row.attempt_count))
            )
        elif row.status not in ("pending", "running"):
            raise BusinessRuleViolation("NOT_RETRYABLE", "This delivery cannot be retried", 409)
        return self.delivery_view(row)

    # --- inbound events ------------------------------------------------------------------

    async def list_events(
        self,
        page: Pagination,
        connection_id: UUID | None,
        status: str | None,
        event_type: str | None,
    ) -> Page[InboundEventView]:
        statement = self.events.select()
        if connection_id:
            statement = statement.where(InboundEvent.connection_id == connection_id)
        if status:
            statement = statement.where(InboundEvent.status == status)
        if event_type:
            statement = statement.where(InboundEvent.event_type == event_type)
        rows, total = await self.events.page(
            statement.order_by(InboundEvent.received_at.desc(), InboundEvent.id), page
        )
        return to_page(InboundEventView, rows, total, page)

    async def replay_event(self, event_id: UUID) -> InboundEventView:
        self.scope.require("integrations.operate")
        row = await self.events.get(event_id, for_update=True)
        if row.status in ("processed", "ignored", "failed", "dead_letter"):
            row.status, row.next_attempt_at, row.error_code = "queued", None, None
            await self.session.flush()
            await self.audit(
                "integration.event.replayed",
                "integration_inbound_event",
                row.id,
                integration=row.integration_key,
            )
            self._after_commit.append(
                ("process_inbound_event", str(row.id), inbound_job_id(row.id, row.attempt_count))
            )
        await self.session.refresh(row)
        return InboundEventView.model_validate(row)

    # --- sync jobs -------------------------------------------------------------------------

    @staticmethod
    def job_view(row: SyncJob) -> SyncJobView:
        return SyncJobView(
            id=row.id,
            connection_id=row.connection_id,
            integration_key=row.integration_key,
            entity=row.entity,
            direction=row.direction,
            mode=row.mode,
            status=row.status,
            cursor=row.cursor,
            stats=SyncStats(
                **{k: int(v) for k, v in (row.stats or {}).items() if k in SyncStats.model_fields}
            ),
            started_at=row.started_at,
            finished_at=row.finished_at,
            last_error=row.last_error,
            created_at=row.created_at,
        )

    async def list_jobs(
        self, page: Pagination, connection_id: UUID | None, status: str | None
    ) -> Page[SyncJobView]:
        statement = self.jobs.select()
        if connection_id:
            statement = statement.where(SyncJob.connection_id == connection_id)
        if status:
            statement = statement.where(SyncJob.status == status)
        rows, total = await self.jobs.page(
            statement.order_by(SyncJob.created_at.desc(), SyncJob.id), page
        )
        return Page(
            items=[self.job_view(r) for r in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def start_sync(self, connection_id: UUID, data: SyncRequest) -> SyncJobView:
        self.scope.require("integrations.operate")
        connection = await self.get(connection_id)
        definition = self.definition(connection.integration_key)
        policy = definition.sync_policy(data.entity) if definition.syncs else None
        if policy is None:
            raise BusinessRuleViolation(
                "SYNC_UNSUPPORTED", "This integration does not support that sync"
            )
        if connection.status not in ("connected", "degraded"):
            raise BusinessRuleViolation(
                "CONNECTION_INACTIVE", "Connect this integration before syncing", 409
            )
        job = self.jobs.new(
            connection_id=connection.id,
            integration_key=connection.integration_key,
            entity=data.entity,
            direction=policy.direction,
            mode=data.mode,
            status="pending",
            stats={},
            requested_by_user_id=self.scope.user_id,
        )
        try:
            async with self.session.begin_nested():
                await self.jobs.add(job)
        except IntegrityError:
            raise Conflict("A sync for this data is already running") from None
        await self.audit(
            "integration.sync.started",
            "integration_sync_job",
            job.id,
            entity=data.entity,
            mode=data.mode,
        )
        self._after_commit.append(("run_sync_job", str(job.id), sync_job_id(job.id, 0)))
        return self.job_view(job)

    async def control_job(self, job_id: UUID, action: str) -> SyncJobView:
        self.scope.require("integrations.operate")
        job = await self.jobs.get(job_id, for_update=True)
        targets = {
            "pause": "paused",
            "resume": "pending",
            "cancel": "cancelled",
            "retry": "pending",
        }
        target = targets[action]
        if action == "resume" and job.status != "paused":
            raise BusinessRuleViolation("INVALID_TRANSITION", "Only paused jobs can be resumed")
        if action == "retry" and job.status not in ("failed", "dead_letter"):
            raise BusinessRuleViolation("INVALID_TRANSITION", "Only failed jobs can be retried")
        if job.status == target:
            return self.job_view(job)
        SYNC_STATES.ensure(job.status, target)
        if target == "pending":
            try:
                async with self.session.begin_nested():
                    job.status, job.finished_at, job.last_error = "pending", None, None
                    await self.session.flush()
            except IntegrityError:
                raise Conflict("A sync for this data is already running") from None
            self._after_commit.append(
                ("run_sync_job", str(job.id), sync_job_id(job.id, job.attempt_count))
            )
        else:
            job.status = target
            if target == "cancelled":
                job.finished_at = now()
            await self.session.flush()
        await self.audit(f"integration.sync.{action}", "integration_sync_job", job.id)
        return self.job_view(job)

    # --- failures + health -------------------------------------------------------------------

    async def failures(self, page: Pagination) -> Page[FailureView]:
        bad = ("failed", "dead_letter")
        window = page.offset + page.page_size
        deliveries = self.deliveries.select().where(Delivery.status.in_(bad))
        events = self.events.select().where(InboundEvent.status.in_(bad))
        jobs = self.jobs.select().where(SyncJob.status.in_(bad))
        total = 0
        for statement in (deliveries, events, jobs):
            total += int(
                await self.session.scalar(
                    select(func.count()).select_from(statement.order_by(None).subquery())
                )
                or 0
            )
        items: list[FailureView] = []
        for d in await self.session.scalars(
            deliveries.order_by(Delivery.updated_at.desc()).limit(window)
        ):
            items.append(
                FailureView(
                    id=d.id,
                    kind="delivery",
                    connection_id=None,
                    integration_key="generic_webhook",
                    summary=f"Webhook delivery of {d.event_type}",
                    error_code=None,
                    attempt_count=d.attempt_count,
                    status=d.status,
                    occurred_at=d.updated_at,
                    can_retry=True,
                )
            )
        for e in await self.session.scalars(
            events.order_by(InboundEvent.updated_at.desc()).limit(window)
        ):
            items.append(
                FailureView(
                    id=e.id,
                    kind="event",
                    connection_id=e.connection_id,
                    integration_key=e.integration_key,
                    summary=f"Inbound {e.event_type}",
                    error_code=e.error_code,
                    attempt_count=e.attempt_count,
                    status=e.status,
                    occurred_at=e.updated_at,
                    can_retry=True,
                )
            )
        for j in await self.session.scalars(jobs.order_by(SyncJob.updated_at.desc()).limit(window)):
            items.append(
                FailureView(
                    id=j.id,
                    kind="job",
                    connection_id=j.connection_id,
                    integration_key=j.integration_key,
                    summary=f"Sync of {j.entity}",
                    error_code=j.error_code,
                    attempt_count=j.attempt_count,
                    status=j.status,
                    occurred_at=j.updated_at,
                    can_retry=True,
                )
            )
        items.sort(key=lambda f: f.occurred_at, reverse=True)
        return Page(
            items=items[page.offset : window], total=total, page=page.page, page_size=page.page_size
        )

    async def health(self) -> HealthView:
        connections = list(
            await self.session.scalars(
                self.connections.select()
                .where(IntegrationConnection.status != "revoked")
                .order_by(IntegrationConnection.display_name)
                .limit(200)
            )
        )
        ids = [c.id for c in connections]
        failing_events: set[UUID] = set()
        job_states: dict[UUID, set[str]] = {}
        if ids:
            failing_events = set(
                await self.session.scalars(
                    select(InboundEvent.connection_id)
                    .where(
                        self.events.predicate(),
                        InboundEvent.connection_id.in_(ids),
                        InboundEvent.status.in_(("failed", "dead_letter")),
                    )
                    .distinct()
                )
            )
            for connection_id, status in await self.session.execute(
                select(SyncJob.connection_id, SyncJob.status)
                .where(
                    self.jobs.predicate(),
                    SyncJob.connection_id.in_(ids),
                    SyncJob.status.in_(("pending", "running", "failed", "dead_letter")),
                )
                .distinct()
            ):
                job_states.setdefault(connection_id, set()).add(status)
        summary = HealthSummary(connected=0, degraded=0, failing=0, disabled=0)
        views: list[ConnectionHealth] = []
        for c in connections:
            definition = REGISTRY.definition(c.integration_key)
            if c.status == "disabled":
                summary.disabled += 1
            elif c.health == "failing" or c.status in ("error", "expired"):
                summary.failing += 1
            elif c.health == "degraded" or c.status == "degraded":
                summary.degraded += 1
            elif c.status == "connected":
                summary.connected += 1
            states = job_states.get(c.id, set())
            sync_state = "not_applicable"
            if definition and definition.syncs:
                sync_state = (
                    "running"
                    if states & {"pending", "running"}
                    else "failing"
                    if states
                    else "idle"
                )
            webhook_state = "not_applicable"
            if definition and definition.webhook_support:
                webhook_state = "failing" if c.id in failing_events else "healthy"
            views.append(
                ConnectionHealth(
                    id=c.id,
                    display_name=c.display_name,
                    integration_key=c.integration_key,
                    status=c.status,
                    health=c.health,
                    circuit_state=c.circuit_state,
                    latency_ms=c.last_latency_ms,
                    last_success_at=c.last_success_at,
                    last_failure_at=c.last_failure_at,
                    rate_limited_until=c.rate_limited_until,
                    webhook_state=webhook_state,
                    sync_state=sync_state,
                )
            )
        return HealthView(summary=summary, connections=views)

    # --- after-commit job dispatch --------------------------------------------------------

    async def flush_jobs(self) -> None:
        """Enqueue jobs collected during the request; call after commit."""
        if self.rt.queue is None:
            return
        for name, arg, job_id in self._after_commit:
            await self.rt.queue.enqueue(name, arg, job_id=job_id)
        self._after_commit.clear()


def runtime_circuit(connection: IntegrationConnection, settings: Settings) -> Circuit:
    return circuit.load(
        connection, settings.circuit_failure_threshold, settings.circuit_cooldown_seconds
    )


__all__ = ["CONNECTION_STATES", "IntegrationService", "Runtime"]
