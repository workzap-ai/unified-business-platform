"""Inbound webhook pipeline.

POST /api/v1/webhooks/{integration_key}/{endpoint_token} (public; no session/CSRF):

1. The body is read with a hard size cap (settings.webhook_max_body_bytes).
2. The connection — and therefore tenant and environment — is identified only by the
   unguessable endpoint token (SHA-256 looked up), never by IDs inside the payload.
   Unknown/disabled/revoked tokens get the same generic 404.
3. The adapter verifies the signature (and timestamp window where the provider signs
   one); failures answer 401 and store nothing.
4. Events are normalized, then inserted idempotently: unique (connection_id,
   provider_event_id). Duplicates are no-ops (no new row, no new job).
5. Only a redacted, size-limited copy of the event data is stored, with the SHA-256 of
   the raw body; stored payloads are purged after webhook_payload_retention_days.
6. A processing job is enqueued after commit and the provider gets a fast 2xx.

Handlers are registered per (integration_key, event_type) with `register_handler`; they
receive a system WorkspaceScope for the connection's tenant environment and must be
idempotent (replay re-runs them). Events without a handler are marked `ignored` — they
remain visible and replayable once a handler exists.
"""

import hashlib
import json
import re
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.jobs import JobQueue
from app.integrations.catalog import REGISTRY
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.integrations.redaction import redact_data
from app.integrations.registry import WebhookReceiver
from app.integrations.retry import backoff_seconds
from app.modules.integrations.models import InboundEvent, IntegrationConnection
from app.shared.scope import WorkspaceScope

TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
KEY = re.compile(r"^[a-z0-9_]{2,60}$")
ACCEPTING = frozenset({"connected", "degraded", "connecting", "draft", "error", "expired"})
MAX_EVENT_ATTEMPTS = 5

Handler = Callable[[AsyncSession, WorkspaceScope, InboundEvent], Awaitable[str]]
_HANDLERS: dict[tuple[str, str], Handler] = {}


def register_handler(integration_key: str, event_type: str) -> Callable[[Handler], Handler]:
    """Register an idempotent handler; event_type may be '*' for a catch-all."""

    def decorator(handler: Handler) -> Handler:
        _HANDLERS[(integration_key, event_type)] = handler
        return handler

    return decorator


def handler_for(integration_key: str, event_type: str) -> Handler | None:
    return _HANDLERS.get((integration_key, event_type)) or _HANDLERS.get((integration_key, "*"))


def new_endpoint_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class WebhookNotFound(Exception):
    """Unknown integration/token: rendered as the generic 404."""


class WebhookUnauthorized(Exception):
    """Signature missing/invalid or outside the replay window."""


class WebhookInvalid(Exception):
    """Signed but unparseable payload."""


@dataclass(frozen=True, slots=True)
class ReceiveResult:
    accepted: int
    duplicates: int
    queued: list[UUID]


def now() -> datetime:
    return datetime.now(UTC)


async def _connection(
    session: AsyncSession, integration_key: str, endpoint_token: str
) -> tuple[IntegrationConnection, WebhookReceiver]:
    if not KEY.fullmatch(integration_key) or not TOKEN.fullmatch(endpoint_token):
        raise WebhookNotFound
    connection = await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.webhook_token_hash == token_hash(endpoint_token),
            IntegrationConnection.integration_key == integration_key,
        )
    )
    provider = REGISTRY.provider(integration_key)
    if (
        connection is None
        or connection.status not in ACCEPTING
        or not isinstance(provider, WebhookReceiver)
    ):
        raise WebhookNotFound
    return connection, provider


def stored_payload(data: Mapping[str, Any], limit: int) -> tuple[dict[str, Any] | None, bool]:
    redacted = redact_data(dict(data))
    encoded = json.dumps(redacted, default=str)
    if len(encoded.encode()) > limit:
        return {"truncated": True}, True
    return redacted, False


async def receive(
    session: AsyncSession,
    settings: Settings,
    integration_key: str,
    endpoint_token: str,
    headers: Mapping[str, str],
    body: bytes,
    *,
    received_at: datetime | None = None,
    correlation_id: str | None = None,
) -> ReceiveResult:
    connection, provider = await _connection(session, integration_key, endpoint_token)
    try:
        credentials = CredentialManager(settings).decrypt_json(connection.credentials_encrypted)
    except IntegrationError:
        raise WebhookUnauthorized from None
    except Exception:
        raise WebhookUnauthorized from None
    current = received_at or now()
    lowered = {k.lower(): v for k, v in headers.items()}
    if not provider.verify_webhook(lowered, body, credentials, settings, current.timestamp()):
        raise WebhookUnauthorized
    try:
        events = provider.parse_webhook(body)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise WebhookInvalid from None
    body_hash = hashlib.sha256(body).hexdigest()
    queued: list[UUID] = []
    duplicates = 0
    for event in events:
        payload, truncated = stored_payload(event.data, settings.webhook_stored_payload_max_bytes)
        event_id = await session.scalar(
            insert(InboundEvent)
            .values(
                tenant_id=connection.tenant_id,
                environment_id=connection.environment_id,
                connection_id=connection.id,
                integration_key=connection.integration_key,
                provider_event_id=event.provider_event_id[:200],
                event_type=event.event_type[:100],
                status="queued",
                signature_verified=True,
                payload_hash=body_hash,
                payload=payload,
                payload_truncated=truncated,
                received_at=current,
                correlation_id=(correlation_id or "")[:64] or None,
            )
            .on_conflict_do_nothing(constraint="uq_integration_inbound_events_provider_event")
            .returning(InboundEvent.id)
        )
        if event_id is None:
            duplicates += 1
        else:
            queued.append(event_id)
    await session.flush()
    return ReceiveResult(len(events), duplicates, queued)


async def handshake(
    session: AsyncSession,
    settings: Settings,
    integration_key: str,
    endpoint_token: str,
    params: Mapping[str, str],
) -> str | None:
    connection, provider = await _connection(session, integration_key, endpoint_token)
    try:
        credentials = CredentialManager(settings).decrypt_json(connection.credentials_encrypted)
    except Exception:
        return None
    return provider.handshake(params, credentials, settings)


def inbound_job_id(event_id: UUID, attempt: int) -> str:
    return f"intg:inbound:{event_id}:{attempt}"


async def enqueue_events(queue: JobQueue, ids: list[UUID]) -> None:
    for event_id in ids:
        await queue.enqueue(
            "process_inbound_event", str(event_id), job_id=inbound_job_id(event_id, 0)
        )


async def process(
    session: AsyncSession, settings: Settings, event_id: UUID, context: dict[str, Any] | None = None
) -> str:
    """Run the handler for one inbound event. Idempotent and safe to repeat."""
    event = await session.scalar(
        select(InboundEvent)
        .where(InboundEvent.id == event_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if event is None or event.status not in ("received", "queued", "failed"):
        return "skipped"
    if event.next_attempt_at and event.next_attempt_at > now():
        return "not_due"
    event.status = "processing"
    event.attempt_count += 1
    await session.flush()
    handler = handler_for(event.integration_key, event.event_type)
    pi_event_ids: list[str] = []
    if handler is None and context is not None:

        async def business_handler(
            db: AsyncSession, business_scope: WorkspaceScope, incoming: InboundEvent
        ) -> str:
            if incoming.integration_key == "stripe" and incoming.event_type in {
                "checkout.session.completed",
                "checkout.session.async_payment_succeeded",
            }:
                from app.integrations.business import settle_checkout
                from app.integrations.http import OutboundClient

                linked = await db.get(IntegrationConnection, incoming.connection_id)
                assert linked is not None
                return await settle_checkout(
                    db,
                    settings,
                    OutboundClient(
                        settings, context["http"], resolver=context.get("integration_resolver")
                    ),
                    linked,
                    str((incoming.payload or {}).get("object_id", "")),
                )
            if incoming.integration_key == "whatsapp_meta" and incoming.event_type in {
                "message.received",
                "message.status",
            }:
                from app.integrations.whatsapp_bridge import receive

                pi_id = await receive(db, incoming)
                if pi_id:
                    pi_event_ids.append(str(pi_id))
                    return "processed"
            return "ignored"

        handler = business_handler
    if handler is None:
        event.status, event.processed_at, event.error_code = "ignored", now(), None
        await session.commit()
        return event.status
    scope = WorkspaceScope.system(
        event.tenant_id,
        event.environment_id,
        frozenset(),
        f"integration:{event.integration_key}",
        request_id=event.correlation_id,
    )
    try:
        async with session.begin_nested():
            outcome = await handler(session, scope, event)
    except Exception as error:
        code = getattr(error, "code", None)
        event.error_code = str(code)[:64] if code else "HANDLER_FAILED"
        if event.attempt_count >= MAX_EVENT_ATTEMPTS:
            event.status, event.next_attempt_at = "dead_letter", None
        else:
            event.status = "failed"
            event.next_attempt_at = now() + timedelta(
                seconds=backoff_seconds(event.attempt_count, 30, 3600)
            )
        await session.commit()
        return event.status
    event.status = outcome if outcome in ("processed", "ignored") else "processed"
    event.processed_at, event.error_code, event.next_attempt_at = now(), None, None
    await session.commit()
    if context is not None:
        from app.integrations.jobs import _enqueue

        for pi_id in pi_event_ids:
            await _enqueue(context, "process_pi_event", pi_id, f"pi:{pi_id}")
    return event.status


async def due_events(session: AsyncSession, limit: int = 200) -> list[tuple[UUID, int]]:
    current = now()
    rows = await session.execute(
        select(InboundEvent.id, InboundEvent.attempt_count)
        .where(
            ((InboundEvent.status == "failed") & (InboundEvent.next_attempt_at <= current))
            | (
                InboundEvent.status.in_(("received", "queued"))
                & (InboundEvent.received_at < current - timedelta(minutes=2))
            )
        )
        .limit(limit)
    )
    stale = current - timedelta(minutes=10)
    await session.execute(
        update(InboundEvent)
        .where(InboundEvent.status == "processing", InboundEvent.updated_at < stale)
        .values(status="failed", next_attempt_at=current, error_code="WORKER_INTERRUPTED")
    )
    return [(r[0], int(r[1])) for r in rows]


async def purge_payloads(session: AsyncSession, settings: Settings) -> int:
    cutoff = now() - timedelta(days=settings.webhook_payload_retention_days)
    result = await session.execute(
        update(InboundEvent)
        .where(InboundEvent.received_at < cutoff, InboundEvent.payload.is_not(None))
        .values(payload=None)
    )
    return int(getattr(result, "rowcount", 0) or 0)
