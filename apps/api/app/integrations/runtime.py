"""Connection runtime: build provider contexts and run provider calls under policy.

Every provider call made on behalf of a connection goes through `ConnectionRuntime.call`:
circuit breaker check -> per-connection/tenant rate limit -> adapter call -> recorded
outcome (health, latency, circuit, status transition, activity row). Health reads never
call providers; they read what this module recorded.
"""

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations import circuit as circuit_store
from app.integrations.catalog import REGISTRY
from app.integrations.circuit import Circuit
from app.integrations.crypto import CredentialManager
from app.integrations.errors import CircuitOpen, IntegrationError, RateLimited
from app.integrations.http import CallContext, OutboundClient, Resolver
from app.integrations.rate_limit import ProviderRateLimiter
from app.integrations.registry import IntegrationProvider, Mode, ProviderContext
from app.modules.integrations.models import IntegrationActivity, IntegrationConnection
from app.shared.state_machine import StateMachine

CONNECTION_STATES = StateMachine(
    "connection",
    {
        "draft": frozenset({"connecting", "connected", "error", "disabled", "revoked"}),
        "connecting": frozenset({"connected", "error", "draft", "disabled", "revoked"}),
        "connected": frozenset(
            {"degraded", "expired", "error", "disabled", "revoked", "connecting"}
        ),
        "degraded": frozenset(
            {"connected", "error", "expired", "disabled", "revoked", "connecting"}
        ),
        "expired": frozenset({"connecting", "connected", "error", "disabled", "revoked"}),
        "error": frozenset({"connecting", "connected", "disabled", "revoked", "draft"}),
        "disabled": frozenset({"connecting", "connected", "error", "revoked"}),
        "revoked": frozenset(),
    },
)
CALLABLE_STATES = frozenset({"connected", "degraded", "connecting", "draft", "error"})


def now() -> datetime:
    return datetime.now(UTC)


def transition(connection: IntegrationConnection, target: str) -> None:
    if connection.status == target:
        return
    CONNECTION_STATES.ensure(connection.status, target)
    connection.status = target


def outbound_client(
    settings: Settings, client: httpx.AsyncClient, resolver: Resolver | None = None
) -> OutboundClient:
    return OutboundClient(settings, client, resolver=resolver)


class ConnectionRuntime:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        http: OutboundClient,
        *,
        redis: Any = None,
    ) -> None:
        self.session, self.settings, self.http = session, settings, http
        self.credentials = CredentialManager(settings)
        self.limiter = ProviderRateLimiter(
            redis,
            settings.integration_rate_limit_per_minute,
            settings.integration_rate_limit_fallback_per_minute,
        )

    def provider(self, connection: IntegrationConnection) -> IntegrationProvider:
        provider = REGISTRY.provider(connection.integration_key)
        if provider is None:
            raise IntegrationError("NOT_CONNECTABLE", "This integration is not available yet")
        return provider

    def context(
        self, connection: IntegrationConnection, call: CallContext | None = None
    ) -> ProviderContext:
        creds = self.credentials.decrypt_json(connection.credentials_encrypted)
        creds.pop("__endpoint_token", None)
        mode: Mode = "sandbox" if connection.mode == "sandbox" else "production"
        return ProviderContext(
            settings=self.settings,
            http=self.http,
            config=dict(connection.config),
            credentials={k: str(v) for k, v in creds.items()},
            mode=mode,
            call=call or CallContext(),
        )

    async def call[T](
        self,
        connection: IntegrationConnection,
        operation: Callable[[ProviderContext], Awaitable[T]],
        *,
        kind: str,
        call: CallContext | None = None,
        enforce_status: bool = True,
    ) -> tuple[T, int]:
        if enforce_status and connection.status not in CALLABLE_STATES:
            raise IntegrationError("CONNECTION_INACTIVE", "This connection is not active")
        current = now()
        breaker = circuit_store.load(
            connection,
            self.settings.circuit_failure_threshold,
            self.settings.circuit_cooldown_seconds,
        )
        if not breaker.allow(current):
            raise CircuitOpen()
        circuit_store.store(breaker, connection)
        if connection.rate_limited_until and connection.rate_limited_until > current:
            raise RateLimited((connection.rate_limited_until - current).total_seconds())
        decision = await self.limiter.acquire(
            connection.integration_key, connection.tenant_id, connection.id
        )
        if not decision.allowed:
            raise RateLimited(decision.retry_after)
        ctx = self.context(connection, call)
        started = time.perf_counter()
        try:
            result = await operation(ctx)
        except IntegrationError as error:
            await self.record_failure(connection, error, breaker, kind=kind)
            raise
        latency = int((time.perf_counter() - started) * 1000)
        await self.record_success(connection, breaker, latency, kind=kind)
        return result, latency

    async def record_success(
        self,
        connection: IntegrationConnection,
        breaker: Circuit,
        latency: int,
        *,
        kind: str,
        message: str = "Call succeeded",
    ) -> None:
        breaker.record_success()
        circuit_store.store(breaker, connection)
        connection.consecutive_failures = 0
        connection.last_success_at = now()
        connection.last_latency_ms = latency
        connection.health = "healthy"
        connection.last_error = connection.last_error_code = None
        connection.rate_limited_until = None
        if connection.status in ("degraded", "error", "connecting", "draft", "expired"):
            transition(connection, "connected")
            connection.connected_at = connection.connected_at or now()
        if kind == "test":
            connection.last_health_check_at = now()
        await self.activity(connection, kind, "success", message, latency)

    async def record_failure(
        self,
        connection: IntegrationConnection,
        error: IntegrationError,
        breaker: Circuit,
        *,
        kind: str,
    ) -> None:
        current = now()
        connection.last_failure_at = current
        connection.last_error = error.message[:300]
        connection.last_error_code = error.code[:64]
        connection.consecutive_failures += 1
        if kind == "test":
            connection.last_health_check_at = current
        if Circuit.counts(error):
            breaker.record_failure(current)
            circuit_store.store(breaker, connection)
        if error.kind == "rate_limited":
            wait = error.retry_after if error.retry_after is not None else 60
            connection.rate_limited_until = current + timedelta(seconds=min(wait, 3600))
        if error.kind in ("auth", "configuration"):
            connection.health = "failing"
            if connection.status != "draft" or kind == "test":
                transition(connection, "error")
        elif error.kind == "permanent" and kind == "test":
            connection.health = "failing"
            transition(connection, "error")
        else:
            failing = connection.consecutive_failures >= self.settings.circuit_failure_threshold
            connection.health = "failing" if failing else "degraded"
            if connection.status == "connected":
                transition(connection, "degraded")
            elif connection.status in ("draft", "connecting") and kind == "test":
                transition(connection, "error")
        await self.activity(connection, kind, "failure", error.message)

    async def activity(
        self,
        connection: IntegrationConnection,
        kind: str,
        outcome: str,
        message: str,
        latency: int | None = None,
    ) -> None:
        self.session.add(
            IntegrationActivity(
                tenant_id=connection.tenant_id,
                environment_id=connection.environment_id,
                connection_id=connection.id,
                kind=kind[:32],
                outcome=outcome,
                message=message[:300],
                latency_ms=latency,
            )
        )
        await self.session.flush()
