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
