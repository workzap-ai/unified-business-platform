"""B1 in a real turn: the owner lists four problems, the model first notes two, and (with the
workspace's list_guard on) the reply goes back once for the two it dropped. Off, nothing changes."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, create, problems_of, say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi.problem_models import PiProblem

pytestmark = pytest.mark.integration

HELLO = "hello"
LIST = """Meri dukaan ke masle:
- Cash day end par match nahi hota, 4000 rupay kam
- Cashiers weekend par late aate hain
- Chawal ka stock do shops mein khatam ho jata hai
- Suppliers har Monday ko late deliver karte hain
"""
FIRST_TWO = [
    create("Cash does not match at day end", "4000 rupay kam", category="cash_collections"),
    create("Cashiers come late on weekends", "weekend par late aate hain", category="staff"),
]
ALL_FOUR = [
    *FIRST_TWO,
    create("Rice stock runs out in two shops", "Chawal ka stock do shops mein khatam"),
    create("Suppliers deliver late on Mondays", "Suppliers har Monday late", category="suppliers"),
]


def models(monkeypatch):
    seen: dict = {"replies": 0, "rewrites": []}

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{"):
            context = json.loads(text)
            if context.get("latest_customer_message") == HELLO:
                value = turn(
                    reply=f"{OPENING} Aap ke business ka naam kya hai?", language="roman_ur"
                )
            else:
                seen["replies"] += 1
                value = turn(
                    reply="Cash ka masla aur late cashiers, samajh aaya. Kaun si shop?",
                    language="roman_ur",
                    problem_ops=FIRST_TWO,
                )
        else:
            seen["rewrites"].append(text)
            value = turn(
                reply="Chawal aur Monday ki deliveries bhi, samajh aaya. Kaun si shop mein?",
                language="roman_ur",
                problem_ops=ALL_FOUR,
            )
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    return seen


async def list_guard(api, on: bool) -> None:
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"brain": {"list_guard": on}}}
    )
    assert response.status_code == 200, response.text


async def test_a_dropped_list_item_goes_back_for_one_rewrite_when_the_guard_is_on(
    api, business_db, monkeypatch
):
    seen = models(monkeypatch)
    pi = await workspace(api, business_db)
    await list_guard(api, True)
    await say(pi, HELLO, "lg-0")
    await say(pi, LIST, "lg-1")
    assert len(seen["rewrites"]) == 1
    assert "Suppliers har Monday ko late deliver karte hain" in seen["rewrites"][0]
    assert "Chawal ka stock do shops" in seen["rewrites"][0]
    assert "Cashiers weekend par late" not in seen["rewrites"][0]  # that one was noted
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 4
    await pi.close()


async def test_nothing_changes_when_the_guard_is_off(api, business_db, monkeypatch):
    seen = models(monkeypatch)
    pi = await workspace(api, business_db)
    await say(pi, HELLO, "lg-2")
    await say(pi, LIST, "lg-3")
    assert seen["rewrites"] == []
    _, rows = await problems_of(business_db, pi)
    assert len(rows) == 2
    assert await business_db.scalar(select(PiProblem.id).limit(1)) is not None
    await pi.close()
