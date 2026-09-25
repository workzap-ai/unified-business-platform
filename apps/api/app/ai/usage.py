"""Usage metering (one ai_usage_events row per provider attempt) and daily budgets.

Rows never contain prompts, outputs, media or keys: only provider, model, alias,
purpose, outcome, latency, token counts and estimated cost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.errors import UsageLimitExceeded
from app.ai.models import AIUsageEvent

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.shared.scope import WorkspaceScope

logger = logging.getLogger("platform.ai")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    tenant_id: UUID
    environment_id: UUID
    provider: str
    model: str
    alias: str
    purpose: str
    status: str  # success | failed
    fallback: bool
    attempt: int
    error_kind: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost: Decimal | None
    conversation_id: UUID | None = None
    run_id: UUID | None = None

    def to_row(self) -> AIUsageEvent:
        return AIUsageEvent(
            tenant_id=self.tenant_id,
            environment_id=self.environment_id,
            provider=self.provider[:20],
            model=self.model[:120],
            alias=self.alias[:20],
            purpose=self.purpose[:20],
            status=self.status,
            fallback=self.fallback,
            attempt=self.attempt,
            error_kind=self.error_kind[:32] if self.error_kind else None,
            latency_ms=self.latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            estimated_cost=self.estimated_cost,
            conversation_id=self.conversation_id,
            run_id=self.run_id,
        )


@dataclass(frozen=True, slots=True)
class UsageTotals:
    tokens: int
    cost: Decimal


class UsageStore(Protocol):
    async def record(self, records: list[UsageRecord]) -> None: ...

    async def totals_since(self, tenant_id: UUID, since: datetime) -> UsageTotals: ...


class NullUsageStore:
    """Used by the legacy facade whose caller persists rows itself."""

    async def record(self, records: list[UsageRecord]) -> None:
        return None

    async def totals_since(self, tenant_id: UUID, since: datetime) -> UsageTotals:
        return UsageTotals(0, Decimal("0"))


class InMemoryUsageStore:
    """Tests and local tooling."""

    def __init__(self) -> None:
        self.records: list[tuple[datetime, UsageRecord]] = []

    async def record(self, records: list[UsageRecord]) -> None:
        now = datetime.now(UTC)
        self.records.extend((now, r) for r in records)

    async def totals_since(self, tenant_id: UUID, since: datetime) -> UsageTotals:
        rows = [r for at, r in self.records if r.tenant_id == tenant_id and at >= since]
        return UsageTotals(
            sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in rows),
            sum((r.estimated_cost or Decimal("0") for r in rows), Decimal("0")),
        )


class SqlUsageStore:
    """Writes each call's attempts in its own short transaction.

    LLM calls happen outside business transactions, so usage survives a caller
    rollback and failed attempts are still metered.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def record(self, records: list[UsageRecord]) -> None:
        if not records:
            return
        async with self.sessions() as session:
            session.add_all([r.to_row() for r in records])
            await session.commit()

    async def totals_since(self, tenant_id: UUID, since: datetime) -> UsageTotals:
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                func.coalesce(AIUsageEvent.input_tokens, 0)
                                + func.coalesce(AIUsageEvent.output_tokens, 0)
                            ),
                            0,
                        ),
                        func.coalesce(func.sum(AIUsageEvent.estimated_cost), 0),
                    ).where(AIUsageEvent.tenant_id == tenant_id, AIUsageEvent.created_at >= since)
                )
            ).one()
        return UsageTotals(int(row[0]), Decimal(row[1]))


def start_of_utc_day(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return datetime.combine(now.date(), time.min, tzinfo=UTC)


class BudgetGuard:
    """Pre-call check of the tenant's UTC-day token/cost budget.

    A single in-flight call can overshoot by its own usage; the next call is refused.
    """

    def __init__(
        self, token_limit: int | None, cost_limit: Decimal | None, store: UsageStore
    ) -> None:
        self.token_limit, self.cost_limit, self.store = token_limit, cost_limit, store

    @classmethod
    def from_settings(cls, settings: Settings, store: UsageStore) -> BudgetGuard:
        return cls(settings.ai_tenant_daily_token_limit, settings.ai_tenant_daily_cost_limit, store)

    @property
    def enabled(self) -> bool:
        return self.token_limit is not None or self.cost_limit is not None

    async def check(self, tenant_id: UUID, now: datetime | None = None) -> None:
        if not self.enabled:
            return
        totals = await self.store.totals_since(tenant_id, start_of_utc_day(now))
        if self.token_limit is not None and totals.tokens >= self.token_limit:
            raise UsageLimitExceeded("token", str(totals.tokens), str(self.token_limit))
        if self.cost_limit is not None and totals.cost >= self.cost_limit:
            raise UsageLimitExceeded("cost", str(totals.cost), str(self.cost_limit))

    def next_reset(self, now: datetime | None = None) -> datetime:
        return start_of_utc_day(now) + timedelta(days=1)


class UsageTracker:
    """Turns attempts into UsageRecords from trusted scope and persists them."""

    def __init__(self, store: UsageStore) -> None:
        self.store = store

    def build(
        self,
        scope: WorkspaceScope,
        *,
        provider: str,
        model: str,
        alias: str,
        purpose: str,
        status: str,
        fallback: bool,
        attempt: int,
        error_kind: str | None,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        estimated_cost: Decimal | None,
        conversation_id: UUID | None,
        run_id: UUID | None,
    ) -> UsageRecord:
        return UsageRecord(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            provider=provider,
            model=model,
            alias=alias,
            purpose=purpose,
            status=status,
            fallback=fallback,
            attempt=attempt,
            error_kind=error_kind,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            conversation_id=conversation_id,
            run_id=run_id,
        )

    async def record(self, records: list[UsageRecord]) -> None:
        try:
            await self.store.record(records)
        except Exception:  # metering must never turn a good answer into a failure
            logger.warning(
                "ai.usage.record_failed", extra={"ai_records": len(records)}, exc_info=False
            )
