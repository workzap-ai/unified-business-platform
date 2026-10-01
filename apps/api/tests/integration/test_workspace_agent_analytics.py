"""Agent Beta analytics, forecasts and the advisory team against real PostgreSQL."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from test_workspace_agent import BASE, bind

from app.ai.types import LLMResponse, ToolCall
from app.modules.billing.models import Invoice, Payment
from app.modules.customers.models import Customer
from app.modules.finance.models import Expense
from app.modules.orders.models import Order
from app.modules.reports.service import months_back
from app.modules.sales.models import SalesLead
from app.modules.workspace_agent.team import DecisionBrief, Recommendation, SpecialistView
from tests.support.workspace import add_member

pytestmark = pytest.mark.integration
COLLECTED = [100, 120, 140, 160, 180, 200]  # last six months, oldest first


async def seed(stack, owner):
    """Six months of collections, orders and expenses, an overdue invoice and a pipeline."""
    db = stack.app.state.test_connection
    scope = {"tenant_id": UUID(owner.tenant_id), "environment_id": UUID(owner.environment_id)}
    customer = uuid4()
    await db.execute(Customer.__table__.insert().values(id=customer, **scope, name="Acme"))
    months = months_back(6)
    for i, (month, amount) in enumerate(zip(months, COLLECTED, strict=True)):
        day = month + timedelta(days=4)
        invoice = uuid4()
        await db.execute(
            Invoice.__table__.insert().values(
                id=invoice,
                **scope,
                number=f"INV-{i}",
                customer_id=customer,
                status="paid",
                issue_date=day,
                due_date=day + timedelta(days=14),
                currency="USD",
                subtotal=Decimal(amount),
                total=Decimal(amount),
                amount_paid=Decimal(amount),
            )
        )
        await db.execute(
            Payment.__table__.insert().values(
                id=uuid4(),
                **scope,
                invoice_id=invoice,
                number=f"PAY-{i}",
                amount=Decimal(amount),
                currency="USD",
                method="cash",
                received_on=day,
                recorded_by_label="test",
            )
        )
        await db.execute(
            Expense.__table__.insert().values(
                id=uuid4(),
                **scope,
                number=f"EXP-{i}",
                category="rent",
                description="Rent",
                amount=Decimal(50),
                currency="USD",
                incurred_on=day,
                recorded_by_label="test",
            )
        )
        await db.execute(
            Order.__table__.insert().values(
                id=uuid4(),
                **scope,
                number=f"ORD-{i}",
                customer_id=customer,
                status="confirmed",
                currency="USD",
                total=Decimal(amount),
                created_by_label="test",
                created_at=datetime.combine(day, datetime.min.time(), UTC),
            )
        )
    await db.execute(
        Invoice.__table__.insert().values(
            id=uuid4(),
            **scope,
            number="INV-LATE",
            customer_id=customer,
            status="issued",
            issue_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=10),
            currency="USD",
            subtotal=Decimal(75),
            total=Decimal(75),
        )
    )
    for title, stage, value in (
        ("A", "new", 1000),
        ("B", "proposal", 500),
        ("C", "won", 300),
        ("D", "lost", 100),
    ):
        await db.execute(
            SalesLead.__table__.insert().values(
                id=uuid4(), **scope, title=title, stage=stage, estimated_value=value, currency="USD"
            )
        )


async def test_report_is_exact_with_forecast_and_permission_filtered(stack):
    async with stack.browser() as ob, stack.browser() as ab:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        report = (await owner.get(f"{BASE}/analytics", params={"topic": "report"})).json()
        charts = {c["id"]: c for c in report["charts"]}
        revenue = report["facts"]["revenue"]
        assert revenue["collected"][-6:] == COLLECTED and revenue["overdue"] == 75
        forecast = charts["revenue_forecast"]
        future = [p for p in forecast["data"] if p["actual"] is None]
        # The partial current month never feeds the model: 5 complete months, rising.
        assert len(future) == 3 and future[0]["period"] == revenue["months"][-1]
        assert future[0]["forecast"] > 180 and future[2]["forecast"] > future[0]["forecast"]
        assert forecast["series"][1] == {"key": "forecast", "label": "Forecast", "dashed": True}
        assert "5 complete months" in forecast["description"]
        assert "so far USD 200" in forecast["description"]
        sales = report["facts"]["sales"]
        assert sales["weighted_value"] == pytest.approx(1000 * 0.1 + 500 * 0.6)
        assert sales["win_rate_pct"] == 50.0
        net = charts["net_cash"]["data"][-1]["net"]
        assert net == COLLECTED[-1] - 50
        kpis = {k["key"]: k for k in report["kpis"]}
        # Month to date vs the same first days of last month (seeded on day 5).
        same_days = 180 if date.today().day >= 5 else 0
        assert kpis["collected_month"]["value"] == 200
        assert kpis["collected_month"]["previous"] == same_days
        assert kpis["collected_month"]["compare"].startswith("vs first")
        assert {"revenue", "sales", "expenses", "orders"} <= set(report["checked_areas"])
        # Accountants see money but not the sales pipeline; nothing leaks through facts.
        accountant = bind(await stack.login(ab, await add_member(owner, ["accountant"])))
        seen = (await accountant.get(f"{BASE}/analytics", params={"topic": "report"})).json()
        assert "sales" not in seen["checked_areas"] and "sales" not in seen["facts"]
        assert "revenue" in seen["checked_areas"]
        for params in ({"months": 100}, {"topic": "everything"}):
            bad = await accountant.get(f"{BASE}/analytics", params=params)
            assert bad.status_code == 422, params  # validation, never a 500


async def test_sales_role_never_sees_money_it_cannot_read(stack):
    async with stack.browser() as ob, stack.browser() as sb:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        seller = bind(await stack.login(sb, await add_member(owner, ["sales"])))
        seen = (await seller.get(f"{BASE}/analytics", params={"topic": "report"})).json()
        assert {"revenue", "cashflow", "expenses"}.isdisjoint(seen["checked_areas"])
        assert "revenue" not in json.dumps(seen["facts"])
        team = (await seller.post(f"{BASE}/team", {"question": "Should I hire?"})).json()
        assert team["mode"] == "rules" and "finance" not in team["consulted"]


async def test_rule_based_brief_without_ai_points_to_real_problems(stack):
    async with stack.browser() as browser:
        owner = bind(await stack.register(browser))
        await seed(stack, owner)
        answer = (
            await owner.post(f"{BASE}/chat", {"message": "Is mahine kya focus karun? mashwara do"})
        ).json()
        brief = answer["team"]["brief"]
        assert answer["team"]["mode"] == "rules" and answer["team"]["specialists"] == []
        assert any(step["page"] == "/billing" for step in brief["next_steps"])
        assert any("overdue" in r for r in brief["risks"])
        assert "Rule-based" in brief["assumptions"][0]
        sales = (
            await owner.post(f"{BASE}/chat", {"message": "Please tell me summary about sales"})
        ).json()
        assert sales["analytics"][0]["topic"] == "sales"


async def test_team_runs_specialists_in_parallel_with_scoped_facts(stack, monkeypatch):
    import app.modules.workspace_agent.routes as routes

    prompts: list[tuple[str, str]] = []

    class FakeManager:
        async def complete(self, scope, **kwargs):
            prompts.append((kwargs["purpose"], kwargs["messages"][-1].text()))
            if kwargs["schema"] is SpecialistView:
                return LLMResponse(
                    "",
                    "test",
                    "test",
                    output=SpecialistView(headline="Collections are rising", confidence="high"),
                )
            return LLMResponse(
                "",
                "test",
                "test",
                output=DecisionBrief(
                    answer="Collections grew 4 months in a row.",
                    recommendation="Chase the overdue invoice first.",
                    next_steps=[
                        Recommendation(action="Chase INV-LATE", why="Late", page="/billing"),
                        Recommendation(action="Open evil", why="x", page="https://evil.test"),
                    ],
                ),
            )

    monkeypatch.setattr(routes, "ai_enabled", lambda request: True)
    monkeypatch.setattr(routes, "manager", lambda request: FakeManager())
    async with stack.browser() as ob, stack.browser() as ab:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        team = (await owner.post(f"{BASE}/team", {"question": "Should I hire?"})).json()
        assert team["mode"] == "ai"
        assert {"finance", "sales", "operations", "analyst"} <= set(team["consulted"])
        assert [s["page"] for s in team["brief"]["next_steps"]] == ["/billing", None]
        purposes = [p for p, _ in prompts]
        assert purposes[-1] == "workspace.strategy"
        assert purposes.count("workspace.team") == len(team["consulted"])
        # Each specialist only received its own domain's facts.
        team_prompts = [t for p, t in prompts if p == "workspace.team"]
        assert any("weighted_value" in t and '"collected"' not in t for t in team_prompts)
        assert any('"collected"' in t and "weighted_value" not in t for t in team_prompts)
        prompts.clear()
        accountant = bind(await stack.login(ab, await add_member(owner, ["accountant"])))
        await accountant.post(f"{BASE}/team", {"question": "Should I hire?"})
        assert prompts and all("weighted_value" not in t for _, t in prompts)


async def test_chat_analytics_tool_returns_charts_to_ui_and_numbers_to_model(stack, monkeypatch):
    import app.modules.workspace_agent.routes as routes

    seen = {}

    class FakeManager:
        def __init__(self):
            self.turn = 0

        async def complete(self, scope, **kwargs):
            self.turn += 1
            assert kwargs["alias"] == "agent"
            if self.turn == 1:
                return LLMResponse(
                    "",
                    "test",
                    "test",
                    tool_calls=[ToolCall("1", "analytics", {"topic": "revenue"})],
                )
            seen["tool"] = json.loads(kwargs["messages"][-1].text())
            return LLMResponse("Collections are up 11% on last month.", "test", "test")

    monkeypatch.setattr(routes, "ai_enabled", lambda request: True)
    monkeypatch.setattr(routes, "manager", lambda request: FakeManager())
    async with stack.browser() as browser:
        owner = bind(await stack.register(browser))
        await seed(stack, owner)
        answer = (await owner.post(f"{BASE}/chat", {"message": "Revenue forecast?"})).json()
        block = answer["analytics"][0]
        assert {c["id"] for c in block["charts"]} >= {"revenue_monthly", "revenue_forecast"}
        assert "charts" not in seen["tool"] and seen["tool"]["facts"]["revenue"]
        assert seen["tool"]["charts_shown_to_user"]
