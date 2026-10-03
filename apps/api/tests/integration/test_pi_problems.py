"""Problems board: Pi sorts each customer problem into a business department; the team
moves one, the move sticks for that problem and becomes an example Pi learns from."""

from types import SimpleNamespace

import pytest
from pi_saas_support import FakeProvider, configure
from test_pi_saas import _kapso, _message_event, _ready_business, _run_jobs
from test_pi_service_conversations import mock_turns, turn

from app.ai.manager import LLMManager
from app.modules.pi_customer.service import Issue, IssueReport

pytestmark = pytest.mark.integration


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


def _issues(monkeypatch, *departments: str) -> list[dict]:
    """Script the problem analysis and record what Pi was told."""
    seen: list[dict] = []

    async def complete(self, scope, output, **kwargs):
        if output is not IssueReport:
            raise AssertionError("only the problem analysis is expected here")
        import json

        seen.append(json.loads(kwargs["messages"][-1].text()))
        report = IssueReport(
            issues=[
                Issue(
                    title="Refund for double charge",
                    category="payment",
                    status="open",
                    summary="Customer was charged twice.",
                    department=departments[0],
                ),
                Issue(
                    title="Website login broken",
                    category="support",
                    status="with_team",
                    summary="Cannot log in to the portal.",
                    department=departments[1] if len(departments) > 1 else "nonsense",
                ),
            ]
        )
        return SimpleNamespace(value=report, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return seen


async def test_problems_are_sorted_by_department_and_moves_teach_pi(
    app, provider, business_db, monkeypatch
):
    mock_turns(monkeypatch, turn(reply="Ji, hum dekhte hain."))
    client, _ = await _ready_business(app, provider, business_db, "Board Co", "6400000001")
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("6400000001", "15550009101", "Paise do baar kat gaye", "wamid.pb-1"),
    )
    await _run_jobs(app, provider, business_db)
    empty = (await client.get("/api/v1/pi-app/problems")).json()
    assert empty["problems"] == [] and empty["waiting_for_analysis"] == 1
    assert [d["key"] for d in empty["departments"]][:3] == ["sales", "customer_support", "finance"]

    seen = _issues(monkeypatch, "finance", "it")
    board = (await client.post("/api/v1/pi-app/problems/refresh")).json()
    assert board["analysed"] == 1 and board["waiting_for_analysis"] == 0
    assert seen[0]["departments"][2]["key"] == "finance" and seen[0]["team_examples"] == []
    by_title = {p["title"]: p for p in board["problems"]}
    assert by_title["Refund for double charge"]["department"] == "finance"
    assert by_title["Website login broken"]["department"] == "it"
    finance = next(d for d in board["departments"] if d["key"] == "finance")
    assert finance["open"] == 1

    # The team decides login problems belong to customer support.
    login = by_title["Website login broken"]
    moved = await client.post(
        "/api/v1/pi-app/problems/move",
        json={
            "conversation_id": login["conversation_id"],
            "index": login["index"],
            "department": "customer_support",
        },
    )
    assert moved.status_code == 200, moved.text
    after = {p["title"]: p for p in moved.json()["problems"]}
    assert after["Website login broken"]["department"] == "customer_support"
    assert after["Website login broken"]["moved_by_team"] is True
    assert moved.json()["examples_learned"] == 1
    bad = await client.post(
        "/api/v1/pi-app/problems/move",
        json={"conversation_id": login["conversation_id"], "index": 0, "department": "space"},
    )
    assert bad.status_code == 422

    # A new message: Pi reads the chat again, is shown the team's example, and the
    # team's move still holds even though the model said "it" again.
    mock_turns(monkeypatch, turn(reply="Shukriya."))
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("6400000001", "15550009101", "Koi update?", "wamid.pb-2"),
    )
    await _run_jobs(app, provider, business_db)
    seen = _issues(monkeypatch, "finance", "it")
    board = (await client.post("/api/v1/pi-app/problems/refresh")).json()
    assert seen[0]["team_examples"] == [
        {
            "text": "Website login broken: Cannot log in to the portal.",
            "department": "customer_support",
        }
    ]
    again = {p["title"]: p for p in board["problems"]}
    assert again["Website login broken"]["department"] == "customer_support"

    # Settings forms that only send some fields keep the departments and examples.
    saved = await client.patch(
        "/api/v1/pi-app/pi/settings/handoff_rules", json={"value": {"max_failed_turns": 3}}
    )
    assert saved.status_code == 200, saved.text
    rules = (await client.get("/api/v1/pi-app/pi/settings")).json()["handoff_rules"]
    assert rules["max_failed_turns"] == 3 and len(rules["department_examples"]) == 1

    # Removing a department drops what Pi was taught for it; the rest stays.
    kept = [d for d in rules["departments"] if d["key"] != "customer_support"]
    saved = await client.patch(
        "/api/v1/pi-app/pi/settings/handoff_rules", json={"value": {"departments": kept}}
    )
    assert saved.status_code == 200, saved.text
    rules = (await client.get("/api/v1/pi-app/pi/settings")).json()["handoff_rules"]
    assert rules["department_examples"] == [] and rules["max_failed_turns"] == 3
    await client.aclose()


async def test_unknown_departments_fall_back_and_other_businesses_see_nothing(
    app, provider, business_db, monkeypatch
):
    mock_turns(monkeypatch, turn())
    client, _ = await _ready_business(app, provider, business_db, "Fallback Co", "6400000002")
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event("6400000002", "15550009102", "Help", "wamid.pb-3"),
    )
    await _run_jobs(app, provider, business_db)
    _issues(monkeypatch, "galaxy")
    board = (await client.post("/api/v1/pi-app/problems/refresh")).json()
    assert {p["department"] for p in board["problems"]} == {"customer_support"}
    other, _ = await _ready_business(app, provider, business_db, "Other Co", "6400000003")
    assert (await other.get("/api/v1/pi-app/problems")).json()["problems"] == []
    for c in (client, other):
        await c.aclose()
