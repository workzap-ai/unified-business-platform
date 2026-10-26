# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Real chats become candidate lessons: pi gives ideas, the owner says "ye kam nahi aya", and the
nightly run puts a lesson in the Teach pi review list. Never live or a canary before a person
approves it; nothing happens while learning is frozen (learning_feedback.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import learning_lessons, learning_nightly
from app.modules.pi.learning_models import PiLearningLesson
from app.modules.pi.models import PiMessage, PiSettings

pytestmark = pytest.mark.integration

IDEAS = (
    "Ji, ye do ideas abhi aazma sakte hain:\n\n"
    "• Chhoti video banayein, taake log kapra dekh sakein.\n"
    "• Purane customers ko message karein, taake wapas aayein.\n\n"
    "Kya aap in sab ke liye solution document aur quote chahenge?"
)


def model(context, n):
    said = context["latest_customer_message"]
    if "ideas do" in said:
        return turn(reply=IDEAS, language="roman_ur")
    if "stock" in said:
        return turn(
            reply="Thanks. I've noted it: stock running out. Is it every shop, or only some?",
            language="en",
            problem_ops=[create("Best-sellers run out", "stock runs out")],
        )
    return turn(reply="Noted. How often does that happen?", language="en")


async def chat(pi, db):
    """A chat where pi gave two ideas and the owner said they did not help. The ideas reply is
    stored as it would have been sent (the scripted pipeline answers a bare ask with its own line)."""
    await say(pi, "stock runs out in two shops", "il-1")
    conversation = await pi.conversation()
    now = datetime.now(UTC)
    for n, (direction, who, body) in enumerate(
        (("outbound", "ai", IDEAS), ("inbound", "customer", "ye kam nahi aya"))
    ):
        db.add(
            PiMessage(
                tenant_id=conversation.tenant_id,
                environment_id=conversation.environment_id,
                conversation_id=conversation.id,
                direction=direction,
                sender_type=who,
                body=body,
                message_type="text",
                status="processed",
                provider_message_id=f"idea-{n}",
                created_at=now - timedelta(minutes=30 - n),
            )
        )
    await db.flush()


async def test_a_reaction_to_ideas_becomes_a_lesson_that_waits_for_a_person(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await chat(pi, business_db)
    conversation = await pi.conversation()
    settings = await business_db.scalar(
        select(PiSettings).where(
            PiSettings.tenant_id == conversation.tenant_id,
            PiSettings.environment_id == conversation.environment_id,
        )
    )
    settings.response_rules = {
        **(settings.response_rules or {}),
        "brain": {"learning_frozen": False},
    }

    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.frozen is False
    counts = run.digest["idea_lessons"]
    assert counts.get("proposed") == 1 and counts.get("reacted") == 1, counts
    [lesson] = (await business_db.scalars(select(PiLearningLesson))).all()
    assert lesson.status == "review" and lesson.created_by == "nightly"  # never live by itself
    assert "did not help" in lesson.text and "chhoti video banayein" in lesson.text
    assert lesson.canary_since is None and lesson.scope.get("language") == "roman_ur"

    again = await learning_nightly.run_workspace(business_db, settings)
    assert (
        again.digest["idea_lessons"].get("proposed", 0) == 0
    )  # the same lesson is not added twice
    assert len((await business_db.scalars(select(PiLearningLesson))).all()) == 1

    live = await learning_lessons.decide(business_db, pi.scope(), lesson, True, None, "ok")
    assert live.status == "live"  # a person approves it, then it is shown to pi as reference


async def test_nothing_is_proposed_while_learning_is_frozen(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)  # frozen by default
    await chat(pi, business_db)
    settings = await business_db.scalar(select(PiSettings))
    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.frozen is True and run.digest == {"frozen": True}
    assert (await business_db.scalars(select(PiLearningLesson))).all() == []
