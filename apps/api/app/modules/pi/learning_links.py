"""The linking threshold, tuned from what staff confirm and reject (pi Brain spec 8.10).

pi suggests that two problems may share a root. Staff confirm or reject each suggestion; that tells
pi how sure it must be before it suggests a link in a given industry. Where staff keep rejecting,
the threshold goes up a step; where they almost never do, it comes down a step. At most one step a
week per industry, always inside the range in `brain_config`, and never while learning is frozen.
A link is only ever a suggestion: this changes how many are made, nothing a person is told.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import brain_config
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiSettings
from app.modules.pi.problem_models import PiProblem, PiProblemLink
from app.shared.scope import WorkspaceScope

STEP = 5  # percentage points
MIN_DECISIONS = 10  # in the window, before the threshold moves up
MIN_DECISIONS_DOWN = 20  # more is needed before it is made easier
RAISE_AT = 0.40  # share rejected
LOWER_AT = 0.10
WINDOW = timedelta(days=30)
WEEK = timedelta(days=7)
OTHER = "_other"
KIND = "link_threshold"


def threshold_for(response_rules: dict[str, Any] | None, industry: str | None) -> Decimal:
    """The least confidence at which pi may suggest a link for a customer of this industry."""
    return Decimal(brain_config.link_pct(response_rules, industry)) / 100


async def decisions(
    session: AsyncSession, scope: WorkspaceScope, since: datetime
) -> dict[str, dict[str, int]]:
    """{industry: {"confirmed": n, "rejected": n}} for links staff decided since `since`."""
    rows = await session.execute(
        select(PiProblemLink.status, Customer.industry_primary)
        .join(PiProblem, PiProblem.id == PiProblemLink.from_id)
        .join(Customer, Customer.id == PiProblem.customer_id)
        .where(
            PiProblemLink.tenant_id == scope.tenant_id,
            PiProblemLink.environment_id == scope.environment_id,
            PiProblemLink.status.in_(("confirmed", "rejected")),
            PiProblemLink.updated_at >= since,
        )
    )
    out: dict[str, dict[str, int]] = {}
    for status, industry in rows:
        counts = out.setdefault(industry or OTHER, {"confirmed": 0, "rejected": 0})
        counts[status] += 1
    return out


def next_pct(current: int, confirmed: int, rejected: int) -> int:
    """One step up when staff reject a lot, one step down when they almost never do."""
    total = confirmed + rejected
    low, high = brain_config.LINK_RANGE
    if total >= MIN_DECISIONS and rejected / total > RAISE_AT:
        return min(high, current + STEP)
    if total >= MIN_DECISIONS_DOWN and rejected / total < LOWER_AT:
        return max(low, current - STEP)
    return current


async def tune(
    session: AsyncSession, scope: WorkspaceScope, settings: PiSettings, now: datetime
) -> dict[str, Any]:
    """One weekly step per industry. Returns the industries that moved, for the digest."""
    recent = await decisions(session, scope, now - WINDOW)
    last = {
        str((c.after or {}).get("industry")): c.created_at
        for c in await session.scalars(
            select(PiLearningChange)
            .where(
                PiLearningChange.tenant_id == scope.tenant_id,
                PiLearningChange.environment_id == scope.environment_id,
                PiLearningChange.kind == KIND,
            )
            .order_by(PiLearningChange.created_at)
        )
    }
    rules = dict(settings.response_rules or {})
    brain = dict(rules.get("brain") or {})
    table = dict(brain.get("link_thresholds") or {})
    moved: dict[str, int] = {}
    for industry, counts in sorted(recent.items()):
        if industry in last and now - last[industry] < WEEK:
            continue
        current = brain_config.link_pct(rules, None if industry == OTHER else industry)
        new = next_pct(current, counts["confirmed"], counts["rejected"])
        if new == current:
            continue
        table[industry] = new
        moved[industry] = new
        session.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind=KIND,
                risk="low",
                before={"industry": industry, "pct": current},
                after={"industry": industry, "pct": new},
                evidence=counts,
                status="live",
                reason=f"staff {'rejected' if new > current else 'confirmed'} most suggestions",
            )
        )
    if moved:
        brain["link_thresholds"] = table
        rules["brain"] = brain
        settings.response_rules = rules
    return {"moved": moved}
