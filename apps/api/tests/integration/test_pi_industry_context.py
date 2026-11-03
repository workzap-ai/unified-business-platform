"""Industry packs reach pi's prompt and the customer's record, only when the workspace
turns them on. Real database/webhook/worker; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.customers.models import Customer

pytestmark = pytest.mark.integration


def scripted(monkeypatch, *replies):
    """Each model call takes the next scripted turn (the last repeats); records the prompts."""
    queue = list(replies)
    prompts: list[str] = []

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":  # the separate note extractor: empty
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        prompts.append(kwargs["messages"][-1].text())
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts


def contexts(prompts: list[str]) -> list[dict]:
    """The context pi sent for each turn (retries after a rejected draft are plain text)."""
    return [json.loads(p) for p in prompts if p.startswith("{")]


async def turn_on(api) -> None:
    response = await api.patch(
        "/api/v1/pi/settings/knowledge_config", json={"value": {"industry_packs": True}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["knowledge_config"]["industry_packs"] is True


async def test_off_by_default_pi_hears_nothing_about_industries(api, business_db, monkeypatch):
    prompts = scripted(monkeypatch, turn(reply="Noted. How many branches?", language="en"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I run a pharmacy and expiry stock is a problem", "ind-off-1")
    await pi.deliver_all()
    context = contexts(prompts)[0]
    assert "industry" not in context and "industry_knowledge" not in context
    customer = await business_db.get(Customer, (await pi.conversation()).customer_id)
    assert customer.industry_primary is None
    await pi.close()


async def test_on_pi_gets_the_trades_knowledge_and_the_customer_keeps_it(
    api, business_db, monkeypatch
):
    prompts = scripted(
        monkeypatch,
        turn(reply="Noted. How many branches do you run?", language="en"),
        turn(reply="Noted. Who orders the stock?", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await turn_on(api)
    await pi.process("I run a pharmacy and expiry stock is a problem", "ind-on-1")
    await pi.deliver_all()
    first = contexts(prompts)[0]
    assert first["industry"] == ["Pharmacies and medical stores"]
    assert "Pharmacies and medical stores" in first["industry_knowledge"]
    assert "What Workzap might build" not in first["industry_knowledge"]

    conversation = await pi.conversation()
    customer = await business_db.get(Customer, conversation.customer_id)
    await business_db.refresh(customer)
    assert customer.industry_primary == "pharmacies_and_medical_stores"
    assert float(customer.industry_confidence) > 0.5

    # A later message that says nothing about the trade keeps the same industry.
    await pi.process("My manager is late every day", "ind-on-2")
    await pi.deliver_all()
    assert contexts(prompts)[-1]["industry"] == ["Pharmacies and medical stores"]
    await business_db.refresh(customer)
    assert customer.industry_primary == "pharmacies_and_medical_stores"
    await pi.close()


async def turn_strict_on(api) -> None:
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"constitution": True}}
    )
    assert response.status_code == 200, response.text


async def test_strict_voice_sends_a_style_slip_back_then_fixes_what_is_left(
    api, business_db, monkeypatch
):
    prompts = scripted(
        monkeypatch,
        turn(reply="Great question! I'd be happy to help. Which shop is it?", language="en"),
        turn(reply="Noted! Which shop is it?", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await turn_strict_on(api)
    await pi.process("My shop stock keeps running out", "strict-1")
    await pi.deliver_all()
    assert contexts(prompts)[0]["strict_voice"] is True
    assert "no hype" in prompts[1] and "R-VOICE-05" in prompts[1]
    reply = (await pi.reply_to("strict-1")).body
    assert "!" not in reply and "Great question" not in reply
    assert reply.startswith("Hi, I'm pi, an AI from Workzap.")  # first message says it is an AI
    assert reply.endswith("Which shop is it?")
    await pi.close()


async def test_strict_voice_never_sends_a_payment_claim(api, business_db, monkeypatch):
    scripted(monkeypatch, turn(reply="Payment received, thank you. Anything else?", language="en"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await turn_strict_on(api)
    await pi.process("I sent the money yesterday", "strict-2")
    await pi.deliver_all()
    sent = [m.body for m in await pi.outbound()]
    assert not any("Payment received" in body for body in sent)
    await pi.close()


async def test_the_linter_is_off_unless_the_workspace_turns_it_on(api, business_db, monkeypatch):
    prompts = scripted(monkeypatch, turn(reply="Great question! Which shop is it?", language="en"))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("My shop stock keeps running out", "strict-off")
    await pi.deliver_all()
    assert "strict_voice" not in contexts(prompts)[0]
    assert not any("R-VOICE" in prompt or "pi's rules" in prompt for prompt in prompts)
    await pi.close()
