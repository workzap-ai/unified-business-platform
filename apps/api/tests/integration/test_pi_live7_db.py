"""Live test 7 (owner, the clothing chat of test 6): the first ideas were wrong, the person said
"solution glt hai again den" and pi must give two new ideas that fit, never "those are all the
ideas I have"."""

import pytest
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_solution_learning import model

from app.modules.customers.models import Customer
from app.modules.pi import solution_context

pytestmark = pytest.mark.integration

NOTED = [
    {
        "group": "stock_inventory",
        "subtype": "overstock_dead_stock",
        "title": "Excess stock to sell off",
        "user_words": ["6crore ka stock wo bechna hai", "warehouse and outlets", "poore sets"],
    }
]


async def test_a_rejection_gets_new_ideas_that_share_evidence_never_the_dead_end(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    await say(pi, "mera clothing brand hai, 6crore ka stock wo bechna hai", "l7-1")
    conversation = await pi.conversation()
    customer = await business_db.get(Customer, conversation.customer_id)
    customer.industry_primary = "fashion_and_apparel_brands"
    conversation.flow_state = "S4_SORTED_SUMMARY"
    conversation.service_brief = {}
    first = await solution_context.build(
        business_db, scope, conversation, "solution dein ap", NOTED, {}
    )
    assert len(first["solution_ideas"]) == 2
    assert not any("buffer" in i or "website" in i.lower() for i in first["solution_ideas"])
    again = await solution_context.build(
        business_db, scope, conversation, "solution glt hai again den", NOTED, {}
    )
    assert again.get("solution_ideas"), again  # not "those are all the ideas I have"
    assert again["solution_rejected_fit"] is True
    assert not set(again["solution_ideas"]) & set(first["solution_ideas"])
    clearance = ("unsold", "sets", "slow", "buyers", "stock", "pieces", "bulk")
    assert any(w in " ".join(again["solution_ideas"]).lower() for w in clearance), (first, again)
