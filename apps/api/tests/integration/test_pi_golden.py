"""Golden conversations from spec Part 10.1 that no other test covers (G4, G9, G14).

The simulated person sends the "Person" lines; the model is scripted with the spec's own replies,
so these tests check that the code lets the spec's wording through and keeps the state right."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."


def listening(context, n):
    said = context["latest_customer_message"]
    if "app" in said:  # G4
        return turn(
            reply=(
                "Once I've noted what's going wrong, Workzap can prepare a solution document "
                "for it, if you want one. For now, what would the app need to fix first?"
            ),
            language="en",
        )
    if "kharcha" in said:  # G9
        return turn(
            reply=(
                "Kharcha is par depend karta hai ke kya banaya jaye. Woh quote par likha hota "
                "hai, aap ke faisle se pehle, aur quote muft hai, koi charge nahi."
            ),
            language="roman_ur",
        )
    if "Best-sellers" in said:
        return turn(
            reply=f"{OPENING} Noted both. Anything else getting in the way?",
            language="en",
            problem_ops=[
                create("Best-sellers run out in two shops", "Best-sellers run out."),
                create("Cashiers late on weekends", "Cashiers come late.", "people_staff"),
            ],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_g4_a_request_for_an_app_while_describing_returns_to_listening(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g4-1")
    await say(pi, "can you make an app for this?", "g4-2")
    reply = (await pi.reply_to("g4-2")).body
    assert reply.startswith("Once I've noted what's going wrong")
    assert reply.count("?") == 1 and reply.endswith("?")
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state in ("S1_LISTENING", "S2_CLARIFYING", "S3_NOTED")
    await pi.close()


async def test_g9_a_switch_to_roman_urdu_gets_the_cost_answer_without_a_price(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g9-1")
    await say(pi, "also the delivery is late", "g9-2")
    await say(pi, "that is a lot", "g9-3")
    await say(pi, "bhai ye batao kitna kharcha hoga?", "g9-4")
    reply = (await pi.reply_to("g9-4")).body
    answer = reply.split("\n\n")[0]
    assert answer.startswith("Kharcha is par depend karta hai")
    assert "muft hai" in answer and not any(c.isdigit() for c in answer)  # R-OFFER-05: no range
    assert "Cashiers late on weekends" in reply  # then the sorted summary (spec 3.7)
    await pi.close()


async def test_g14_returning_after_forty_days_says_who_it_is_and_remembers(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, listening)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out and cashiers are late on weekends", "g14-1")
    long_ago = datetime.now(UTC) - timedelta(days=40)
    for message in (await business_db.scalars(select(PiMessage))).all():
        message.created_at = long_ago
    await business_db.flush()
    await say(pi, "hi again", "g14-2")
    reply = (await pi.reply_to("g14-2")).body
    assert reply.startswith("Hi, it's pi, the AI from Workzap. Welcome back.")
    assert "2 problems" in reply and reply.endswith("is something new going on?")
    assert reply.count("?") == 1
    await pi.close()
