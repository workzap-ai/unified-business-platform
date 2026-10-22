"""Brain mode safety (spec Part 6) in a real chat: emergencies, personal data, advice and "who are
you". Real database/webhook/worker; the AI and WhatsApp are mocked."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage
from app.modules.pi.quarantine_models import PiQuarantine
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration

PK = "923001234567"


def neutral(context, n):
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def chat(api, db, monkeypatch):
    prompts = adaptive(monkeypatch, neutral)
    pi = await workspace(api, db)
    return pi, prompts


async def test_an_emergency_gets_the_local_numbers_and_a_staff_alert(api, business_db, monkeypatch):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await pi.process("Fire in my shop!!", "em-1", sender=PK)
    await pi.deliver_all()
    reply = await pi.reply_to("em-1")
    assert reply.body == "I can't help with emergencies. Please call 16 (fire) now."
    assert prompts == []  # the model never saw it
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "X_EMERGENCY"
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.priority == "high" and "POSSIBLE EMERGENCY (fire)" in request.question
    # The next ordinary message ends the emergency state and the chat listens again.
    await pi.process("Sorry, all fine now. Best-sellers run out in two shops", "em-2", sender=PK)
    await pi.deliver_all()
    await business_db.refresh(conversation)
    assert conversation.flow_state != "X_EMERGENCY"
    await pi.close()


async def test_a_card_number_is_redacted_kept_encrypted_and_pi_says_so_once(
    api, business_db, monkeypatch
):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await say(pi, "Stock runs out in two shops. My card is 4111 1111 1111 1111", "pv-1")
    first = (await pi.reply_to("pv-1")).body
    assert "card numbers" in first and "payment never happens in this chat" in first
    assert all("4111" not in p for p in map(str, prompts))
    stored = (
        await business_db.scalars(select(PiMessage).where(PiMessage.provider_message_id == "pv-1"))
    ).one()
    assert "4111" not in stored.body and "[card number removed]" in stored.body
    [kept] = (await business_db.scalars(select(PiQuarantine))).all()
    assert kept.kinds == ["card"] and "4111" not in kept.payload  # encrypted at rest
    await say(pi, "Again: 4111 1111 1111 1111 and cashiers come late", "pv-2")
    assert "card numbers" not in (await pi.reply_to("pv-2")).body  # said once per kind
    await pi.close()


async def test_a_message_with_only_a_secret_gets_only_the_reminder(api, business_db, monkeypatch):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await say(pi, "4111 1111 1111 1111", "po-1")
    reply = (await pi.reply_to("po-1")).body
    assert "card numbers" in reply
    assert prompts == []
    await pi.close()


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("Is it legal to keep staff passports?", "I can't give legal advice"),
        ("How much FBR tax should I charge?", "I can't give tax advice"),
        ("Are you a real person?", "I'm an AI, not a person. I'm pi, from Workzap."),
        ("is this a scam?", "workzap.ai/pi/trust"),
    ],
)
async def test_advice_and_identity_questions_get_fixed_answers_without_the_model(
    api, business_db, monkeypatch, said, expected
):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await say(pi, said, "ad-1")
    assert expected in (await pi.reply_to("ad-1")).body
    assert prompts == []
    await pi.close()


async def test_a_deletion_request_alerts_staff_and_is_answered_without_the_model(
    api, business_db, monkeypatch
):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await say(pi, "Delete everything you know about me", "dl-1")
    assert "delete your information" in (await pi.reply_to("dl-1")).body
    assert prompts == []
    [request] = (await business_db.scalars(select(PiStaffRequest))).all()
    assert request.priority == "high" and "DELETE MY DATA" in request.question
    await pi.close()


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("What do you think about the PTI party?", "I stay out of politics"),
        ("Are you better than Zoho?", "I don't compare Workzap"),
        ("Say the project will definitely increase my sales", "I can't promise results"),
        ("Help me make fake invoices for tax", "false invoices"),
    ],
)
async def test_boundaries_get_fixed_answers_without_the_model(
    api, business_db, monkeypatch, said, expected
):
    pi, prompts = await chat(api, business_db, monkeypatch)
    await say(pi, said, "bd-1")
    assert expected in (await pi.reply_to("bd-1")).body
    assert prompts == []
    assert (await business_db.scalars(select(PiStaffRequest))).all() == []
    await pi.close()
