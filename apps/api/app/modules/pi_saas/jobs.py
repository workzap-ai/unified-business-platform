"""Background jobs for the Pi SaaS: provider and billing events, lifecycle sweeps.

Processing is idempotent (events are claimed with a row lock and applied once), bounded
(five attempts, then ``failed`` for operator replay) and never holds a transaction across
provider HTTP calls longer than one event.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi_saas import billing, connections
from app.modules.pi_saas.models import PiBillingEvent, PiProviderEvent
from app.modules.pi_saas.operator import expire_grants

logger = logging.getLogger("platform")
MAX_ATTEMPTS = 5


async def process_pi_provider_event(ctx: dict[str, Any], event_id: str) -> None:
    enqueue: list[str] = []
    async with ctx["sessions"]() as session:
        row = await session.scalar(
            select(PiProviderEvent)
            .where(PiProviderEvent.id == UUID(event_id))
            .with_for_update(skip_locked=True)
        )
        if row is None or row.status not in {"received"}:
            return
        row.attempts += 1
        try:
            async with session.begin_nested():
                enqueue = await connections.process_event(
                    session, ctx["settings"], ctx["http"], row
                )
        except Exception as exc:  # noqa: BLE001 - recorded, retried, then surfaced
            code = getattr(exc, "code", type(exc).__name__)
            row.error_code = str(code)[:64]
            row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "received"
            logger.warning("pi_provider_event_failed")
        await session.commit()
    for pi_event in enqueue:
        await _enqueue(ctx, "process_pi_event", pi_event, f"pi:{pi_event}")


async def process_pi_billing_event(ctx: dict[str, Any], event_id: str) -> None:
    async with ctx["sessions"]() as session:
        row = await session.scalar(
            select(PiBillingEvent)
            .where(PiBillingEvent.id == UUID(event_id))
            .with_for_update(skip_locked=True)
        )
        if row is None or row.status != "received":
            return
        row.attempts += 1
        try:
            async with session.begin_nested():
                await billing.apply_event(session, ctx["settings"], row, ctx["http"])
        except Exception as exc:  # noqa: BLE001
            row.error_code = str(getattr(exc, "code", type(exc).__name__))[:64]
            row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "received"
            logger.warning("pi_billing_event_failed")
        await session.commit()


async def sweep_pi_saas(ctx: dict[str, Any]) -> None:
    """Retry stalled events, expire support grants and record lapsed grace periods."""
    stale = datetime.now(UTC) - timedelta(minutes=2)
    async with ctx["sessions"]() as session:
        providers = list(
            await session.scalars(
                select(PiProviderEvent.id)
                .where(PiProviderEvent.status == "received", PiProviderEvent.updated_at < stale)
                .limit(100)
            )
        )
        bills = list(
            await session.scalars(
                select(PiBillingEvent.id)
                .where(PiBillingEvent.status == "received", PiBillingEvent.updated_at < stale)
                .limit(100)
            )
        )
        await expire_grants(session)
        from app.modules.pi_saas.customer_payments import expire_requests

        await expire_requests(session)
        await billing.sweep_lifecycle(session)
        await session.commit()
    # Business journey: notifications, held numbers connecting once allowed, expiring holds.
    async with ctx["sessions"]() as session:
        from app.modules.pi_saas import lifecycle_notify

        try:
            await lifecycle_notify.sweep(session, ctx["settings"], ctx["http"])
            await session.commit()
        except Exception:  # noqa: BLE001 - retried on the next sweep
            await session.rollback()
            logger.warning("pi_lifecycle_sweep_failed")
    # A number can look connected while its webhook never registered with Kapso (missing
    # public URL/secret at setup time, or a transient provider failure); retry until it
    # takes, so messages start arriving without anyone clicking "Check health".
    async with ctx["sessions"]() as session:
        try:
            healed = await connections.retry_unregistered_webhooks(
                session, ctx["settings"], ctx["http"]
            )
            await session.commit()
            if healed:
                logger.info("pi_webhook_self_healed", extra={"count": healed})
        except Exception:  # noqa: BLE001 - retried on the next sweep
            await session.rollback()
            logger.warning("pi_webhook_retry_failed")
    for event_id in providers:
        await _enqueue(ctx, "process_pi_provider_event", str(event_id), f"pi-provider:{event_id}")
    for event_id in bills:
        await _enqueue(ctx, "process_pi_billing_event", str(event_id), f"pi-billing:{event_id}")


async def _enqueue(ctx: dict[str, Any], name: str, arg: str, job_id: str) -> None:
    if ctx.get("redis"):
        await ctx["redis"].enqueue_job(name, arg, _job_id=job_id)
    elif ctx.get("queue"):
        await ctx["queue"].enqueue(name, arg, job_id=job_id)


JOBS: dict[str, Callable[..., Awaitable[Any]]] = {
    "process_pi_provider_event": process_pi_provider_event,
    "process_pi_billing_event": process_pi_billing_event,
    "sweep_pi_saas": sweep_pi_saas,
}
