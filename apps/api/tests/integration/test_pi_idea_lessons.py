# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Real chats become candidate lessons: pi gives ideas, the owner says "ye kam nahi aya", and the
nightly run puts a lesson in the Teach pi review list. Never live or a canary before a person
approves it; nothing happens while learning is frozen (learning_feedback.py)."""

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_learning_loop import learning_on
from test_pi_service_conversations import turn

from app.modules.pi import learning_lessons, learning_nightly
from app.modules.pi.learning_models import PiLearningLesson
from app.modules.pi.models import PiSettings

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


async def chat(pi):
    await say(pi, "stock runs out in two shops", "il-1")
    await say(pi, "ideas do", "il-2")
    await say(pi, "ye kam nahi aya", "il-3")


async def test_a_reaction_to_ideas_becomes_a_lesson_that_waits_for_a_person(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await chat(pi)
    settings = await business_db.scalar(select(PiSettings))

    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.frozen is False
    counts = run.digest["idea_lessons"]
    assert counts["proposed"] == 1 and counts["reacted"] == 1, counts
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
    await chat(pi)
    settings = await business_db.scalar(select(PiSettings))
    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.frozen is True and run.digest == {"frozen": True}
    assert (await business_db.scalars(select(PiLearningLesson))).all() == []
