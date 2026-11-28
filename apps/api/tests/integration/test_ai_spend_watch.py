"""A workspace that makes a lot of paid calls is told once a day; a quiet one is not."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace

from app.ai import spend_watch
from app.ai.models import AIUsageEvent
from app.modules.notifications.models import Notification

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


def event(scope, provider="openai", purpose="pi_service", hours_ago=1, cost=None):
    return AIUsageEvent(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        provider=provider,
        model="gpt-x",
        alias="fast",
        purpose=purpose,
        status="success",
        latency_ms=100,
        estimated_cost=cost,
        created_at=NOW - timedelta(hours=hours_ago),
    )


async def alerts(db):
    db.expire_all()
    return (
        await db.scalars(select(Notification).where(Notification.kind == spend_watch.KIND))
    ).all()


async def test_too_many_openai_calls_alert_once_a_day_and_name_the_busiest(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "369600001")
    business_db.add_all([event(scope, purpose="pi_meeting_voice") for _ in range(6)])
    business_db.add_all([event(scope, provider="groq") for _ in range(50)])  # not counted
    business_db.add_all([event(scope, hours_ago=30) for _ in range(50)])  # too old
    await business_db.commit()

    assert await spend_watch.watch(business_db, call_line=5, cost_line=None, now=NOW) == 1
    assert await spend_watch.watch(business_db, call_line=5, cost_line=None, now=NOW) == 1
    (alert,) = await alerts(business_db)  # the second look found the same alert, not a new one
    assert alert.severity == "warning" and alert.required_permission == "pi.settings.manage"
    assert "6 OpenAI calls" in alert.body and "pi_meeting_voice" in alert.body
    # tomorrow is a new day, so a new alert
    later = NOW + timedelta(days=1)
    business_db.add_all([event(scope, hours_ago=-24 + 1) for _ in range(6)])
    await business_db.commit()
    await spend_watch.watch(business_db, call_line=5, cost_line=None, now=later)
    assert len(await alerts(business_db)) == 2
    await pi.close()


async def test_a_quiet_workspace_and_a_switched_off_line_raise_nothing(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "369600002")
    business_db.add_all([event(scope) for _ in range(3)])
    await business_db.commit()
    assert await spend_watch.watch(business_db, call_line=5, cost_line=None, now=NOW) == 0
    assert await spend_watch.watch(business_db, call_line=None, cost_line=None, now=NOW) == 0
    assert await alerts(business_db) == []
    await pi.close()


async def test_the_cost_line_counts_estimated_cost_and_says_it_can_under_count(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "369600003")
    business_db.add_all([event(scope, cost=Decimal("2.50")) for _ in range(2)])
    await business_db.commit()
    assert (
        await spend_watch.watch(business_db, call_line=None, cost_line=Decimal("4"), now=NOW) == 1
    )
    (alert,) = await alerts(business_db)
    assert "$5.00" in alert.body and "may be higher" in alert.body
    await pi.close()


async def test_a_failing_watch_never_raises(api, business_db):
    class Broken:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("db down")

        async def rollback(self):
            pass

    assert await spend_watch.watch(Broken(), call_line=1, cost_line=None, now=NOW) == 0
