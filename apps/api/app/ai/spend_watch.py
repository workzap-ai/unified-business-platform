"""A daily look at how much each workspace used the paid models (an alert, never a block).

Everything that goes through the AI gateway leaves a row in `ai_usage_events`. This adds up the
last 24 hours per workspace and tells its settings managers once a day when it looks high:

* the OpenAI call line (`ai_daily_openai_call_alert`) always works, because it only counts calls;
* the cost line (`ai_daily_cost_alert`) adds up `estimated_cost`, which exists only for models with
  a known price, so it can under-count. It says so in the message.

The notification names the busiest purposes and models and their call counts, never a prompt or a
reply. It does not stop anything: the hard stops stay where they are (the budget guard, the
workspace limits). What this does NOT see: anything that calls a provider outside the gateway
(a script run by hand, a notebook, a test with a real key). Only the provider's own dashboard
shows that, which is why a separate key with its own monthly limit is the real brake.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from app.ai.models import AIUsageEvent
from app.modules.notifications.service import notify
from app.modules.pi_meetings.guest_routes import system_scope

logger = logging.getLogger(__name__)

PERMISSION = "pi.settings.manage"
KIND = "ai_spend_alert"
TOP = 3  # purposes named in the message


async def _busiest(session: Any, tenant_id: Any, environment_id: Any, since: datetime) -> str:
    rows = await session.execute(
        select(AIUsageEvent.purpose, AIUsageEvent.model, func.count())
        .where(
            AIUsageEvent.tenant_id == tenant_id,
            AIUsageEvent.environment_id == environment_id,
            AIUsageEvent.provider == "openai",
            AIUsageEvent.created_at >= since,
        )
        .group_by(AIUsageEvent.purpose, AIUsageEvent.model)
        .order_by(func.count().desc())
        .limit(TOP)
    )
    return "; ".join(f"{purpose} on {model}: {n} calls" for purpose, model, n in rows.all())


async def watch(
    session: Any,
    *,
    call_line: int | None,
    cost_line: Decimal | None,
    now: datetime | None = None,
) -> int:
    """Alert each workspace over a line (once a UTC day). Returns how many alerts were raised."""
    if call_line is None and cost_line is None:
        return 0
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=24)
    raised = 0
    try:
        rows = await session.execute(
            select(
                AIUsageEvent.tenant_id,
                AIUsageEvent.environment_id,
                func.count().filter(AIUsageEvent.provider == "openai"),
                func.coalesce(func.sum(AIUsageEvent.estimated_cost), 0),
            )
            .where(AIUsageEvent.created_at >= since)
            .group_by(AIUsageEvent.tenant_id, AIUsageEvent.environment_id)
        )
        for tenant_id, environment_id, calls, cost in rows.all():
            over_calls = call_line is not None and calls >= call_line
            over_cost = cost_line is not None and Decimal(cost) >= cost_line
            if not (over_calls or over_cost):
                continue
            parts = []
            if over_calls:
                parts.append(f"{calls} OpenAI calls in the last 24 hours (line: {call_line})")
            if over_cost:
                parts.append(
                    f"about ${Decimal(cost):.2f} estimated cost (line: ${cost_line}); only "
                    "models with a known price are counted, so the real figure may be higher"
                )
            busiest = await _busiest(session, tenant_id, environment_id, since)
            await notify(
                session,
                system_scope(tenant_id, environment_id),
                KIND,
                "AI usage is high today",
                " and ".join(parts) + (f". Busiest: {busiest}." if busiest else "."),
                permission=PERMISSION,
                severity="warning",
                dedupe_key=f"ai-spend:{tenant_id}:{now.date().isoformat()}",
            )
            raised += 1
        await session.commit()
    except Exception:  # noqa: BLE001 - a watch never breaks the job that runs it
        logger.warning("ai_spend_watch_failed", exc_info=True)
        await session.rollback()
    return raised


async def sweep_ai_spend(ctx: dict[str, Any]) -> int:
    """The worker job (every half hour): the alert is once a day per workspace by its dedupe key."""
    settings = ctx["settings"]
    async with ctx["sessions"]() as session:
        return await watch(
            session,
            call_line=settings.ai_daily_openai_call_alert,
            cost_line=settings.ai_daily_cost_alert,
        )
