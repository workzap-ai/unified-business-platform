"""Gaps closed in solutions that learn (Addendum 2, Parts 2 and 3), on a real database.

Same set-up as test_pi_solution_learning: a real chat with the model mocked, and what pi "gave" set
on the stored reply, because these tests are about what the context builder, the nightly jobs and
the stores do with it."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_solution_learning import BASE, LATER, an_industry, model, started

from app.modules.customers.models import Customer
from app.modules.pi import (
    industry_packs,
    learning_gate,
    learning_solutions,
    learning_solutions_grow,
    solution_context,
    solution_ideas,
    solution_versions,
    solutions,
)
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiMessage
from app.modules.pi.solution_models import (
    PiBuildFit,
    PiCatalogueProposal,
    PiIdeaArm,
    PiIdeaFeedback,
    PiIdeaSource,
)

pytestmark = pytest.mark.integration

MORE = [
    "Message your past customers when something new arrives, so they remember you.",
    "Ask each new customer how they found you, and keep a tally for a month.",
    "Post fresh photos of new arrivals on your Maps listing so nearby people find you.",
    "Greet every walk-in at once, because people stay where they feel noticed.",
]


def noted_of(problem):
    return [{"title": problem["words"], "group": problem.get("category", "")}]


async def more_ideas(db, scope, industry, problem_id, n=4):
    arms = []
    for text in MORE[:n]:
        arm = await learning_solutions.add_candidate(
            db,
            scope,
            industry_key=industry,
            problem_id=problem_id,
            text=text,
            source="miner",
            evidence_ids=[],
        )
        if arm is not None:
            arms.append(arm)
    return arms


def two_problems():
    """An industry with two problems, each with two plain English ideas."""
    for key in solutions.industries():
        seed = solutions.load(key)
        good = [
            p
            for p in seed["problems"]
            if len(p["quick_ideas"]) == 2 and all(i.isascii() for i in p["quick_ideas"])
        ]
        if len(good) >= 2 and good[0]["words"].isascii() and good[1]["words"].isascii():
            return key, good[0], good[1]
    raise AssertionError("no industry with two English problems")


async def say_at(pi, db, text, key, at):
    before = set(await db.scalars(select(PiMessage.id)))
    await say(pi, text, key)
    for message in await db.scalars(select(PiMessage)):
        if message.id not in before:
            message.created_at = at if message.direction == "inbound" else at + timedelta(seconds=5)
    await db.flush()


async def chat_in(api, db, monkeypatch, noted_state="S4_SORTED_SUMMARY"):
    pi, scope, conversation, customer, ideas, _reply = await started(api, db, monkeypatch)
    conversation.flow_state = noted_state
    return pi, scope, conversation, customer, ideas


# --- 1: two ideas per problem, not four -------------------------------------------------------


async def test_g1_a_second_ask_on_the_same_problem_never_hands_out_more_than_two(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, *_ = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    await more_ideas(business_db, scope, industry, problem["id"])
    conversation.service_brief = {}
    first = await solution_context.build(
        business_db, scope, conversation, "kuch batao", noted_of(problem), {}
    )
    assert len(first["solution_ideas"]) == 2
    second = await solution_context.build(
        business_db, scope, conversation, "kuch batao", noted_of(problem), {}
    )
    assert "solution_ideas" not in second and second.get("solution_exhausted")
    given = await solution_ideas.remembered(business_db, scope, customer.id, problem["id"])
    assert len(given) == 2 and conversation.service_brief["ideas_given"] == 2
    await pi.close()


# --- 2: RV-02 after a declined offer ----------------------------------------------------------


async def test_g2_after_a_declined_offer_two_more_ideas_for_a_new_problem_only(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    await say(pi, "my shop loses sales when stock runs out", "g2-1")
    conversation = await pi.conversation()
    customer = await business_db.get(Customer, conversation.customer_id)
    industry, first, second = two_problems()
    customer.industry_primary = industry
    conversation.flow_state = "S4_SORTED_SUMMARY"
    conversation.service_brief = {
        "declines": 1,
        "ideas_given": 4,
        "ideas_problems": [first["id"]],
    }
    again = await solution_context.build(
        business_db, scope, conversation, "solution do", noted_of(first), {}
    )
    assert again["solution_asked_no_ideas"] and "solution_ideas" not in again  # not a new problem
    fresh = await solution_context.build(
        business_db, scope, conversation, "solution do", noted_of(second), {}
    )
    assert 1 <= len(fresh["solution_ideas"]) <= 2
    after = conversation.service_brief
    assert after["ideas_at_decline"] == 4 and after["ideas_given"] == 4 + len(
        fresh["solution_ideas"]
    )
    more = await solution_context.build(
        business_db, scope, conversation, "solution do", noted_of(second), {}
    )
    assert "solution_ideas" not in more  # two more is all a decline buys
    await pi.close()


# --- 3: a request for a fix is never left unanswered -----------------------------------------


async def test_g3_a_request_with_no_industry_yields_a_marker_not_silence(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, *_ = await chat_in(
        api, business_db, monkeypatch, "S2_CLARIFYING"
    )
    customer.industry_primary = None
    noted = [{"title": "stock runs out every week", "group": "stock_inventory"}]
    got = await solution_context.build(business_db, scope, conversation, "solution do", noted, {})
    assert got["solution_asked_no_ideas"] is True
    assert got["solution_noted"] == ["stock runs out every week"]
    assert got["solution_why"] == "no_industry"
    brief = conversation.service_brief
    assert brief["solution_unanswered_n"] == 1 and brief["solution_unanswered"][0]["why"]
    # a plain message that asks for nothing gets no marker
    quiet = await solution_context.build(
        business_db, scope, conversation, "we sell phones", noted, {}
    )
    assert quiet == {}
    await pi.close()


async def test_g3b_a_request_with_nothing_noted_and_one_nothing_matches_are_answered_too(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, *_ = await chat_in(
        api, business_db, monkeypatch, "S2_CLARIFYING"
    )
    nothing = await solution_context.build(business_db, scope, conversation, "solution do", [], {})
    assert nothing["solution_asked_no_ideas"] and nothing["solution_why"] == "nothing_noted"
    odd = [{"title": "zebra purple xylophone quartz", "group": "nothing_like_it"}]
    got = await solution_context.build(business_db, scope, conversation, "solution do", odd, {})
    assert got["solution_asked_no_ideas"] and got["solution_why"] == "no_match"
    await pi.close()


# --- 4: the instant reaction ------------------------------------------------------------------


async def test_g4_already_doing_that_is_honoured_in_the_same_chat(api, business_db, monkeypatch):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    await more_ideas(business_db, scope, industry, problem["id"])
    said = "ye to hum pehle se karte hain"
    await say_at(pi, business_db, said, "g4-2", BASE + timedelta(minutes=5))
    got = await solution_context.build(
        business_db, scope, conversation, said, noted_of(problem), {}
    )
    stamp = conversation.service_brief["learning_used"][0]
    assert stamp["ideas_scored"] is True and stamp["reaction"] == "idea_already_doing"
    memory = await solution_ideas.remembered(business_db, scope, customer.id)
    assert {m.reaction for m in memory} == {"rejected"}
    rejected = {a.kind for a in ideas}
    if got.get("solution_ideas"):
        assert got["solution_next"] == "swap"
        fresh = await business_db.scalars(
            select(PiIdeaArm).where(PiIdeaArm.text.in_(got["solution_ideas"]))
        )
        assert all(a.kind not in rejected for a in fresh)
    # the feedback is already written, once: the nightly run does not score it again
    n = len(list(await business_db.scalars(select(PiIdeaFeedback))))
    assert n == 2
    await learning_solutions.score_replies(business_db, scope, LATER)
    assert len(list(await business_db.scalars(select(PiIdeaFeedback)))) == n
    await pi.close()


async def test_g4b_a_plain_message_keeps_the_stamp_open_and_a_late_it_worked_still_scores(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    await say_at(pi, business_db, "dekhte hain", "g4b-2", BASE + timedelta(minutes=10))
    first = await learning_solutions.score_replies(business_db, scope, BASE + timedelta(hours=8))
    assert first["waiting"] == 1 and first["scored"] == 0  # not closed by the first nightly run
    for step, text in enumerate(["kal baat karte hain", "theek hai dekhte hain"], start=3):
        await say_at(pi, business_db, text, f"g4b-{step}", BASE + timedelta(days=step))
    await say_at(
        pi, business_db, "Maps wala kaam kiya, it worked, customers aa rahe hain", "g4b-9",
        BASE + timedelta(days=6),
    )  # fmt: skip
    counts = await learning_solutions.score_replies(business_db, scope, BASE + timedelta(days=7))
    assert counts["scored"] == 1
    signals = {f.signal for f in await business_db.scalars(select(PiIdeaFeedback))}
    assert signals == {"idea_worked"}
    memory = await solution_ideas.remembered(business_db, scope, customer.id)
    assert {m.reported_result for m in memory} == {"worked"}
    await pi.close()


async def test_g4c_a_stamp_with_no_reaction_closes_after_fourteen_days(
    api, business_db, monkeypatch
):
    pi, scope, conversation, *_ = await chat_in(api, business_db, monkeypatch)
    await say_at(pi, business_db, "dekhte hain", "g4c-2", BASE + timedelta(minutes=10))
    done = await learning_solutions.score_replies(business_db, scope, BASE + timedelta(days=15))
    assert done["scored"] + done["not_given"] == 1
    await pi.close()


async def test_g4d_a_returning_customer_who_says_it_worked_gets_the_next_steps(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    await more_ideas(business_db, scope, industry, problem["id"])
    await solution_ideas.record_given(
        business_db,
        scope,
        customer_id=customer.id,
        conversation_id=None,
        arms=ideas,
        now=datetime.now(UTC) - timedelta(days=3),
    )
    back = await solution_context.build(business_db, scope, conversation, "hello", [], {})
    assert set(back["solution_followup"]["ideas"]) == {a.text for a in ideas}
    assert conversation.service_brief["solution_followup_arms"]
    said = "it worked, customers aa rahe hain"
    got = await solution_context.build(business_db, scope, conversation, said, [], {})
    memory = await solution_ideas.remembered(business_db, scope, customer.id)
    earlier = {a.id for a in ideas}
    assert {m.reported_result for m in memory if m.idea_arm_id in earlier} == {"worked"}
    assert got["solution_next"] == "worked" and got["solution_ideas"]
    assert not {a.text for a in ideas} & set(got["solution_ideas"])  # never the same ones again
    assert got.get("solution_build")  # then the Workzap line
    # heard once only
    feedback = list(await business_db.scalars(select(PiIdeaFeedback)))
    assert {f.signal for f in feedback} == {"idea_worked"} and len(feedback) == 2
    await pi.close()


async def test_g4e_not_tried_asks_once_what_got_in_the_way_and_scores_nothing(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    await solution_ideas.record_given(
        business_db,
        scope,
        customer_id=customer.id,
        conversation_id=None,
        arms=ideas,
        now=datetime.now(UTC) - timedelta(days=3),
    )
    await solution_context.build(business_db, scope, conversation, "hello", [], {})
    first = await solution_context.build(
        business_db, scope, conversation, "abhi nahi kiya, time nahi mila", [], {}
    )
    assert first == {"solution_not_tried": True}
    again = await solution_context.build(business_db, scope, conversation, "abhi nahi kiya", [], {})
    assert again == {}  # asked once, never nagged
    assert not list(await business_db.scalars(select(PiIdeaFeedback)))
    await pi.close()


async def test_g4f_it_did_not_help_flags_the_idea_for_review(api, business_db, monkeypatch):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    await more_ideas(business_db, scope, industry, problem["id"])
    await solution_ideas.record_given(
        business_db,
        scope,
        customer_id=customer.id,
        conversation_id=None,
        arms=ideas,
        now=datetime.now(UTC) - timedelta(days=3),
    )
    await solution_context.build(business_db, scope, conversation, "hello", [], {})
    got = await solution_context.build(
        business_db, scope, conversation, "we tried it and it did not help", [], {}
    )
    assert got.get("solution_next") == "swap"
    items = [
        c
        for c in await business_db.scalars(select(PiLearningChange))
        if c.kind == solution_ideas.FIT_REVIEW
    ]
    assert {c.target_id for c in items} == {a.id for a in ideas}
    assert all(c.status == "review" for c in items)
    await pi.close()


# --- 5: the gate, the promotion bar, the canary, automatic rollback ----------------------------


async def make_testing_arm(db, scope, industry, problem_id, text, *, uses, n, score_sum, alpha):
    arm = await learning_solutions.add_candidate(
        db,
        scope,
        industry_key=industry,
        problem_id=problem_id,
        text=text,
        source="miner",
        evidence_ids=[],
    )
    assert arm is not None and arm.status == "testing" and arm.traffic_cap == 0.10
    arm.uses, arm.stats, arm.alpha = uses, {"n": n, "score_sum": score_sum}, alpha
    await db.flush()
    return arm


async def test_g5_promotion_needs_a_non_negative_score_and_the_best_live_rate(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(business_db, scope, industry)
    peer = (
        await business_db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == industry,
                PiIdeaArm.problem_id == problem["id"],
                PiIdeaArm.kind != solution_ideas.ASK,
            )
        )
    ).first()
    peer.stats, peer.alpha = {"n": 10, "score_sum": 25}, 9.0  # a live idea at 80%
    low = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[0], uses=60, n=10, score_sum=-3, alpha=2.0
    )
    slow = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[1], uses=60, n=10, score_sum=20, alpha=4.0
    )
    good = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[2], uses=60, n=10, score_sum=30, alpha=9.5
    )
    young = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[3], uses=10, n=2, score_sum=6, alpha=3.0
    )
    mine = {low.id, slow.id, good.id, young.id}
    view = {
        r["id"]: r["decision"]
        for r in await learning_solutions.canary_view(business_db, scope)
        if r["id"] in mine  # the industry's shipped extra ideas are in testing too
    }
    assert view == {
        low.id: "hold",
        slow.id: "hold",
        good.id: "promote",
        young.id: "watching",
    }
    assert await learning_solutions.promote_ideas(business_db, scope) == {"promoted": 1, "held": 2}
    for arm in (low, slow, young):
        await business_db.refresh(arm)
        assert arm.status == "testing" and arm.traffic_cap == 0.10
    await business_db.refresh(good)
    assert good.status == "active" and good.traffic_cap == 1.0
    await pi.close()


async def test_g5b_a_failed_release_gate_stops_promotion_shadow_and_version_bumps(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    good = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[2], uses=60, n=10, score_sum=30, alpha=9.5
    )
    shadow = PiIdeaArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        arm_key=f"{industry}:L1:q1",
        industry_key=industry,
        problem_id="L1",
        language="en",
        text=MORE[3],
        kind="other",
        status="shadow",
        traffic_cap=0.10,
        source="miner",
    )
    business_db.add(shadow)
    await business_db.flush()
    await solution_versions.bump(
        business_db,
        scope,
        industry,
        {"add_problem": {"id": "L1", "words": "stock runs out", "arm_ids": [str(shadow.id)]}},
        {},
        status="shadow",
    )
    versions_before = len(await solution_versions.versions(business_db, scope, industry))
    await learning_gate.record(
        business_db, scope, learning_gate.GateResult(False, ["mean 1.2"], conversations=5)
    )
    later = datetime.now(UTC) + timedelta(days=9)
    digest = await learning_solutions_grow.run_all(business_db, scope, BASE, later, None)
    assert digest["gate"] == "held" and digest["canary"]["held"] and digest["grown"]["held"]
    await business_db.refresh(good)
    await business_db.refresh(shadow)
    assert good.status == "testing" and shadow.status == "shadow"
    assert len(await solution_versions.versions(business_db, scope, industry)) == versions_before
    # the gate passes again: the idea is promoted and the shadow entry goes live
    await learning_gate.record(business_db, scope, learning_gate.GateResult(True))
    digest = await learning_solutions_grow.run_all(business_db, scope, BASE, later, None)
    assert digest["gate"] == "open" and digest["canary"]["promoted"] == 1
    await business_db.refresh(good)
    await business_db.refresh(shadow)
    assert good.status == "active" and shadow.status == "testing"
    live = [
        v
        for v in await solution_versions.versions(business_db, scope, industry)
        if v.status == "live"
    ]
    assert any((v.diff or {}).get("add_problem") and v.evidence.get("live_at") for v in live)
    await pi.close()


async def test_g5c_a_learned_version_that_scores_worse_than_the_seed_rolls_back_by_itself(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(business_db, scope, industry)
    seeds = list(
        await business_db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == industry,
                PiIdeaArm.problem_id == problem["id"],
                PiIdeaArm.source == "seed",
            )
        )
    )
    for arm in seeds:
        arm.stats = {"n": 10, "score_sum": 20}
    bad = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[0], uses=50, n=10, score_sum=-8, alpha=1.0
    )
    fine = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[1], uses=50, n=10, score_sum=30, alpha=9.0
    )
    await solution_versions.bump(business_db, scope, industry, {"added": [str(bad.id)]}, {})
    await solution_versions.bump(business_db, scope, industry, {"added": [str(fine.id)]}, {})
    young = await make_testing_arm(
        business_db, scope, industry, problem["id"], MORE[2], uses=5, n=1, score_sum=-2, alpha=1.0
    )
    await solution_versions.bump(business_db, scope, industry, {"added": [str(young.id)]}, {})
    result = await learning_solutions.evaluate_versions(business_db, scope)
    assert result == {"rolled_back": [f"{industry}@1.1"]}
    for arm, status in ((bad, "retired"), (fine, "testing"), (young, "testing")):
        await business_db.refresh(arm)
        assert arm.status == status
    versions = {
        v.version: v.status for v in await solution_versions.versions(business_db, scope, industry)
    }
    assert versions == {"1.0": "live", "1.1": "rolled_back", "1.2": "live", "1.3": "live"}
    kinds = [c.kind for c in await business_db.scalars(select(PiLearningChange))]
    assert "solution_auto_rollback" in kinds
    await pi.close()


# --- 6: owner, document and neighbour ideas ---------------------------------------------------


async def test_g6_a_reviewer_submits_an_owner_idea_through_the_route_and_the_guard(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    industry, problem = an_industry()
    url = "/api/v1/pi/solutions/ideas"
    good = await api.post(
        url,
        json={
            "industry": industry,
            "problem_id": problem["id"],
            "text": MORE[0],
            "source": "owner",
        },
    )
    assert good.status_code == 200, good.text
    body = good.json()
    assert body["accepted"] is True and body["status"] == "testing" and body["traffic_cap"] == 0.1
    assert body["source"] == "owner"
    arm = await business_db.get(PiIdeaArm, __import__("uuid").UUID(body["id"]))
    source = await business_db.scalar(
        select(PiIdeaSource).where(PiIdeaSource.idea_arm_id == arm.id)
    )
    assert source.source == "owner" and source.redaction_confidence >= 0.98
    versions = await solution_versions.versions(business_db, pi.scope(), industry)
    assert versions[-1].diff == {"added": [str(arm.id)]}
    for bad in (
        "Open a spreadsheet and add a column for each ad.",
        "Install an app that does it all.",
        "This will double your sales.",
        "Call 0300 1234567 about this.",
        MORE[0],  # a repeat
    ):
        refused = await api.post(
            url, json={"industry": industry, "problem_id": problem["id"], "text": bad}
        )
        assert refused.status_code == 200 and refused.json()["accepted"] is False, bad
        assert refused.json()["reasons"]
    unknown = await api.post(
        url, json={"industry": industry, "problem_id": "nope", "text": MORE[1]}
    )
    assert unknown.json()["accepted"] is False
    wrong = await api.post(
        url,
        json={
            "industry": industry,
            "problem_id": problem["id"],
            "text": MORE[1],
            "source": "miner",
        },
    )
    assert wrong.status_code == 422
    await pi.close()


async def test_g6b_a_document_line_and_a_neighbours_best_idea_enter_the_same_way(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    arm, why = await learning_solutions_grow.add_human_idea(
        business_db,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        text=MORE[1],
        source="document",
    )
    assert arm is not None and arm.source == "document" and arm.status == "testing" and not why
    # neighbours: the same sector, a similar problem
    sector = {}
    for key, pack in industry_packs.load_packs().items():
        if solutions.load(key):
            sector.setdefault(industry_packs.sector_key(pack), []).append(key)
    found = None
    for members in sector.values():
        for a in members:
            for mine in solutions.load(a)["problems"]:
                for b in members:
                    match = (
                        solution_ideas.match_problem(
                            solutions.load(b)["problems"],
                            mine.get("category", ""),
                            mine.get("subtype", ""),
                            mine.get("words", ""),
                        )
                        if b != a
                        else None
                    )
                    if match and all(i.isascii() for i in mine["quick_ideas"]):
                        found = (a, mine, b, match)
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
    assert found, "no neighbouring industries with a matching problem"
    a, mine, b, match = found
    await solution_ideas.ensure_arms(business_db, scope, a)
    star = (
        await business_db.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.industry_key == a,
                PiIdeaArm.problem_id == mine["id"],
                PiIdeaArm.kind != solution_ideas.ASK,
                PiIdeaArm.status == "active",
            )
        )
    ).first()
    assert star is not None
    star.stats = {"n": 30, "score_sum": 60}
    await business_db.flush()
    result = await learning_solutions_grow.neighbour_ideas(business_db, scope)
    assert result["proposed"] >= 1
    tried = list(
        await business_db.scalars(
            select(PiIdeaArm).where(PiIdeaArm.source == "neighbour", PiIdeaArm.text == star.text)
        )
    )
    assert tried and all(t.status in ("testing", "review") and t.traffic_cap == 0.10 for t in tried)
    assert all(t.industry_key != a for t in tried)
    evidence = await business_db.scalar(
        select(PiIdeaSource).where(PiIdeaSource.idea_arm_id == tried[0].id)
    )
    assert evidence.evidence_ids == [str(star.id)]
    await pi.close()


# --- 7: sample replies and the example bank ---------------------------------------------------


async def test_g7_seed_samples_enter_the_bank_through_the_gate_and_rollback_undoes_a_replacement(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    ready = [
        k
        for k in solutions.industries()
        if learning_solutions_grow.fit_for_bank(
            solutions.load(k)["sample_reply"]["person"], solutions.load(k)["sample_reply"]["pi"]
        )[0]
    ]
    assert ready
    industry = ready[0]
    refused = next(k for k in solutions.industries() if k not in ready)
    first = await learning_solutions_grow.seed_samples(business_db, scope, {industry, refused})
    assert first == {"added": 1, "rejected": 1, "there": 0}
    again = await learning_solutions_grow.seed_samples(business_db, scope, {industry, refused})
    assert again == {"added": 0, "rejected": 1, "there": 1}
    [row] = await solution_versions.sample_examples(business_db, scope, industry)
    assert row.status == "candidate" and row.source == "solution_sample"
    assert "solution document" not in row.reply_text  # the offer is the application's, not learned
    # a replacement is fed the same way, the old one leaves, and a rollback undoes both
    other = next(k for k in ready[1:]) if len(ready) > 1 else industry
    new = solutions.load(other)["sample_reply"]
    current = await solution_versions.current_sample(business_db, scope, industry) or {}
    swapped = await learning_solutions_grow.feed_sample(
        business_db, scope, industry, new["person"], new["pi"], "en", "solution_learned"
    )
    assert swapped == "added"
    await solution_versions.bump(
        business_db,
        scope,
        industry,
        {"sample_reply": {"from": current, "to": {"person": new["person"], "pi": new["pi"]}}},
        {},
    )
    await solution_versions.rollback(business_db, scope, industry)
    states = {
        r.source: r.status
        for r in await solution_versions.sample_examples(business_db, scope, industry)
    }
    assert states["solution_learned"] == "retired"
    assert (await solution_versions.current_sample(business_db, scope, industry)) == current
    await pi.close()


# --- 8: drafted entries and their probation ---------------------------------------------------


async def test_g8_a_drafted_entry_goes_live_on_probation_and_is_taken_back_when_worse(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(business_db, scope, industry)
    seeds = list(
        await business_db.scalars(
            select(PiIdeaArm).where(PiIdeaArm.industry_key == industry, PiIdeaArm.source == "seed")
        )
    )
    for arm in seeds:
        arm.stats = {"n": 10, "score_sum": 20}
    drafted = []
    for i, text in enumerate(MORE[:2], start=1):
        arm = PiIdeaArm(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            arm_key=f"{industry}:L1:q{i}",
            industry_key=industry,
            problem_id="L1",
            language="en",
            text=text,
            kind="other",
            status="shadow",
            traffic_cap=0.10,
            source="miner",
        )
        business_db.add(arm)
        drafted.append(arm)
    await business_db.flush()
    entry = {
        "id": "L1",
        "words": "stock runs out",
        "arm_ids": [str(a.id) for a in drafted],
        "workzap_build": {"keys": ["stock_alerts"], "text": "x"},
        "ask_first": "Which item runs out most often?",
        "free_stops": "Who is told, and when, is in the solution document.",
    }
    await solution_versions.bump(
        business_db, scope, industry, {"add_problem": entry}, {}, status="shadow"
    )
    assert (
        await learning_solutions_grow.promote_shadows(
            business_db, scope, datetime.now(UTC) + timedelta(days=8)
        )
        == 1
    )
    learned = await solution_ideas.learned_problems(business_db, scope, industry)
    assert learned[0]["workzap_build"]["keys"] == ["stock_alerts"] and learned[0]["state"] == "live"
    for arm in drafted:
        arm.uses, arm.stats = 30, {"n": 10, "score_sum": -9}
    result = await learning_solutions.evaluate_versions(business_db, scope)
    assert result["rolled_back"] == [f"{industry}@1.1"]
    assert not await solution_ideas.learned_problems(business_db, scope, industry)
    await pi.close()


# --- 9: regression replay and the extra triggers -----------------------------------------------


async def test_g9_the_gate_replays_regression_cases_and_a_slip_fails_it(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    scope = pi.scope()
    business_db.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="solution_regression",
            risk="low",
            before={
                "person": "stock problem, koi hal?",
                "pi": "Please send me your card number and OTP so I can sort it.",
            },
            after={"signal": "request_unanswered", "industry": "x"},
            status="live",
        )
    )
    await business_db.flush()
    first = await learning_gate.replay_regressions(business_db, scope)
    assert first["cases"] == 1 and first["caught"] == 1 and first["slipped"] == []
    [case] = [
        c
        for c in await business_db.scalars(select(PiLearningChange))
        if c.kind == "solution_regression"
    ]
    assert case.after["replay"]["caught"] is True and case.after["replay"]["rules"]
    # the same case stops being caught: it must show as slipped and fail the gate
    case.before = {**case.before, "pi": "Noted. I can help with that."}
    result = await learning_gate.replay(business_db, scope)
    assert result.regressions["slipped"] == [str(case.id)] and result.ok is False
    assert "regression" in " ".join(result.reasons)
    assert result.as_dict()["regressions"]["cases"] == 1
    await pi.close()


async def test_g9b_an_unanswered_request_and_two_rejections_are_audited(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    await say_at(pi, business_db, "solution do", "g9b-2", BASE + timedelta(minutes=10))
    conversation.service_brief = {
        **conversation.service_brief,
        "solution_unanswered": [{"industry": "x", "why": "no_match", "at": BASE.isoformat()}],
    }
    since = datetime.now(UTC) - timedelta(days=1)
    counts = await learning_solutions_grow.audit_failed(business_db, scope, since)
    assert counts == {"lessons": 1, "cases": 1}
    cases = [
        c
        for c in await business_db.scalars(select(PiLearningChange))
        if c.kind == "solution_regression"
    ]
    assert [c.after["signal"] for c in cases] == ["request_unanswered"]
    assert await learning_solutions_grow.audit_failed(business_db, scope, since) == {
        "lessons": 0,
        "cases": 0,
    }
    # two rejected ideas in one chat
    stamps = [dict(s) for s in conversation.service_brief["learning_used"]]
    stamps[0]["reaction"] = "idea_already_doing"
    stamps.append({**stamps[0], "reaction": "idea_not_possible"})
    conversation.service_brief = {**conversation.service_brief, "learning_used": stamps}
    twice = await learning_solutions_grow.audit_failed(business_db, scope, since)
    assert twice == {"lessons": 1, "cases": 1}
    await pi.close()


# --- 10: weekly review items and build fit ------------------------------------------------------


async def test_g10_three_businesses_with_one_unmet_need_make_a_catalogue_proposal(
    api, business_db, monkeypatch
):
    pi, scope, conversation, *_ = await chat_in(api, business_db, monkeypatch)
    stamps = [
        {"unmatched": "customers ask for a delivery tracker", "industry": ind, "customer": who}
        for ind, who in (("a_shop", "c1"), ("a_clinic", "c2"), ("a_shop", "c3"))
    ] + [{"unmatched": "only two ask for this", "industry": "a_shop", "customer": "c1"}]
    conversation.service_brief = {**conversation.service_brief, "learning_used": stamps}
    conversation.last_message_at = datetime.now(UTC)
    counts = await learning_solutions_grow.propose_catalogue(business_db, scope, datetime.now(UTC))
    assert counts == {"proposed": 1, "updated": 0}
    [proposal] = await business_db.scalars(select(PiCatalogueProposal))
    assert proposal.need_text == "customers ask for a delivery tracker"
    assert proposal.count == 3 and proposal.industries == ["a_clinic", "a_shop"]
    assert (await learning_solutions_grow.propose_catalogue(business_db, scope, datetime.now(UTC)))[
        "proposed"
    ] == 0
    await pi.close()


async def test_g10b_two_owners_saying_it_did_not_help_makes_a_review_item(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    second = Customer(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        name="Another owner",
        phone="+923001110002",
    )
    business_db.add(second)
    await business_db.flush()
    for who in (customer, second):
        business_db.add(
            PiIdeaFeedback(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                idea_arm_id=ideas[0].id,
                customer_id=who.id,
                industry_key=ideas[0].industry_key,
                language="en",
                signal="idea_no_help",
                score=-2,
            )
        )
        await business_db.flush()
        if who is customer:
            assert (await learning_solutions.flag_unhelpful(business_db, scope))["flagged"] == 0
    assert (await learning_solutions.flag_unhelpful(business_db, scope))["flagged"] == 1
    assert (await learning_solutions.flag_unhelpful(business_db, scope))["flagged"] == 0
    review = await api.get("/api/v1/pi/solutions/review")
    assert review.status_code == 200
    [item] = review.json()["fit_reviews"]
    assert item["owners"] == 2 and item["idea"] == str(ideas[0].id)
    decided = await api.post(
        f"/api/v1/pi/solutions/fit-reviews/{item['id']}/decide",
        json={"approve": False, "reason": "wrong fit"},
    )
    assert decided.status_code == 200 and decided.json()["status"] == "rejected"
    await business_db.refresh(ideas[0])
    assert ideas[0].status == "retired"
    await pi.close()


async def test_g10c_build_fit_is_recorded_from_projects_and_confirmed_by_a_reviewer(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    await solution_ideas.record_given(
        business_db,
        scope,
        customer_id=customer.id,
        conversation_id=conversation.id,
        arms=ideas,
        now=datetime.now(UTC),
    )
    keys = (problem.get("workzap_build") or {}).get("keys") or []
    assert keys
    row = await learning_solutions_grow.record_build_fit(
        business_db, scope, customer_id=customer.id, event="document_approved"
    )
    assert row is not None and row.catalogue_key == keys[0] and row.outcome == "doc_approved"
    assert row.confirmed_by is None
    same = await learning_solutions_grow.record_build_fit(
        business_db, scope, customer_id=customer.id, event="quote_accepted"
    )
    assert same is not None and same.id == row.id and same.outcome == "accepted"
    assert (
        await learning_solutions_grow.record_build_fit(
            business_db, scope, customer_id=customer.id, event="unknown_event"
        )
        is None
    )
    listed = await api.get("/api/v1/pi/solutions/build-fit", params={"confirmed": False})
    assert [i["id"] for i in listed.json()["items"]] == [str(row.id)]
    done = await api.post(
        f"/api/v1/pi/solutions/build-fit/{row.id}/confirm", json={"approve": True}
    )
    assert done.status_code == 200 and done.json()["confirmed"] is True
    again = await api.post(
        f"/api/v1/pi/solutions/build-fit/{row.id}/confirm", json={"approve": True}
    )
    assert again.status_code == 404  # decided once
    # it fed nothing into the idea feedback
    assert not list(await business_db.scalars(select(PiIdeaFeedback)))
    assert len(list(await business_db.scalars(select(PiBuildFit)))) == 1
    await pi.close()


# --- 11: builds mentioned and the metrics --------------------------------------------------------


async def test_g11_builds_named_in_the_reply_are_kept_in_solution_memory(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    conversation.service_brief = {}
    got = await solution_context.build(
        business_db, scope, conversation, "solution do", noted_of(problem), {}
    )
    assert got.get("solution_build")
    memory = await solution_ideas.remembered(business_db, scope, customer.id, problem["id"])
    assert memory and all(
        m.builds_mentioned == [problem["workzap_build"]["keys"][0]] for m in memory
    )
    await pi.close()


async def test_g11b_the_metrics_route_reports_rates_counts_and_unanswered_requests(
    api, business_db, monkeypatch
):
    pi, scope, conversation, customer, ideas = await chat_in(api, business_db, monkeypatch)
    industry, problem = an_industry()
    for signal, score in (
        ("idea_will_try", 3),
        ("idea_generic", -3),
        ("idea_already_doing", -1),
        ("idea_no_help", -2),
    ):
        business_db.add(
            PiIdeaFeedback(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                idea_arm_id=ideas[0].id,
                customer_id=customer.id,
                industry_key=industry,
                language="en",
                signal=signal,
                score=score,
            )
        )
    await solution_ideas.record_given(
        business_db,
        scope,
        customer_id=customer.id,
        conversation_id=conversation.id,
        arms=ideas,
        now=datetime.now(UTC),
    )
    conversation.service_brief = {
        **conversation.service_brief,
        "solution_unanswered": [{"industry": industry, "why": "no_match"}],
    }
    await more_ideas(business_db, scope, industry, problem["id"], 1)
    await business_db.flush()
    response = await api.get("/api/v1/pi/solutions/metrics")
    assert response.status_code == 200, response.text
    body = response.json()
    mine = body["industries"][industry]
    assert mine["feedback"] == 4 and mine["engagement_rate"] == 0.25
    assert mine["generic_rate"] == 0.25 and mine["already_tried_rate"] == 0.25
    assert mine["no_help_rate"] == 0.25 and mine["requests_unanswered"] == 1
    assert mine["ideas_per_conversation"] == 2.0 and mine["ideas_added"] == 1
    assert body["overall"]["feedback"] == 4 and body["overall"]["requests_unanswered"] == 1
    assert "offer" not in str(body)
    one = await api.get("/api/v1/pi/solutions/metrics", params={"industry": industry})
    assert set(one.json()["industries"]) == {industry}
    canary = await api.get("/api/v1/pi/solutions/canary")
    assert canary.status_code == 200 and canary.json()["items"][0]["traffic"] == 0.1
    await pi.close()


async def test_g12_the_nightly_run_reports_the_new_steps(api, business_db, monkeypatch):
    from app.modules.pi import learning_nightly
    from app.modules.pi.models import PiSettings

    adaptive(monkeypatch, model)
    pi = await workspace(api, business_db)
    response = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"brain": {"learning_frozen": False}}}
    )
    assert response.status_code == 200, response.text
    settings = await business_db.scalar(
        select(PiSettings).where(PiSettings.response_rules["pi_mode"].astext == "brain")
    )
    run = await learning_nightly.run_workspace(
        business_db, settings, datetime.now(UTC) + timedelta(days=2)
    )
    digest = run.digest["solutions"]
    assert set(digest) >= {
        "gate", "canary", "auto_rollback", "neighbours", "sample_seeds", "review",
    }  # fmt: skip
    assert digest["gate"] == "open"
    await pi.close()
