"""ARQ job functions for the integration platform (registered in app.worker).

All jobs are idempotent: they lock their row with SKIP LOCKED, check the status and
no-op when there is nothing to do, so duplicate enqueues and ARQ re-runs are safe.
`integrations_sweep` runs every minute (cron) and re-drives anything whose enqueue was
lost, whose backoff elapsed or whose worker died.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.integrations import outbox, sync, webhooks
from app.integrations.http import OutboundClient
from app.modules.integrations.models import OAuthState, SyncJob

logger = logging.getLogger("platform")


def _http(ctx: dict[str, Any]) -> OutboundClient:
    return OutboundClient(ctx["settings"], ctx["http"], resolver=ctx.get("integration_resolver"))


async def _enqueue(ctx: dict[str, Any], name: str, arg: str, job_id: str) -> None:
    queue = ctx.get("queue")
    if queue is not None:
        await queue.enqueue(name, arg, job_id=job_id)
        return
    pool = ctx.get("redis")  # ARQ worker context carries its ArqRedis pool
    if pool is not None and hasattr(pool, "enqueue_job"):
        try:
            await pool.enqueue_job(name, arg, _job_id=job_id)
        except Exception:
            logger.warning("integration_enqueue_failed")


async def process_inbound_event(ctx: dict[str, Any], event_id: str) -> str:
    async with ctx["sessions"]() as session:
        return await webhooks.process(session, ctx["settings"], UUID(event_id))


async def dispatch_outbox(ctx: dict[str, Any]) -> int:
    async with ctx["sessions"]() as session:
        ids = await outbox.dispatch_pending(session, ctx["settings"])
        await session.commit()
    for delivery_id in ids:
        await _enqueue(
            ctx, "deliver_webhook", str(delivery_id), outbox.delivery_job_id(delivery_id, 0)
        )
    return len(ids)


async def deliver_webhook(ctx: dict[str, Any], delivery_id: str) -> str:
    async with ctx["sessions"]() as session:
        return await outbox.deliver(session, ctx["settings"], _http(ctx), UUID(delivery_id))


async def run_sync_job(ctx: dict[str, Any], job_id: str) -> str:
    async with ctx["sessions"]() as session:
        result = await sync.run_job(
            session, ctx["settings"], _http(ctx), UUID(job_id), redis=ctx.get("redis")
        )
    if result == "continued":
        await _enqueue(
            ctx, "run_sync_job", job_id, f"intg:sync:{job_id}:cont:{datetime.now(UTC).timestamp()}"
        )
    return result


async def integrations_sweep(ctx: dict[str, Any]) -> dict[str, int]:
    settings = ctx["settings"]
    await dispatch_outbox(ctx)
    current = datetime.now(UTC)
    async with ctx["sessions"]() as session:
        deliveries = await outbox.due_deliveries(session)
        events = await webhooks.due_events(session)
        # Failed sync jobs are retried automatically after 5 minutes (bounded attempts).
        retry_jobs = list(
            await session.scalars(
                select(SyncJob)
                .where(
                    SyncJob.status == "failed",
                    SyncJob.attempt_count < sync.MAX_JOB_ATTEMPTS,
                    SyncJob.updated_at < current - timedelta(minutes=5),
                )
                .limit(50)
                .with_for_update(skip_locked=True)
            )
        )
        for job in retry_jobs:
            job.status = "pending"
        pending_jobs = list(
            await session.scalars(
                select(SyncJob.id)
                .where(
                    SyncJob.status == "pending", SyncJob.updated_at < current - timedelta(minutes=1)
                )
                .limit(50)
            )
        )
        purged = await webhooks.purge_payloads(session, settings)
        await session.execute(
            delete(OAuthState).where(OAuthState.expires_at < current - timedelta(days=1))
        )
        await session.commit()
    for delivery_id, attempts in deliveries:
        await _enqueue(
            ctx, "deliver_webhook", str(delivery_id), outbox.delivery_job_id(delivery_id, attempts)
        )
    for event_id, attempts in events:
        await _enqueue(
            ctx, "process_inbound_event", str(event_id), webhooks.inbound_job_id(event_id, attempts)
        )
    for job_id in {*(j.id for j in retry_jobs), *pending_jobs}:
        await _enqueue(ctx, "run_sync_job", str(job_id), f"intg:sync:{job_id}:sweep")
    return {"deliveries": len(deliveries), "events": len(events), "purged": purged}


JOBS: dict[str, Callable[..., Awaitable[Any]]] = {
    "process_inbound_event": process_inbound_event,
    "dispatch_outbox": dispatch_outbox,
    "deliver_webhook": deliver_webhook,
    "run_sync_job": run_sync_job,
    "integrations_sweep": integrations_sweep,
}
