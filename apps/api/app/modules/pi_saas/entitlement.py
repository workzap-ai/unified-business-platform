"""Entitlement and metering for Pi businesses.

A tenant without a Pi business account is an Owner OS workspace using the installed PI
product; this module leaves it unaffected. For Pi businesses, automation and outbound
sending require an entitled subscription and an active (not paused) account. Inbound
messages are always stored so no customer message is lost while a plan is inactive.

Usage is metered per environment and UTC month. Only production usage counts against
plan allowances; test-environment usage is recorded separately.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiPlan,
    PiSubscription,
    PiUsageCounter,
)

# Metric -> plan allowance key.
ALLOWANCE_FOR = {
    "messages_out": "messages",
    "ai_tokens": "ai_tokens",
    "media_items": "media_items",
}


def month(at: datetime | None = None) -> date:
    at = at or datetime.now(UTC)
    return date(at.year, at.month, 1)


@dataclass(frozen=True)
class Entitlement:
    """What a business may do right now, with a customer-safe reason when it may not."""

    managed: bool  # False for Owner OS workspaces (no Pi business account)
    status: str
    automation: bool
    sending: bool
    reason: str | None
    plan_key: str | None = None
    allowances: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Decimal] = field(default_factory=dict)
    is_production: bool = True


UNMANAGED = Entitlement(
    managed=False, status="unmanaged", automation=True, sending=True, reason=None
)


def subscription_active(subscription: PiSubscription | None, now: datetime) -> tuple[bool, str]:
    if subscription is None:
        return False, "NO_SUBSCRIPTION"
    if subscription.status == "trialing":
        if subscription.trial_ends_at is not None and subscription.trial_ends_at <= now:
            return False, "TRIAL_ENDED"
        return True, "TRIALING"
    if subscription.status == "active":
        if (
            subscription.cancel_at_period_end
            and subscription.current_period_end
            and subscription.current_period_end <= now
        ):
            return False, "SUBSCRIPTION_CANCELED"
        if subscription.current_period_end is not None and subscription.current_period_end <= now:
            # Awaiting the renewal event; the grace period covers delayed webhooks.
            if subscription.grace_ends_at is None or subscription.grace_ends_at <= now:
                return False, "RENEWAL_PENDING"
        return True, "ACTIVE"
    if subscription.status == "past_due":
        if subscription.grace_ends_at is not None and subscription.grace_ends_at > now:
            return True, "PAST_DUE_GRACE"
        return False, "PAYMENT_REQUIRED"
    if subscription.status == "canceled":
        return False, "SUBSCRIPTION_CANCELED"
    return False, "SUBSCRIPTION_SUSPENDED"


async def usage_for(
    session: AsyncSession, tenant_id: UUID, environment_id: UUID, period: date | None = None
) -> dict[str, Decimal]:
    rows = await session.execute(
        select(PiUsageCounter.metric, PiUsageCounter.quantity).where(
            PiUsageCounter.tenant_id == tenant_id,
            PiUsageCounter.environment_id == environment_id,
            PiUsageCounter.period == (period or month()),
        )
    )
    return {metric: Decimal(quantity) for metric, quantity in rows}


async def entitlement(
    session: AsyncSession, tenant_id: UUID, environment_id: UUID | None = None
) -> Entitlement:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is None:
        return UNMANAGED
    subscription = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant_id)
    )
    plan = (
        await session.scalar(select(PiPlan).where(PiPlan.key == subscription.plan_key))
        if subscription
        else None
    )
    now = datetime.now(UTC)
    ok, status = subscription_active(subscription, now)
    environment_id = environment_id or account.production_environment_id
    is_production = environment_id == account.production_environment_id
    usage = await usage_for(session, tenant_id, environment_id)
    allowances = dict(plan.allowances) if plan else {}
    reason: str | None = None if ok else status
    automation = sending = ok
    if account.status != "active":
        automation = sending = False
        reason = "ACCOUNT_SUSPENDED" if account.status == "suspended" else "ACCOUNT_CLOSED"
    elif account.setup_state == "paused":
        automation = False
        reason = reason or "PI_PAUSED"
    if automation and is_production:
        for metric, key in ALLOWANCE_FOR.items():
            limit = allowances.get(key)
            if limit is not None and usage.get(metric, Decimal(0)) >= Decimal(str(limit)):
                automation = False
                reason = "USAGE_LIMIT_REACHED"
                break
        if (
            automation
            and subscription is not None
            and subscription.spend_limit is not None
            and usage.get("ai_cost", Decimal(0)) >= subscription.spend_limit
        ):
            automation = False
            reason = "SPEND_LIMIT_REACHED"
    return Entitlement(
        managed=True,
        status=status,
        automation=automation,
        sending=sending,
        reason=reason,
        plan_key=subscription.plan_key if subscription else None,
        allowances=allowances,
        usage=usage,
        is_production=is_production,
    )


async def meter(
    session: AsyncSession,
    tenant_id: UUID,
    environment_id: UUID,
    metric: str,
    quantity: Decimal | int | float = 1,
) -> None:
    """Atomically add usage (participates in the caller's transaction). Only Pi
    businesses are metered; Owner OS workspaces use the AI usage ledger alone."""
    exists = await session.scalar(
        select(PiBusinessAccount.id).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if exists is None:
        return
    amount = Decimal(str(quantity))
    await session.execute(
        insert(PiUsageCounter)
        .values(
            tenant_id=tenant_id,
            environment_id=environment_id,
            period=month(),
            metric=metric,
            quantity=amount,
        )
        .on_conflict_do_update(
            constraint="uq_pi_usage_counters_metric",
            set_={"quantity": PiUsageCounter.quantity + amount},
        )
    )


async def meter_ai(
    session: AsyncSession,
    records: list[tuple[UUID, UUID, int | None, int | None, Decimal | None]],
) -> None:
    """Meter AI tokens and estimated cost per (tenant, environment)."""
    totals: dict[tuple[UUID, UUID], tuple[int, Decimal]] = {}
    for tenant_id, environment_id, input_tokens, output_tokens, cost in records:
        tokens, spent = totals.get((tenant_id, environment_id), (0, Decimal(0)))
        totals[(tenant_id, environment_id)] = (
            tokens + (input_tokens or 0) + (output_tokens or 0),
            spent + (cost or Decimal(0)),
        )
    for (tenant_id, environment_id), (tokens, spent) in totals.items():
        if tokens:
            await meter(session, tenant_id, environment_id, "ai_tokens", tokens)
        if spent:
            await meter(session, tenant_id, environment_id, "ai_cost", spent)


async def storage_used_mb(session: AsyncSession, tenant_id: UUID) -> Decimal:
    """Knowledge text kept for this business (all environments), in MB."""
    from sqlalchemy import func

    from app.modules.pi.models import KnowledgeDocument

    used = await session.scalar(
        select(func.coalesce(func.sum(func.octet_length(KnowledgeDocument.body)), 0)).where(
            KnowledgeDocument.tenant_id == tenant_id
        )
    )
    return (Decimal(int(used or 0)) / Decimal(1024 * 1024)).quantize(Decimal("0.01"))


async def check_storage(session: AsyncSession, tenant_id: UUID, adding_bytes: int) -> None:
    """Refuse new knowledge that would go past the plan's storage allowance."""
    from app.shared.errors import BusinessRuleViolation

    plan_state = await entitlement(session, tenant_id)
    limit = plan_state.allowances.get("storage_mb") if plan_state.managed else None
    if limit is None:
        return
    used = await storage_used_mb(session, tenant_id)
    if used + Decimal(adding_bytes) / Decimal(1024 * 1024) > Decimal(str(limit)):
        raise BusinessRuleViolation(
            "STORAGE_LIMIT_REACHED",
            f"Your plan includes {limit} MB of business knowledge. Remove old documents "
            "or upgrade to add more.",
            402,
        )


async def remaining(
    session: AsyncSession, tenant_id: UUID, environment_id: UUID, metric: str
) -> Decimal | None:
    """How much of a metered allowance is left this month (None = unlimited)."""
    state = await entitlement(session, tenant_id, environment_id)
    key = ALLOWANCE_FOR.get(metric)
    if not state.managed or not state.is_production or key is None:
        return None
    limit = state.allowances.get(key)
    if limit is None:
        return None
    return max(Decimal(0), Decimal(str(limit)) - state.usage.get(metric, Decimal(0)))
