"""Platform spec v1.4, Part 16: the opening warm-up through the real webhook flow (flag on).
Real database/webhook/worker; the AI and WhatsApp are mocked."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


def model(context, _call):
    if context.get("reply_language") == "roman_ur":
        return turn(
            reply="Hi, main pi hoon, Workzap ka AI. Kaun si dukaan mein sab se kam bikta hai?",
            language="roman_ur",
        )
    return turn(reply="Hi, I'm pi, an AI from Workzap. Which shop sells the least?", language="en")


async def warm_chat(api, db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"brain": {"warmup": True}}}
    )
    assert response.status_code == 200, response.text
    return pi


async def last_reply(pi, db, key):
    await db.rollback()
    return (await pi.reply_to(key)).body


async def test_hi_then_identity_then_page_ask_then_the_door(api, business_db, monkeypatch):
    pi = await warm_chat(api, business_db, monkeypatch)
    await say(pi, "Hi", "w-1")
    first = await last_reply(pi, business_db, "w-1")
    assert "an AI from Workzap" in first and first.count("?") == 1 and "called" in first
    await say(pi, "mera clothing brand hai, baby aur male clothes", "w-2")
    second = await last_reply(pi, business_db, "w-2")
    assert "link" in second.lower() and "public" in second.lower() and "?" not in second
    await say(pi, "website nahi hai", "w-3")
    third = await last_reply(pi, business_db, "w-3")
    # "website nahi hai" is Roman Urdu, so the chat continues in it (spec 16.2: language lock)
    assert third.startswith("Theek hai.") and third.count("?") == 1
    assert "bhaari" in third
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    brief = conversation.service_brief
    assert brief["warmup"]["step"] == "done"
    facts = {f["key"]: f for f in brief["business_profile"]["facts"]}
    assert facts["website"]["value"] == "none" and facts["what_they_do"]["confirmed"] is True
    await say(pi, "kapre bik nahi rahe", "w-4")  # now the ordinary model answers
    assert "dukaan" in await last_reply(pi, business_db, "w-4")
    await pi.close()


async def test_a_hurried_owner_gets_no_warmup(api, business_db, monkeypatch):
    pi = await warm_chat(api, business_db, monkeypatch)
    await say(pi, "mera sales staff gaib rehta hai, bohat masla hai", "h-1")
    reply = await last_reply(pi, business_db, "h-1")
    assert "dukaan" in reply and "called" not in reply
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.service_brief["warmup"]["step"] == "skipped"
    await pi.close()


async def test_without_the_flag_hi_gets_the_old_opening(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await say(pi, "Hi", "o-1")
    reply = await last_reply(pi, business_db, "o-1")
    assert reply == "Hi, I'm pi, an AI from Workzap. What does your business do?"
    count = len(list(await business_db.scalars(select(PiMessage.id))))
    assert count >= 2
    await pi.close()
