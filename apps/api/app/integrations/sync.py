"""Sync engine: jobs, attempts, cursors, conflicts and external references.

State machine: pending -> running -> succeeded | failed | paused | cancelled | dead_letter;
failed/dead_letter -> pending (retry); paused -> pending (resume).

A job runs in the worker (`run_job`), one page at a time. After every page it commits
stats and the page cursor (checkpoint), then re-reads its own status so a pause/cancel
from the API takes effect between pages; a resumed or retried job continues from the
checkpoint. Only definitions whose adapter implements a sync source can create jobs
(IntegrationRegistry enforces this at registration).

Source of truth is declared per entity by the definition. Currently implemented:
Stripe customers (pull, platform is source of truth): each provider customer gets an
`integration_external_refs` row; new refs are linked to an existing CRM customer when
exactly one has the same email (read-only lookup), ambiguous matches become
`integration_sync_conflicts`, and CRM data is never written. Loop prevention: every ref
stores the fingerprint of the last write and its origin; a record whose fingerprint is
unchanged is skipped (incremental mode), and writes originating from the platform are
never re-imported as provider changes.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.catalog import REGISTRY
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.integrations.registry import CustomerSyncSource, ExternalCustomer
from app.integrations.runtime import ConnectionRuntime
from app.modules.customers.models import Customer
from app.modules.integrations.models import (
    ExternalReference,
    IntegrationConnection,
    SyncAttempt,
    SyncConflict,
    SyncCursor,
    SyncJob,
)
from app.shared.state_machine import StateMachine

SYNC_STATES = StateMachine(
    "sync job",
    {
        "pending": frozenset({"running", "cancelled", "paused"}),
        "running": frozenset(
            {"succeeded", "failed", "paused", "cancelled", "dead_letter", "pending"}
        ),
        "failed": frozenset({"pending", "dead_letter", "cancelled"}),
        "paused": frozenset({"pending", "cancelled"}),
        "dead_letter": frozenset({"pending", "cancelled"}),
        "succeeded": frozenset(),
        "cancelled": frozenset(),
    },
)
EMPTY_STATS = {
    "discovered": 0,
    "created": 0,
    "updated": 0,
    "skipped": 0,
    "failed": 0,
    "conflicts": 0,
}
PAGE_SIZE = 100
MAX_PAGES_PER_RUN = 50
MAX_JOB_ATTEMPTS = 3


def now() -> datetime:
    return datetime.now(UTC)


def sync_job_id(job_id: UUID, attempt: int) -> str:
    return f"intg:sync:{job_id}:{attempt}"


async def _match_customer(
    session: AsyncSession, connection: IntegrationConnection, email: str | None
) -> tuple[UUID | None, str]:
    if not email:
        return None, "none"
    ids = list(
        await session.scalars(
            select(Customer.id)
            .where(
                Customer.tenant_id == connection.tenant_id,
                Customer.environment_id == connection.environment_id,
                func.lower(Customer.email) == email.lower(),
            )
            .limit(2)
        )
    )
    if len(ids) == 1:
        return ids[0], "email"
    return None, "ambiguous" if ids else "none"


async def apply_customer(
    session: AsyncSession,
    job: SyncJob,
    connection: IntegrationConnection,
    item: ExternalCustomer,
    stats: dict[str, int],
) -> None:
    stats["discovered"] += 1
    ref = await session.scalar(
        select(ExternalReference).where(
            ExternalReference.tenant_id == connection.tenant_id,
            ExternalReference.environment_id == connection.environment_id,
            ExternalReference.connection_id == connection.id,
            ExternalReference.entity == "customers",
            ExternalReference.external_id == item.external_id,
        )
    )
    if ref is not None:
        if ref.fingerprint == item.fingerprint and job.mode == "incremental":
            stats["skipped"] += 1
            return
        if ref.last_write_origin == "platform" and ref.fingerprint == item.fingerprint:
            stats["skipped"] += 1  # our own write echoed back: never re-import
            return
        ref.fingerprint, ref.last_write_origin, ref.last_synced_at = (
            item.fingerprint,
            "provider",
            now(),
        )
        if ref.platform_entity_id is None:
            customer_id, _match = await _match_customer(session, connection, item.email)
            ref.platform_entity_id = customer_id
        stats["updated"] += 1
        return
    customer_id, match = await _match_customer(session, connection, item.email)
    if match == "ambiguous":
        stats["conflicts"] += 1
        session.add(
            SyncConflict(
                tenant_id=connection.tenant_id,
                environment_id=connection.environment_id,
                job_id=job.id,
                connection_id=connection.id,
                entity="customers",
                external_id=item.external_id,
                reason="Several CRM customers share this email address",
                details={"match": "email"},
            )
        )
    await session.execute(
        insert(ExternalReference)
        .values(
            tenant_id=connection.tenant_id,
            environment_id=connection.environment_id,
            connection_id=connection.id,
            entity="customers",
            external_id=item.external_id,
            platform_entity_id=customer_id,
            fingerprint=item.fingerprint,
            last_write_origin="provider",
            last_synced_at=now(),
        )
        .on_conflict_do_nothing(constraint="uq_integration_external_refs_external")
    )
    stats["created"] += 1


async def _reload(session: AsyncSession, job_id: UUID) -> SyncJob | None:
    job: SyncJob | None = await session.scalar(
        select(SyncJob).where(SyncJob.id == job_id).execution_options(populate_existing=True)
    )
    return job


async def run_job(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    job_id: UUID,
    *,
    redis: Any = None,
) -> str:
    job = await session.scalar(
        select(SyncJob)
        .where(SyncJob.id == job_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if job is None or job.status != "pending":
        return "skipped"
    connection = await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.tenant_id == job.tenant_id,
            IntegrationConnection.environment_id == job.environment_id,
            IntegrationConnection.id == job.connection_id,
        )
    )
    definition = REGISTRY.definition(job.integration_key)
    provider = REGISTRY.provider(job.integration_key)
    if (
        connection is None
        or definition is None
        or not isinstance(provider, CustomerSyncSource)
        or definition.sync_policy(job.entity) is None
        or connection.status not in ("connected", "degraded")
    ):
        SYNC_STATES.ensure(job.status, "cancelled")
        job.status, job.finished_at = "cancelled", now()
        job.last_error = "The connection is not active or no longer supports this sync"
        await session.commit()
        return job.status
    SYNC_STATES.ensure(job.status, "running")
    job.status, job.attempt_count = "running", job.attempt_count + 1
    job.started_at = job.started_at or now()
    stats = {**EMPTY_STATS, **(job.stats or {})}
    attempt = SyncAttempt(
        tenant_id=job.tenant_id,
        environment_id=job.environment_id,
        job_id=job.id,
        attempt=job.attempt_count,
        status="running",
        started_at=now(),
    )
    session.add(attempt)
    await session.commit()

    runtime = ConnectionRuntime(session, settings, http, redis=redis)
    cursor = job.cursor
    pages = 0
    try:
        while True:

            async def fetch(
                ctx: Any, c: str | None = cursor, source: CustomerSyncSource = provider
            ) -> Any:
                return await source.list_customers(ctx, c, PAGE_SIZE)

            page, _latency = await runtime.call(connection, fetch, kind="sync")
            for item in page.items:
                await apply_customer(session, job, connection, item, stats)
            cursor = page.next_cursor
            job.cursor, job.stats = cursor, dict(stats)
            attempt.stats = dict(stats)
            pages += 1
            await session.commit()  # checkpoint
            current = await _reload(session, job.id)
            if current is None or current.status != "running":
                attempt.status, attempt.finished_at = (
                    current.status if current else "cancelled",
                    now(),
                )
                await session.commit()
                return current.status if current else "cancelled"
            job = current
            if cursor is None:
                break
            if pages >= MAX_PAGES_PER_RUN:
                job.status = "pending"  # continue in a fresh job run
                attempt.status, attempt.finished_at = "succeeded", now()
                await session.commit()
                return "continued"
    except IntegrationError as error:
        job = await _reload(session, job_id) or job
        job.last_error, job.error_code = error.message[:300], error.code[:64]
        job.stats = dict(stats)
        target = (
            "dead_letter"
            if (not error.retryable or job.attempt_count >= MAX_JOB_ATTEMPTS)
            else "failed"
        )
        if job.status == "running":
            job.status = target
            job.finished_at = now()
        attempt.status, attempt.finished_at, attempt.error_code = target, now(), error.code[:64]
        await session.commit()
        return job.status
    job.status, job.finished_at, job.last_error, job.error_code = "succeeded", now(), None, None
    attempt.status, attempt.finished_at = "succeeded", now()
    await session.execute(
        insert(SyncCursor)
        .values(
            tenant_id=job.tenant_id,
            environment_id=job.environment_id,
            connection_id=job.connection_id,
            entity=job.entity,
            cursor=None,
            last_success_at=now(),
        )
        .on_conflict_do_update(
            constraint="uq_integration_sync_cursors_entity",
            set_={"last_success_at": now(), "cursor": None},
        )
    )
    await session.commit()
    return job.status
