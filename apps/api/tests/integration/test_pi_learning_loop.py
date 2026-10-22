"""The learning loop end to end: a good chat becomes a redacted example, goes live a day later, is
shown to a different customer, and the outcome is credited back (pi Brain spec 8.4 to 8.5)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_experiences import spread
from test_pi_service_conversations import turn

from app.modules.pi import learning_arms, learning_bank, learning_nightly
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.experience_scorer import score_new
from app.modules.pi.learning_models import (
    PiLearningChange,
    PiLearningExample,
    PiLearningRun,
    PiQuestionArm,
)
from app.modules.pi.models import PiMessage, PiSettings
from app.modules.pi.runtime import send_pi_message

pytestmark = pytest.mark.integration

SECOND = "15550000002"


def model(context, n):
    said = context["latest_customer_message"]
    hint = (context.get("question_hint") or {}).get("wording")
    if "stock runs out" in said:
        return turn(
            reply="Thanks. I've noted it: stock running out. Is it every shop, or only some?",
            language="en",
            problem_ops=[create("Best-sellers run out", "stock runs out")],
        )
    if "Only two" in said:
        return turn(reply="Noted. How often does that happen?", language="en")
    if "deliveries" in said:  # the second customer: pi follows the suggested wording
        return turn(reply=hint or "How often does that happen?", language="en")
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def deliver_everything(pi, db):
    """pi.deliver_all only sends the first conversation's replies: send every queued one."""
    queued = await db.scalars(
        select(PiMessage.id).where(PiMessage.direction == "outbound", PiMessage.status == "queued")
    )
    for message_id in list(queued):
        await send_pi_message(pi.ctx, str(message_id))


async def learning_on(api):
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"learning_frozen": False}}},
    )
    assert response.status_code == 200, response.text


async def good_chat(pi, db):
    """The first customer: a question, a rich answer, another question, another rich answer."""
    await say(pi, "stock runs out in two shops", "ll-1")
    await say(pi, "Only two of the shops, mostly on weekends when it gets very busy", "ll-2")
    await say(pi, "Every single weekend, it has been like this for months now really", "ll-3")
    await spread(db, pi, ["ll-1", "ll-2", "ll-3"])


async def test_a_good_chat_becomes_an_example_that_a_different_customer_is_shown(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await good_chat(pi, business_db)
    scope = pi.scope()

    assert await score_new(business_db) == 2  # the first two replies; the last has no outcome yet
    counts = await learning_bank.curate(business_db, scope)
    assert counts["added"] == 1  # the first reply: a rich answer, then another one
    [example] = (await business_db.scalars(select(PiLearningExample))).all()
    assert example.status == "candidate" and example.language == "en"
    assert "stock runs out" in example.person_text and "Is it every shop" in example.reply_text
    assert float(example.redaction_confidence) >= 0.98

    # A day later it goes live, and the change is logged.
    later = datetime.now(UTC) + timedelta(hours=25)
    assert (await learning_bank.activate(business_db, scope, later))["activated"] == 1
    await business_db.refresh(example)
    assert example.status == "active"
    kinds = [c.kind for c in await business_db.scalars(select(PiLearningChange))]
    assert "example_activated" in kinds

    # Another customer: the second message already sees the example and a question hint.
    await pi.process("stock runs out at my branch", "ll-4", sender=SECOND)
    await deliver_everything(pi, business_db)
    await pi.process("also the deliveries are late", "ll-5", sender=SECOND)
    await deliver_everything(pi, business_db)
    contexts = [json.loads(p) for p in prompts if p.startswith("{")]
    seen = next(
        c for c in contexts if c["latest_customer_message"] == "also the deliveries are late"
    )
    assert [e["reply"] for e in seen["learned_examples"]][0] == example.reply_text
    assert seen["question_hint"]["slot"] == "scope"
    assert "learned_examples" not in contexts[0]  # the very first message: nothing to show yet

    # The reply used the hint, so the outcome is credited to that wording and that example.
    after_a_day = datetime.now(UTC) + timedelta(hours=60)
    assert await score_new(business_db, now=after_a_day) >= 1
    credited = [e for e in await business_db.scalars(select(PiExperience)) if e.arm_id is not None]
    assert len(credited) == 1 and credited[0].example_ids == [str(example.id)]
    result = await learning_arms.learn_from(
        business_db, scope, since=after_a_day - timedelta(days=5)
    )
    assert result["arms_updated"] == 1
    arm = await business_db.get(PiQuestionArm, credited[0].arm_id)
    assert arm.uses == 1 and arm.beta == 2.0  # the answer never came: not a useful wording (yet)
    await pi.close()


async def test_nothing_is_learned_or_shown_while_learning_is_frozen(api, business_db, monkeypatch):
    prompts = adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)  # learning stays frozen: the default
    await good_chat(pi, business_db)
    await score_new(business_db)
    settings = await business_db.scalar(select(PiSettings))
    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.frozen is True and run.digest == {"frozen": True}
    assert (await business_db.scalars(select(PiLearningExample))).all() == []
    assert (await business_db.scalars(select(PiLearningChange))).all() == []
    contexts = [json.loads(p) for p in prompts if p.startswith("{")]
    assert all("learned_examples" not in c and "question_hint" not in c for c in contexts)
    await pi.close()


async def test_the_nightly_run_writes_a_digest_and_runs_once_a_day(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await good_chat(pi, business_db)
    await score_new(business_db)
    assert await learning_nightly.run_due(business_db) == 1
    [run] = (await business_db.scalars(select(PiLearningRun))).all()
    assert run.frozen is False and run.digest["examples"]["added"] == 1
    assert "health" in run.digest and "arms" in run.digest
    assert await learning_nightly.run_due(business_db) == 0  # not again within 20 hours
    tomorrow = datetime.now(UTC) + timedelta(hours=21)
    assert await learning_nightly.run_due(business_db, tomorrow) == 1
    await pi.close()


async def test_an_example_that_holds_a_name_or_a_number_is_never_made(
    api, business_db, monkeypatch
):
    def with_a_name(context, n):
        said = context["latest_customer_message"]
        if "Johar" in said:
            return turn(
                reply="Thanks. I've noted it. Is it every shop, or only some?", language="en"
            )
        return turn(reply="Noted. How often does that happen?", language="en")

    adaptive(monkeypatch, with_a_name)
    pi = await workspace(api, business_db)
    await learning_on(api)
    await say(pi, "stock runs out at the Johar Town branch", "ln-1")
    await say(pi, "Only two of the shops, mostly on weekends when it gets very busy", "ln-2")
    await say(pi, "Every single weekend, it has been like this for months now really", "ln-3")
    await spread(business_db, pi, ["ln-1", "ln-2", "ln-3"])
    await score_new(business_db)
    counts = await learning_bank.curate(business_db, pi.scope())
    assert counts["added"] == 0  # "Johar Town" in their words keeps the whole exchange out
    assert (await business_db.scalars(select(PiLearningExample))).all() == []
    await pi.close()
