"""pi replies in the language of the customer's latest message, strictly.
Real database/webhook/worker; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.errors import GatewayUnavailable
from app.ai.manager import LLMManager

pytestmark = pytest.mark.integration


def scripted(monkeypatch, *replies):
    """Each call takes the next scripted turn; records every prompt pi sent."""
    queue = iter(replies)
    prompts: list[str] = []

    async def complete(self, scope, output, **kwargs):
        prompts.append(kwargs["messages"][-1].text())
        value = next(queue)
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts


async def test_english_after_roman_urdu_gets_an_english_reply(api, business_db, monkeypatch):
    prompts = scripted(
        monkeypatch,
        turn(reply="Ji, main pi hoon, company ka AI assistant. Aap ko kya chahiye?"),
        # The model drifts back to Roman Urdu; pi's check sends it back once.
        turn(reply="Aap ka business kis type ka hai? Hum aap ki madad kar sakte hain."),
        turn(reply="Sure. What kind of business is it for?", language="roman_ur"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Salam, mujhe website chahiye", "lang-1")
    await pi.deliver_all()
    first = json.loads(prompts[0])
    assert first["reply_language"] == "roman_ur"
    await pi.process("Can you tell me your team performance?", "lang-2")
    await pi.deliver_all()
    second = json.loads(prompts[1])
    assert second["reply_language"] == "en" and second["reply_language_name"] == "English"
    assert prompts[2].startswith("Don't send that draft: it is written in Roman Urdu")
    replies = [m.body for m in await pi.outbound()]
    assert "Sure. What kind of business is it for?" in replies
    assert not any("kis type" in reply for reply in replies)
    conversation = await pi.conversation()
    assert conversation.language == "en"  # follows the customer, not the model's label
    await pi.close()


async def test_a_short_reply_keeps_the_language_of_the_chat(api, business_db, monkeypatch):
    prompts = scripted(
        monkeypatch,
        turn(reply="Hi, I'm pi, the company's AI assistant. What do you need?", language="en"),
        turn(reply="Great, noted.", language="en"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("I need a website for my bakery", "short-1")
    await pi.deliver_all()
    await pi.process("ok", "short-2")
    await pi.deliver_all()
    assert json.loads(prompts[1])["reply_language"] == "en"
    await pi.close()


async def test_team_notice_is_in_the_customers_language(api, business_db, monkeypatch):
    scripted(monkeypatch, GatewayUnavailable())
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Mujhe website chahiye, kitne din lagenge?", "notice-1")
    await pi.deliver_all()
    assert (await pi.conversation()).mode == "human"
    [notice] = await pi.outbound()
    assert notice.body.startswith("Aap ke message ka shukriya")
    await pi.close()


async def test_another_language_is_left_to_the_model(api, business_db, monkeypatch):
    prompts = scripted(
        monkeypatch,
        turn(reply="Ji, main pi hoon, company ka AI assistant. Aap ko kya chahiye?"),
        turn(reply="Claro. ¿Para qué tipo de negocio es la tienda?", language="es"),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Salam, mujhe website chahiye", "other-1")
    await pi.deliver_all()
    await pi.process("Necesito una tienda online para mi negocio", "other-2")
    await pi.deliver_all()
    assert "reply_language" not in json.loads(prompts[1])
    assert len(prompts) == 2  # no rewrite forced into Roman Urdu
    assert (await pi.conversation()).language == "es"
    await pi.close()
