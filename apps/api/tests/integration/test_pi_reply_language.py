"""pi replies in the language of the customer's latest message, strictly.
Real database/webhook/worker; the AI and WhatsApp are mocked."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn

from app.ai.errors import GatewayUnavailable
from app.ai.manager import LLMManager
from app.modules.pi.models import PiMessage
from app.modules.sales.models import SalesLead

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


async def test_hi_gets_a_short_english_greeting_despite_old_language_and_company_goals(
    api, business_db, monkeypatch
):
    bad_reply = (
        "Aapka message mila. Workzap ke kuch goals hain:\n"
        "• Hamari services ki quality ko behtar banana.\n"
        "• Clients ki zarurat ko samajhna aur unhe pura karna."
    )
    prompts = scripted(monkeypatch, turn(reply=bad_reply))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Hi", "greeting-first")
    await pi.deliver_all()
    first = await pi.reply_to("greeting-first")
    assert first.body.startswith("Hi, I'm pi, Service Agency's AI assistant.")
    assert first.body.endswith("How can I help you today?")

    conversation = await pi.conversation()
    previous_brief = {
        "requirements": {"service": "Website", "scope": "Online store"},
        "projects": [{"title": "Website", "details": "Online store", "status": "confirmed"}],
        "ready_for_team": True,
        "reminder_consent": "granted",
    }
    conversation.service_brief = previous_brief
    conversation.summary = "Earlier discussion: company goals and an online store."
    conversation.language = "roman_ur"
    business_db.add(
        PiMessage(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            conversation_id=conversation.id,
            direction="inbound",
            sender_type="customer",
            message_type="text",
            body="Aap ke business ke goals kya hain?",
            status="processed",
        )
    )
    await business_db.commit()
    for n, greeting in enumerate(("Hi", "HELLO!", "Good morning")):
        mid = f"greeting-return-{n}"
        await pi.process(greeting, mid)
        await pi.deliver_all()
        body = (await pi.reply_to(mid)).body
        assert body.startswith("Hi") and body.endswith("How can I help you today?")
    await business_db.refresh(conversation)
    assert conversation.language == "en"
    assert conversation.service_brief == previous_brief
    assert conversation.summary == "Earlier discussion: company goals and an online store."
    assert prompts == []  # Greetings cannot be turned into an unrelated model-generated pitch.
    assert (
        await business_db.scalar(
            select(func.count())
            .select_from(SalesLead)
            .where(SalesLead.tenant_id == conversation.tenant_id)
        )
        == 0
    )
    assert (await api.get("/api/v1/pi/requests")).json()["items"] == []
    assert len(pi.sent) == 4
    await pi.close()


@pytest.mark.parametrize(
    "draft",
    [
        "Main pi hoon, company ka AI assistant. Aap ka business kis type ka hai?",
        "I'm pi, your AI assistant. Aap ka business kis type ka hai?",
    ],
)
async def test_a_rewrite_still_in_the_wrong_language_is_never_sent(
    api, business_db, monkeypatch, draft
):
    prompts = scripted(monkeypatch, turn(reply=draft), turn(reply=draft))
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Can you explain your process?", "language-retry")
    await pi.deliver_all()
    assert len(prompts) == 2
    assert json.loads(prompts[0])["reply_language"] == "en"
    [reply] = await pi.outbound()
    assert reply.body == "Noted. I'm checking this with the team and will confirm here shortly."
    assert draft not in reply.body
    assert (await pi.conversation()).mode == "ai"
    assert (await api.get("/api/v1/pi/requests")).json()["items"]
    await pi.close()


async def test_team_notice_is_in_the_customers_language(api, business_db, monkeypatch):
    scripted(monkeypatch, GatewayUnavailable())
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("Mujhe website chahiye, kitne din lagenge?", "notice-1")
    await pi.deliver_all()
    assert (await pi.conversation()).mode == "ai"
    [notice] = await pi.outbound()
    assert notice.body.startswith("Noted. Main team se confirm")
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


async def test_a_youtube_link_is_read_before_pi_answers(api, business_db, monkeypatch):
    from app.modules.pi import links

    async def fake_get(outbound, url, accept):
        if "oembed" in url:
            body = '{"title": "Flight booking app demo", "author_name": "Travel Tech"}'
            return url, "application/json", body
        page = '<meta name="description" content="A flight search and booking app walkthrough.">'
        return url, "text/html", page

    async def fake_summary(manager, scope, alias, found, conversation):
        return "A demo of a flight booking app: search, seat choice, payment."

    monkeypatch.setattr(links, "_get", fake_get)
    monkeypatch.setattr(links, "_summary", fake_summary)
    prompts = scripted(
        monkeypatch,
        # Drafts the old mistakes: "I heard" for a typed message, and a promise to look later.
        turn(
            reply='I heard: "here you go". Please give me a moment to review the video, '
            "and I will provide feedback shortly.",
            language="en",
        ),
        turn(
            reply='I heard: "here you go". Got it: a flight booking app like this demo, with '
            "search, seat choice and payment. Is it for your own agency?",
            language="en",
        ),
    )
    pi = await pi_workspace(api, business_db, business_type="service_business")
    await pi.process("https://www.youtube.com/shorts/TuLe2t8h1KI here you go", "link-1")
    await pi.deliver_all()
    context = json.loads(prompts[0])
    [link] = context["shared_links"]
    assert link["title"] == "Flight booking app demo" and link["kind"] == "video"
    assert prompts[1].startswith("Don't send that draft: it promises to watch or review")
    [reply] = [m.body for m in await pi.outbound()]
    assert reply.startswith("Got it: a flight booking app")  # "I heard" removed
    await pi.close()
