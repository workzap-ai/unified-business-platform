"""Transactional outbox and outbound webhook delivery.

Business services call `emit()` inside their own transaction; the event row commits or
rolls back with the business change. A worker (`dispatch_outbox`, also run by the
periodic sweep) fans events out to matching webhook subscriptions of the *same tenant
environment* as `integration_deliveries` rows (unique per subscription+event), and
`deliver_webhook` sends each one signed (see app.integrations.signing) with bounded
exponential backoff; after `delivery_max_attempts` a delivery moves to `dead_letter`
and can be retried manually.

Usage from a business service (inside the caller's transaction, before commit):

    from app.integrations.outbox import EntityRef, emit

    await emit(
        session, scope, "order.confirmed",
        {"order_id": str(order.id), "number": order.number, "total": str(order.total)},
        EntityRef("order", order.id),
    )

Payloads must be JSON-serializable, ≤ 64 KiB, contain no secrets, and carry money as
decimal strings.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.crypto import CredentialManager
from app.integrations.errors import IntegrationError
from app.integrations.events import is_known
from app.integrations.http import CallContext, OutboundClient
from app.integrations.retry import backoff_seconds
from app.integrations.signing import SIGNATURE_HEADER, signature_header
from app.modules.integrations.models import Delivery, OutboxEvent, WebhookSubscription
from app.shared.scope import WorkspaceScope

MAX_PAYLOAD_BYTES = 64 * 1024
STALE_RUNNING = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class EntityRef:
    entity_type: str
    entity_id: UUID


def now() -> datetime:
    return datetime.now(UTC)


def fingerprint(event_type: str, payload: dict[str, Any], entity: EntityRef | None) -> str:
    material = json.dumps(
        [
            event_type,
            payload,
            entity.entity_type if entity else None,
            str(entity.entity_id) if entity else None,
        ],
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


async def emit(
    session: AsyncSession,
    scope: WorkspaceScope,
    event_type: str,
    payload: dict[str, Any],
    entity_ref: EntityRef | None = None,
    *,
    origin: str | None = None,
    correlation_id: str | None = None,
) -> OutboxEvent:
    """Write an outbox event in the caller's transaction (does not commit)."""
    if not is_known(event_type):
        raise ValueError(f"Unknown event type {event_type}")
    body = json.dumps(payload, default=str, separators=(",", ":"))
    if len(body.encode()) > MAX_PAYLOAD_BYTES:
        raise ValueError("Outbox payload is too large")
    event = OutboxEvent(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        event_type=event_type,
        payload=json.loads(body),
        entity_type=entity_ref.entity_type[:60] if entity_ref else None,
        entity_id=entity_ref.entity_id if entity_ref else None,
        status="pending",
        available_at=now(),
        created_at=now(),
        correlation_id=(correlation_id or scope.request_id or None),
        origin=origin[:80] if origin else None,
        fingerprint=fingerprint(event_type, payload, entity_ref),
    )
    session.add(event)
    await session.flush()
    return event


async def dispatch_pending(session: AsyncSession, settings: Settings) -> list[UUID]:
    """Fan pending outbox events out to deliveries. Returns delivery ids to send."""
    events = list(
        await session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending", OutboxEvent.available_at <= now())
            .order_by(OutboxEvent.available_at)
            .limit(settings.outbox_batch_size)
            .with_for_update(skip_locked=True)
        )
    )
    created: list[UUID] = []
    for event in events:
        from app.integrations.workflows import fanout

        await fanout(session, event)
        subscriptions = await session.scalars(
            select(WebhookSubscription).where(
                WebhookSubscription.tenant_id == event.tenant_id,
                WebhookSubscription.environment_id == event.environment_id,
                WebhookSubscription.enabled.is_(True),
                WebhookSubscription.deleted_at.is_(None),
                WebhookSubscription.event_types.contains([event.event_type]),
            )
        )
        for subscription in subscriptions:
            if event.origin == f"webhook:{subscription.id}":
                continue  # loop prevention: never echo an event back to its source
            delivery_id = await session.scalar(
                insert(Delivery)
                .values(
                    tenant_id=event.tenant_id,
                    environment_id=event.environment_id,
                    subscription_id=subscription.id,
                    outbox_event_id=event.id,
                    event_type=event.event_type,
                    status="pending",
                    max_attempts=settings.delivery_max_attempts,
                    idempotency_key=f"{event.id}:{subscription.id}",
                )
                .on_conflict_do_nothing(constraint="uq_integration_deliveries_event")
                .returning(Delivery.id)
            )
            if delivery_id is not None:
                created.append(delivery_id)
        event.status = "dispatched"
        event.dispatched_at = now()
        event.attempts += 1
    await session.flush()
    return created


def delivery_body(event: OutboxEvent) -> bytes:
    return json.dumps(
        {
            "id": str(event.id),
            "type": event.event_type,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "data": event.payload,
        },
        separators=(",", ":"),
        default=str,
    ).encode()


async def deliver(
    session: AsyncSession, settings: Settings, http: OutboundClient, delivery_id: UUID
) -> str:
    """Attempt one delivery. Idempotent: non-due or finished deliveries are no-ops."""
    delivery = await session.scalar(
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if delivery is None or delivery.status not in ("pending", "failed"):
        return "skipped"
    if delivery.next_attempt_at and delivery.next_attempt_at > now():
        return "not_due"
    # Scope comes from the delivery row itself, never from payload data.
    subscription = await session.scalar(
        select(WebhookSubscription).where(
            WebhookSubscription.tenant_id == delivery.tenant_id,
            WebhookSubscription.environment_id == delivery.environment_id,
            WebhookSubscription.id == delivery.subscription_id,
        )
    )
    event = await session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == delivery.tenant_id,
            OutboxEvent.environment_id == delivery.environment_id,
            OutboxEvent.id == delivery.outbox_event_id,
        )
    )
    if subscription is None or event is None:
        return "skipped"
    if subscription.deleted_at is not None or not subscription.enabled:
        delivery.status, delivery.last_error = "cancelled", "Subscription disabled or removed"
        await session.flush()
        return delivery.status
    delivery.status = "running"
    delivery.attempt_count += 1
    await session.commit()  # claim the attempt before network I/O

    body = delivery_body(event)
    try:
        secret = CredentialManager(settings).decrypt(subscription.secret_encrypted)
        response = await http.request(
            "POST",
            subscription.url,
            content=body,
            headers={
                "content-type": "application/json",
                SIGNATURE_HEADER: signature_header(secret, body),
                "X-Platform-Event": delivery.event_type,
                "X-Platform-Delivery": str(delivery.id),
                "Idempotency-Key": delivery.idempotency_key,
            },
            max_bytes=16 * 1024,
            context=CallContext(correlation_id=event.correlation_id, idempotent=True),
        )
        delivery.response_status = response.status_code
        response.ensure_success()
    except IntegrationError as error:
        delivery.last_error = error.message[:300]
        permanent = error.code in (
            "URL_REJECTED",
            "CREDENTIALS_UNREADABLE",
            "ENCRYPTION_NOT_CONFIGURED",
        )
        if permanent or delivery.attempt_count >= delivery.max_attempts:
            delivery.status, delivery.next_attempt_at = "dead_letter", None
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = now() + timedelta(
                seconds=backoff_seconds(
                    delivery.attempt_count,
                    settings.delivery_backoff_base_seconds,
                    settings.delivery_backoff_max_seconds,
                    error.retry_after,
                )
            )
        subscription.failure_count += 1
        subscription.last_delivery_status = delivery.status
        subscription.last_delivery_at = now()
        await session.commit()
        return delivery.status
    except Exception as error:
        # Configuration problems (no encryption key) cannot heal by retrying.
        if getattr(error, "code", None) == "ENCRYPTION_NOT_CONFIGURED":
            delivery.status, delivery.next_attempt_at = "dead_letter", None
            delivery.last_error = "Credential storage is not configured on this server"
        else:
            delivery.status = (
                "failed" if delivery.attempt_count < delivery.max_attempts else "dead_letter"
            )
            delivery.last_error = "Delivery failed unexpectedly"
            delivery.next_attempt_at = (
                now() + timedelta(seconds=settings.delivery_backoff_base_seconds)
                if delivery.status == "failed"
                else None
            )
        await session.commit()
        return delivery.status
    delivery.status, delivery.delivered_at = "succeeded", now()
    delivery.last_error, delivery.next_attempt_at = None, None
    subscription.failure_count = 0
    subscription.last_delivery_status = "succeeded"
    subscription.last_delivery_at = now()
    await session.commit()
    return delivery.status


async def due_deliveries(session: AsyncSession, limit: int = 200) -> list[tuple[UUID, int]]:
    """Failed deliveries whose backoff elapsed, plus pending and stale running ones."""
    current = now()
    stale = await session.scalars(
        select(Delivery)
        .where(Delivery.status == "running", Delivery.updated_at < current - STALE_RUNNING)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    for row in stale:
        # A worker died mid-attempt: the attempt counts; schedule a retry now.
        row.status = "failed" if row.attempt_count < row.max_attempts else "dead_letter"
        row.next_attempt_at = current
    await session.flush()
    rows = await session.execute(
        select(Delivery.id, Delivery.attempt_count)
        .where(
            or_(
                Delivery.status == "pending",
                and_(Delivery.status == "failed", Delivery.next_attempt_at <= current),
            )
        )
        .order_by(Delivery.next_attempt_at.nulls_first())
        .limit(limit)
    )
    return [(r[0], int(r[1])) for r in rows]


def delivery_job_id(delivery_id: UUID, attempt_count: int) -> str:
    return f"intg:delivery:{delivery_id}:{attempt_count}"
