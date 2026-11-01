"""ROFFER07 in a real brain-mode chat: with response_rules.brain.quote_facts on, a yes to the offer
asks the missing quote facts once (one question, with the reason), and the answer starts the quote.
With the flag off nothing changes. Real database/webhook/worker; the AI and WhatsApp are mocked."""

import pytest
from sqlalchemy import select
from test_pi_brain_decisions import model, state_of, the_offer_is_open  # noqa: F401
from test_pi_brain_problems import adaptive, say, workspace

from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration


async def at_the_offer(
    api,
    db,
    monkeypatch,
    *,
    quote_facts,
    first="Best-sellers run out and cashiers are late on weekends",
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    if quote_facts:
        patched = await api.patch(
            "/api/v1/pi/settings/response_rules",
            json={"value": {"pi_mode": "brain", "brain": {"quote_facts": True}}},
        )
        assert patched.status_code == 200, patched.text
    await say(pi, first, "qf-1")
    await say(pi, "That's all", "qf-2")
    await say(pi, "looks right", "qf-3")
    return pi


async def test_quote_facts_on_a_yes_asks_once_then_the_answer_starts_the_quote(
    api, business_db, monkeypatch
):
    pi = await at_the_offer(api, business_db, monkeypatch, quote_facts=True)
    await say(pi, "yes", "qf-4")
    asked = (await pi.reply_to("qf-4")).body
    assert "quote is accurate" in asked and asked.count("?") == 1
    assert asked.rstrip().endswith("?")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S5_READINESS"  # nothing is prepared yet
    assert conversation.service_brief["quote_facts_asked"] is True
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []

    await say(pi, "three shops, in Lahore", "qf-5")
    conversation = await state_of(business_db, pi)
    assert conversation.flow_state == "S6_PREPARING"
    assert conversation.service_brief["quote_facts_done"] is True
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.kind == "review_document"
    await pi.close()


async def test_quote_facts_off_a_yes_goes_the_old_way(api, business_db, monkeypatch):
    pi = await at_the_offer(api, business_db, monkeypatch, quote_facts=False)
    await say(pi, "yes", "qf-4")
    assert (await pi.reply_to("qf-4")).body == "Should it cover all of these, or only some?"
    assert "quote_facts_asked" not in (await state_of(business_db, pi)).service_brief
    await pi.close()


async def test_quote_facts_only_the_facts_the_owner_has_not_given_are_asked(
    api, business_db, monkeypatch
):
    first = (
        "We have 3 shops in Lahore, stock is on paper. Best-sellers run out and cashiers are late"
    )
    pi = await at_the_offer(api, business_db, monkeypatch, quote_facts=True, first=first)
    await say(pi, "yes", "qf-4")
    # shops, places and the record system are all known: nothing to ask, the quote goes on
    assert "quote is accurate" not in (await pi.reply_to("qf-4")).body
    assert "quote_facts_asked" not in (await state_of(business_db, pi)).service_brief
    await pi.close()


async def test_quote_facts_a_gap_is_asked_with_at_most_two_questions_on_every_reply(
    api, business_db, monkeypatch
):
    first = "We have 3 shops. Best-sellers run out and cashiers are late on weekends"
    pi = await at_the_offer(api, business_db, monkeypatch, quote_facts=True, first=first)
    await say(pi, "yes", "qf-4")
    asked = (await pi.reply_to("qf-4")).body
    assert "quote is accurate" in asked and "shops" not in asked.lower().split("tell me")[-1]
    for outbound in await pi.outbound():
        assert (outbound.body or "").count("?") <= 2  # ROFFER07: never more than two questions
    await pi.close()
