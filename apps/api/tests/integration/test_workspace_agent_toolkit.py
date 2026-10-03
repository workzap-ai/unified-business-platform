"""Agent Beta toolkit: search, customer 360, what-if, activity and the new draft actions."""

from datetime import date, timedelta

import pytest
from test_workspace_agent import BASE, bind, decide, propose
from test_workspace_agent_analytics import seed

from app.ai.types import LLMResponse, ToolCall
from tests.support.workspace import add_member

pytestmark = pytest.mark.integration


async def test_search_spans_areas_and_respects_permissions(stack):
    async with stack.browser() as ob, stack.browser() as hb:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        found = (await owner.post(f"{BASE}/chat", {"message": "search Acme"})).json()
        assert {r["area"] for r in found["results"]} == {"customers"}
        invoices = (await owner.post(f"{BASE}/chat", {"message": "find INV-LATE"})).json()
        assert [r["area"] for r in invoices["results"]] == ["billing"]
        hr = bind(await stack.login(hb, await add_member(owner, ["hr"])))
        hidden = (await hr.post(f"{BASE}/chat", {"message": "search Acme"})).json()
        assert hidden["results"] == [] and "Nothing you can access" in hidden["message"]


async def fake_tools(monkeypatch, calls):
    """A model that calls the given tools on turn one, then answers."""
    import app.modules.workspace_agent.routes as routes

    class FakeManager:
        def __init__(self):
            self.turn = 0

        async def complete(self, scope, **kwargs):
            self.turn += 1
            if self.turn == 1:
                return LLMResponse(
                    "",
                    "test",
                    "test",
                    tool_calls=[ToolCall(str(i), n, a) for i, (n, a) in enumerate(calls)],
                )
            calls_seen.extend(m.text() for m in kwargs["messages"] if m.role == "tool")
            return LLMResponse("Done.", "test", "test")

    calls_seen: list[str] = []
    monkeypatch.setattr(routes, "ai_enabled", lambda request: True)
    monkeypatch.setattr(routes, "manager", lambda request: FakeManager())
    return calls_seen


async def test_customer_360_is_complete_for_owner_and_trimmed_for_sales(stack, monkeypatch):
    outputs = await fake_tools(monkeypatch, [("customer_360", {"name": "Acme"})])
    async with stack.browser() as ob, stack.browser() as sb:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        answer = (await owner.post(f"{BASE}/chat", {"message": "Tell me about Acme"})).json()
        areas = {r["area"] for r in answer["results"]}
        assert {
            "customer_profile",
            "customer_orders",
            "customer_invoices",
            "customer_leads",
        } <= areas
        unpaid = next(r for r in answer["results"] if r["area"] == "customer_invoices")
        assert unpaid["items"][0]["number"] == "INV-LATE" and unpaid["items"][0]["overdue"]
        assert '"overdue_invoices": 1' in outputs[0]
        seller = bind(await stack.login(sb, await add_member(owner, ["sales"])))
        outputs.clear()
        answer = (await seller.post(f"{BASE}/chat", {"message": "Tell me about Acme"})).json()
        areas = {r["area"] for r in answer["results"]}
        assert "customer_invoices" not in areas and "customer_orders" in areas
        assert "outstanding_by_currency" not in outputs[0]


async def test_what_if_projects_from_complete_months(stack, monkeypatch):
    await fake_tools(
        monkeypatch,
        [("what_if", {"new_monthly_cost": 100, "label": "Hire", "months": 6})],
    )
    async with stack.browser() as ob, stack.browser() as sb:
        owner = bind(await stack.register(ob))
        await seed(stack, owner)
        answer = (await owner.post(f"{BASE}/chat", {"message": "Can I afford a hire?"})).json()
        block = answer["analytics"][0]
        facts = block["facts"]
        # Last three complete months collected 140, 160, 180; spending 50 each month.
        assert facts["base_monthly_income"] == 160 and facts["base_monthly_spend"] == 50
        assert facts["scenario_monthly_spend"] == 150
        assert facts["cumulative_after_months"] == pytest.approx(10 * 6)
        assert facts["baseline_after_months"] == pytest.approx(110 * 6)
        assert block["charts"][0]["series"][1]["dashed"] is True
        # The simulator needs money access: sales can't run it.
        seller = bind(await stack.login(sb, await add_member(owner, ["sales"])))
        denied = (await seller.post(f"{BASE}/chat", {"message": "Can I afford a hire?"})).json()
        assert denied["analytics"] == []


async def test_activity_needs_audit_permission(stack):
    async with stack.browser() as ob, stack.browser() as sb:
        owner = bind(await stack.register(ob))
        await owner.create("customers", {"name": "Logged Customer"})
        seen = (
            await owner.post(f"{BASE}/chat", {"message": "Who changed things? activity"})
        ).json()
        activity = next(r for r in seen["results"] if r["area"] == "activity")
        assert any(e["action"] == "customer.created" for e in activity["items"])
        seller = bind(await stack.login(sb, await add_member(owner, ["sales"])))
        hidden = (await seller.post(f"{BASE}/chat", {"message": "activity"})).json()
        assert not any(r["area"] == "activity" for r in hidden["results"])


async def test_lead_note_and_expense_drafts_apply_only_on_confirm(stack):
    async with stack.browser() as ob, stack.browser() as sb:
        owner = bind(await stack.register(ob))
        customer = await owner.create("customers", {"name": "Draft Co"})
        lead = await propose(
            owner,
            "leads.create",
            {"title": "Website redesign", "customer_id": customer["id"], "estimated_value": "500"},
        )
        assert (await owner.get("sales/leads")).json()["total"] == 0
        lead_id = (await decide(owner, lead)).json()["result"]["ids"][0]
        moved = await propose(owner, "leads.update", {"id": lead_id, "stage": "qualified"})
        assert moved["preview"]["from_stage"] == "new"
        assert (await decide(owner, moved)).status_code == 200
        assert (await owner.get(f"sales/leads/{lead_id}")).json()["stage"] == "qualified"
        skip = await owner.post(
            f"{BASE}/proposals",
            {"operation": "leads.update", "arguments": {"id": lead_id, "stage": "won"}},
        )
        assert skip.status_code in {409, 422}  # qualified -> won skips the proposal stage
        note = await propose(
            owner, "customer_notes.create", {"customer_id": customer["id"], "body": "Call Friday"}
        )
        assert note["preview"]["customer"] == "Draft Co"
        assert (await decide(owner, note)).status_code == 200
        notes = (await owner.get(f"customers/{customer['id']}/notes")).json()["items"]
        assert notes[0]["body"] == "Call Friday"
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        future = await owner.post(
            f"{BASE}/proposals",
            {
                "operation": "expenses.create",
                "arguments": {
                    "category": "rent",
                    "description": "Rent",
                    "amount": "100",
                    "incurred_on": tomorrow,
                },
            },
        )
        assert future.status_code == 422
        expense = await propose(
            owner,
            "expenses.create",
            {
                "category": "rent",
                "description": "Rent",
                "amount": "100",
                "incurred_on": date.today().isoformat(),
            },
        )
        assert (await decide(owner, expense)).status_code == 200
        # Sales can draft leads but not record expenses.
        seller = bind(await stack.login(sb, await add_member(owner, ["sales"])))
        denied = await seller.post(
            f"{BASE}/proposals",
            {
                "operation": "expenses.create",
                "arguments": {
                    "category": "rent",
                    "description": "x",
                    "amount": "1",
                    "incurred_on": date.today().isoformat(),
                },
            },
        )
        assert denied.status_code == 403
        context = (await seller.get(f"{BASE}/context")).json()
        assert "leads.create" in context["actions"] and "expenses.create" not in context["actions"]
