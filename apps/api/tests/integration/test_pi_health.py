"""pi Health: problems found from live data, safe fixes done by pi (and recorded), and
pi's self-tests (AI mocked; nothing is sent)."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _customer_in_chat, _lead
from test_pi_pipeline import pi_workspace

from app.ai.manager import LLMManager
from app.modules.audit.models import AuditEvent
from app.modules.pi.models import PiMessage
from app.modules.pi.service_conversation import Requirements, ServiceTurn
from app.modules.pi_saas.health_selftest import SCENARIOS
from app.modules.quotes.models import Quote

pytestmark = pytest.mark.integration

HEALTH = "/api/v1/pi/health"


def _check(state: dict, key: str) -> dict:
    return next(c for c in state["checks"] if c["key"] == key)


async def test_health_finds_stuck_work_and_pi_fixes_the_safe_part(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    customer_id, conversation = await _customer_in_chat(pi)
    lead_id = await _lead(pi, customer_id, conversation)
    made = await api.post(f"/api/v1/pi/deals/leads/{lead_id}/proposal")
    assert made.status_code == 201, made.text
    quote = await business_db.get(Quote, UUID(made.json()["quote_id"]))
    quote.created_at = datetime.now(UTC) - timedelta(days=2)
    old = datetime.now(UTC) - timedelta(minutes=10)
    stuck = PiMessage(
        tenant_id=UUID(pi.tenant_id),
        environment_id=UUID(pi.environment_id),
        conversation_id=conversation.id,
        direction="outbound",
        sender_type="ai",
        body="Thanks, the team will confirm here.",
        status="queued",
        created_at=old,
        updated_at=old,
    )
    business_db.add(stuck)
    await business_db.flush()

    response = await api.get(HEALTH)
    assert response.status_code == 200, response.text
    state = response.json()
    assert _check(state, "messages_stuck")["status"] == "warning"
    assert _check(state, "messages_stuck")["count"] == 1
    assert _check(state, "messages_stuck")["fix"] == "auto"
    unpriced = _check(state, "deals_unpriced")
    assert unpriced["status"] == "warning" and unpriced["count"] == 1
    assert unpriced["fix"] == "settings" and unpriced["href"].startswith("/quotes")
    assert state["score"] < 100
    assert len(state["trends"]) == 7 and state["fixed_recently"]["total"] == 0

    queue = api._transport.app.state.queue  # type: ignore[attr-defined]
    queue.jobs.clear()
    healed = await api.post(f"{HEALTH}/heal")
    assert healed.status_code == 200, healed.text
    assert ("send_pi_message", (str(stuck.id),)) in queue.jobs
    after = healed.json()
    assert _check(after, "messages_stuck")["status"] == "fixed"
    assert _check(after, "messages_stuck")["last_fixed_at"]
    assert after["fixed_recently"]["total"] >= 1
    assert after["score"] > state["score"]
    fixed = await business_db.scalar(
        select(AuditEvent).where(
            AuditEvent.tenant_id == UUID(pi.tenant_id),
            AuditEvent.action == "pi.health.fixed",
        )
    )
    assert fixed is not None and fixed.details["check"] == "messages_stuck"
    assert fixed.details["count"] == 1
    # The quote is the business's own data: still shown, never changed by pi.
    await business_db.refresh(quote)
    assert quote.status == "draft"
    assert _check(after, "deals_unpriced")["status"] == "warning"
    assert sum(day["fixes"] for day in after["trends"]) >= 1


def _service_turn(reply: str, ready: bool = False) -> ServiceTurn:
    return ServiceTurn(
        reply=reply,
        language="en",
        summary="Customer is asking about the business.",
        requirements=Requirements(service="Logo"),
        missing=[],
        awaiting_customer=not ready,
        ready_for_team=ready,
    )


async def test_self_tests_are_recorded_and_shown(api, business_db, monkeypatch):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    replies = {
        "Hi": _service_turn("Hello, welcome to our studio. What can we help you with today?"),
        "Tell me about your services": _service_turn(
            "Thanks for asking! We can help with that, feel free to ask."
        ),
    }
    last: list[ServiceTurn] = []

    async def complete(self, scope, output, **kwargs):
        text = kwargs["messages"][-1].text()
        if text.startswith("Don't send that draft") and last:
            return SimpleNamespace(value=last[-1], response=SimpleNamespace(attempts=[]))
        try:
            latest = json.loads(text).get("latest_customer_message", "")
        except ValueError:
            latest = ""
        value = replies.get(latest) or _service_turn("Thank you, I have noted that.")
        last.append(value)
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)

    response = await api.post(f"{HEALTH}/self-test")
    assert response.status_code == 200, response.text
    tests = response.json()["self_tests"]
    assert tests["last_run_at"] and len(tests["scenarios"]) == len(SCENARIOS)
    by_key = {s["key"]: s for s in tests["scenarios"]}
    assert by_key["greeting"]["passed"] is True, by_key["greeting"]
    services = by_key["services"]
    assert services["passed"] is False and services["reason"]
    assert services["href"] == "/pi/knowledge"
    assert tests["pass_rate"] is not None and 0 < tests["pass_rate"] < 100
    assert tests["daily"][-1]["total"] >= len(SCENARIOS)

    rows = list(
        await business_db.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == UUID(pi.tenant_id),
                AuditEvent.action == "pi.health.self_test",
            )
        )
    )
    assert {r.details["scenario"] for r in rows} == {s.key for s in SCENARIOS}
    shown = (await api.get(HEALTH)).json()["self_tests"]
    assert {s["key"]: s["passed"] for s in shown["scenarios"]}["greeting"] is True
