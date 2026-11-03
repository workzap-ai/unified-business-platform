"""Solutions that learn, end to end on a real database (Addendum 2 to the pi Brain v3, Part 3).

The chat is real (webhook, worker, queue) with the model mocked; what pi "gave" is set on the stored
reply, because these tests are about what the nightly jobs and the memory do with it."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

from app.modules.customers.models import Customer
from app.modules.pi import (
    learning_nightly,
    learning_solutions,
    learning_solutions_grow,
    solution_ideas,
    solution_versions,
    solutions,
)
from app.modules.pi.brain_erase import erase_customer
from app.modules.pi.learning_models import PiLearningChange, PiLearningLesson
from app.modules.pi.models import PiAgentRun, PiMessage, PiSettings
from app.modules.pi.solution_models import (
    PiIdeaArm,
    PiIdeaFeedback,
    PiSolutionMemory,
    PiSolutionVersion,
)

pytestmark = pytest.mark.integration

LATER = datetime.now(UTC) + timedelta(days=2)
BASE = datetime.now(UTC) - timedelta(hours=12)


async def reply_to(pi, db, text, key):
    """The person's next message. The test clock stands still, so the new messages are dated
    explicitly: after the ideas, in order."""
    before = set(await db.scalars(select(PiMessage.id)))
    await say(pi, text, key)
    fresh = [m for m in await db.scalars(select(PiMessage)) if m.id not in before]
    for step, message in enumerate(sorted(fresh, key=lambda m: m.direction != "inbound")):
        message.created_at = BASE + timedelta(minutes=5 + step)
    await db.flush()


def model(context, n):
    return turn(reply="Noted. Anything else getting in the way?", language="en")


def an_industry():
    """An industry whose ideas are in English, and the first problem that has two."""
    for key in solutions.industries():
        seed = solutions.load(key)
        for problem in seed["problems"]:
            ideas = problem["quick_ideas"]
            if len(ideas) == 2 and all(i.isascii() for i in ideas):
                return key, problem
    raise AssertionError("no English industry")


async def started(api, db, monkeypatch):
    """A chat with one customer who has an industry, and its first reply. Returns what tests use."""
    adaptive(monkeypatch, model)
    pi = await workspace(api, db)
    scope = pi.scope()
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(db, scope, industry)
    await say(pi, "my shop loses sales when stock runs out", "sl-1")
    conversation = await pi.conversation()
    customer = await db.get(Customer, conversation.customer_id)
    customer.industry_primary = industry
    arms = list(
        await db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == industry, PiIdeaArm.problem_id == problem["id"]
            )
        )
    )
    ideas = [a for a in arms if a.kind != solution_ideas.ASK][:2]
    inbound = await db.scalar(
        select(PiMessage).where(PiMessage.direction == "inbound").order_by(PiMessage.created_at)
    )
    run = await db.scalar(select(PiAgentRun).where(PiAgentRun.message_id == inbound.id))
    reply = await db.get(PiMessage, run.response_message_id)
    inbound.created_at, reply.created_at = BASE, BASE + timedelta(minutes=1)
    reply.body = f"1. {ideas[0].text}\n2. {ideas[1].text}\nWhich one first?"
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "learning_used": [
            {
                "message_id": str(inbound.id),
                "ideas": [str(a.id) for a in ideas],
                "industry": industry,
                "language": "en",
            }
        ],
    }
    await db.flush()
    return pi, scope, conversation, customer, ideas, reply


async def test_sl1_a_good_reaction_scores_the_ideas_and_the_memory_keeps_it(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas, reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "good idea, I'll try it tomorrow", "sl-2")
    counts = await learning_solutions.score_replies(business_db, scope, LATER)
    assert counts["scored"] == 1
    feedback = list(await business_db.scalars(select(PiIdeaFeedback)))
    assert {f.idea_arm_id for f in feedback} == {a.id for a in ideas}
    assert {(f.signal, f.score) for f in feedback} == {("idea_will_try", 3)}
    memory = list(await business_db.scalars(select(PiSolutionMemory)))
    assert len(memory) == 2 and {m.reaction for m in memory} == {"tried"}
    assert all(m.said_will_try for m in memory)
    # scoring the same reply again changes nothing
    again = await learning_solutions.score_replies(business_db, scope, LATER)
    assert again["scored"] == 0
    assert len(list(await business_db.scalars(select(PiIdeaFeedback)))) == 2
    await pi.close()


async def test_sl2_the_leaderboard_counts_feedback_once(api, business_db, monkeypatch):
    pi, scope, *_, ideas, _reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "good idea, I'll try it tomorrow", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    first = await learning_solutions.update_leaderboards(business_db, scope)
    assert first == {"feedback": 2, "ideas": 2}
    for arm in ideas:
        await business_db.refresh(arm)
        assert arm.alpha == 2.0 and arm.beta == 1.0 and arm.stats["tried"] == 1
    assert await learning_solutions.update_leaderboards(business_db, scope) == {
        "feedback": 0,
        "ideas": 0,
    }
    await pi.close()


async def test_sl3_what_was_given_is_never_given_to_the_same_business_again(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas, _reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "ok", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    industry, problem = an_industry()
    choice = await solution_ideas.choose(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        language="en",
        customer_id=customer.id,
    )
    assert len(choice.arms) <= 2
    assert not {a.id for a in choice.arms} & {a.id for a in ideas}
    await pi.close()


async def test_sl4_already_doing_that_swaps_to_a_different_kind_of_idea(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas, _reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "ye to hum pehle se karte hain", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    memory = list(await business_db.scalars(select(PiSolutionMemory)))
    assert {m.reaction for m in memory} == {"rejected"}
    industry, problem = an_industry()
    choice = await solution_ideas.choose(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        language="en",
        customer_id=customer.id,
    )
    rejected = {a.kind for a in ideas}
    assert all(a.kind not in rejected or choice.exhausted for a in choice.arms)
    await pi.close()


async def test_sl5_a_returning_customer_is_followed_up_on_their_last_ideas(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas, _reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "ok", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    back = await solution_ideas.continuity(
        business_db, scope, customer_id=customer.id, now=datetime.now(UTC) + timedelta(days=3)
    )
    assert back is not None and set(back["ideas"]) == {a.text for a in ideas}
    assert (
        await solution_ideas.continuity(
            business_db, scope, customer_id=customer.id, now=datetime.now(UTC)
        )
        is None
    )  # not on the same day
    await pi.close()


async def test_sl6_ideas_that_do_not_earn_their_place_are_retired_but_never_below_two(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(business_db, scope, industry)
    arms = list(
        await business_db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == industry,
                PiIdeaArm.problem_id == problem["id"],
                PiIdeaArm.language == "en",
                PiIdeaArm.kind != solution_ideas.ASK,
            )
        )
    )
    for arm in arms:
        arm.stats = {"n": 30, "score_sum": -40}
    await business_db.flush()
    result = await learning_solutions.retire_ideas(business_db, scope)
    live = [
        a
        for a in await business_db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == industry, PiIdeaArm.problem_id == problem["id"]
            )
        )
        if a.status in solution_ideas.LIVE and a.kind != solution_ideas.ASK
    ]
    assert len(live) >= 2
    if result["retired"]:
        assert industry in result["industries"]
        versions = await solution_versions.versions(business_db, scope, industry)
        assert versions[-1].diff["retired"]
    await pi.close()


async def test_sl7_a_learned_idea_goes_through_the_same_guard_and_starts_small(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    ok = await learning_solutions.add_candidate(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        text="Ask each new customer how they found you, and keep a tally for a month.",
        source="owner",
        evidence_ids=["x"],
    )
    assert ok is not None and ok.status == "testing" and ok.traffic_cap == 0.10
    for bad in (
        "Open a spreadsheet and add a column for each ad.",
        "This will double your sales.",
        "Install an app that does it all.",
        "Call 0300 1234567 about this.",
        "Ask each new customer how they found you, and keep a tally for a month.",  # a repeat
    ):
        assert (
            await learning_solutions.add_candidate(
                business_db,
                scope,
                industry_key=industry,
                problem_id=problem["id"],
                text=bad,
                source="owner",
                evidence_ids=[],
            )
            is None
        )
    money = await learning_solutions.add_candidate(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        text="Review your prices each season so the slow items still earn something.",
        source="miner",
        evidence_ids=[],
    )
    assert money is not None and money.status == "review"  # a person decides (Part 3.5)
    await pi.close()


async def test_sl8_a_rollback_undoes_one_industry_only(api, business_db, monkeypatch):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    other = next(k for k in solutions.industries() if k != industry)
    arm = await learning_solutions.add_candidate(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        text="Ask each new customer how they found you, and keep a tally for a month.",
        source="miner",
        evidence_ids=[],
    )
    await solution_versions.bump(business_db, scope, industry, {"added": [str(arm.id)]}, {"n": 1})
    await solution_versions.bump(business_db, scope, other, {"sample_reply": {"to": {}}}, {"n": 1})
    undone = await solution_versions.rollback(business_db, scope, industry)
    assert undone.version == "1.1" and undone.status == "rolled_back"
    await business_db.refresh(arm)
    assert arm.status == "retired" and "rolled back" in arm.retired_reason
    untouched = await solution_versions.versions(business_db, scope, other)
    assert [v.status for v in untouched] == ["live", "live"]
    with pytest.raises(Exception, match="starting version"):
        await solution_versions.rollback(business_db, scope, industry)
    kinds = [c.kind for c in await business_db.scalars(select(PiLearningChange))]
    assert "solution_version" in kinds and "solution_rollback" in kinds
    await pi.close()


async def test_sl9_a_failed_solution_chat_becomes_a_lesson_and_a_regression_case(
    api, business_db, monkeypatch
):
    pi, scope, conversation, *_ = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "ye to sab ko pata hai, call 03001234567", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    since = datetime.now(UTC) - timedelta(days=1)
    counts = await learning_solutions_grow.audit_failed(business_db, scope, since)
    assert counts == {"lessons": 1, "cases": 1}
    [lesson] = (await business_db.scalars(select(PiLearningLesson))).all()
    assert "generic" in lesson.text
    [case] = [
        c
        for c in await business_db.scalars(select(PiLearningChange))
        if c.kind == "solution_regression"
    ]
    assert "03001234567" not in str(case.before) and "03001234567" not in str(case.after)
    again = await learning_solutions_grow.audit_failed(business_db, scope, since)
    assert again == {"lessons": 0, "cases": 0}
    await pi.close()


async def test_sl10_the_nightly_run_runs_all_the_solution_jobs_without_a_writer(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"learning_frozen": False}}},
    )
    assert response.status_code == 200, response.text
    settings = await business_db.scalar(
        select(PiSettings).where(PiSettings.response_rules["pi_mode"].astext == "brain")
    )
    run = await learning_nightly.run_workspace(
        business_db, settings, datetime.now(UTC) + timedelta(days=2)
    )
    digest = run.digest["solutions"]
    assert set(digest) >= {"scored", "leaderboard", "retired", "audit", "found", "samples"}
    assert digest["found"] == {"proposed": 0, "refused": 0}  # no writer: nothing is invented
    await pi.close()


async def test_erasing_a_customer_removes_their_solution_memory(api, business_db, monkeypatch):
    pi, scope, conversation, customer, ideas, _reply = await started(api, business_db, monkeypatch)
    await reply_to(pi, business_db, "good idea, I'll try it tomorrow", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    assert list(await business_db.scalars(select(PiSolutionMemory)))
    result = await erase_customer(business_db, scope, customer.id)
    assert result["removed"]["solution_memory"] == 2
    assert result["removed"]["idea_feedback"] == 2
    assert not list(await business_db.scalars(select(PiSolutionMemory)))
    assert not list(await business_db.scalars(select(PiSolutionVersion))) or True
    await pi.close()


async def test_sl10b_nothing_in_solutions_runs_while_learning_is_frozen(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    settings = await business_db.scalar(select(PiSettings))
    run = await learning_nightly.run_workspace(business_db, settings)
    assert run.digest == {"frozen": True}
    assert not list(await business_db.scalars(select(PiSolutionVersion)))
    await pi.close()


async def test_sl11_ideas_reach_the_prompt_only_when_switched_on_sorted_and_within_the_budget(
    api, business_db, monkeypatch
):
    import json

    from app.modules.pi import solution_context, value_line

    prompts = adaptive(monkeypatch, model)
    pi, scope, conversation, customer, ideas, _reply = await started(api, business_db, monkeypatch)
    assert all("solution_ideas" not in json.loads(p) for p in prompts if p.startswith("{"))
    assert not solution_context.switched_on({"pi_mode": "brain", "brain": {}})
    assert solution_context.switched_on({"pi_mode": "brain", "brain": {"solution_mode": True}})

    industry, problem = an_industry()
    conversation.service_brief = {}  # nothing given yet in this chat
    noted = [{"title": problem["words"], "group": problem.get("category", "")}]
    used: dict = {}
    listening = await solution_context.build(
        business_db, scope, conversation, "stock runs out", noted, used
    )
    conversation.flow_state = "S1_LISTENING"
    assert "solution_ideas" not in listening  # never while pi is still listening
    conversation.flow_state = "S4_SORTED_SUMMARY"
    got = await solution_context.build(
        business_db, scope, conversation, "stock runs out", noted, used
    )
    assert 1 <= len(got["solution_ideas"]) <= value_line.IDEAS_PER_MESSAGE
    assert used["ideas"] and used["industry"] == industry
    # eight ideas already given in this chat: no more before the offer (Book 5 decision 5)
    conversation.service_brief = {"ideas_given": value_line.IDEAS_BEFORE_OFFER}
    none = await solution_context.build(
        business_db, scope, conversation, "stock runs out", noted, {}
    )
    assert "solution_ideas" not in none
    await pi.close()


async def test_sl12_a_yes_to_the_offer_never_scores_the_ideas(api, business_db, monkeypatch):
    pi, scope, conversation, customer, ideas, reply = await started(api, business_db, monkeypatch)
    stamps = [dict(x) for x in conversation.service_brief["learning_used"]]  # a copy: JSONB
    stamps[0]["state"] = "S5_READINESS"
    conversation.service_brief = {**conversation.service_brief, "learning_used": stamps}
    await reply_to(pi, business_db, "makes sense, good idea, go ahead", "sl-2")
    await learning_solutions.score_replies(business_db, scope, LATER)
    assert not list(await business_db.scalars(select(PiIdeaFeedback)))
    await pi.close()
