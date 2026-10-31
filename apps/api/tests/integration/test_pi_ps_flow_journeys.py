"""PS-flow journeys end to end, scripted (no model spend): 32 business journeys in English, Roman
Urdu, Urdu script and Arabic through the real webhook, worker, compose_service_turn, note_problems
and the database, then the real requirement read, the L2-1 gate and the blueprint builder over
what was stored (`tests/fixtures/ps_flow_journeys.json`, built by hand, no PS-0 Held-out case).

Scripted: the model's replies and problem notes (from the journey). Real: everything else.

Behaviour the lanes have not landed yet is listed per journey by
`tests.support.ps_journey_flow.pending_components`: such a component that fails ends the journey as
an expected failure (reason in the report); the same component passing is fine. Every other
component is asserted hard, so a regression in landed behaviour fails the journey.
"""

import json
import re

import pytest
from ps_journey_harness import blob, run_journey, views_of

from app.modules.pi import option_wiring, requirements_read
from app.shared.scope import WorkspaceScope
from tests.support import ps_journey_checks as ck
from tests.support import ps_journey_flow as fl

pytestmark = pytest.mark.integration

JOURNEYS = ck.load()
OWNER = ("owner_said", "confirmed")
TRIED_ASK = re.compile(r"tried|aazmaya|try kiya|try kiye|آزمایا|آزمائ|جربتم|جربت", re.IGNORECASE)


def record_findings(journey, run, reqs):
    expect = journey["expect"]
    found: dict[str, list[str]] = {
        k: []
        for k in (
            "problems_kept",
            "record_figures",
            "record_limits",
            "record_tried",
            "record_cause",
            "replies",
            "replies_language",
            "replies_one_question",
            "replies_spelling",
            "replies_money_promise",
            "replies_repeat",
            "reply_asks_known",
        )
    }
    if len(run.rows) != expect["problems"]:
        found["problems_kept"].append(f"{len(run.rows)} stored, {expect['problems']} expected")
    text = " ".join(blob(r) for r in run.rows)
    kept, gone = ck.figures_after_corrections(journey)
    found["record_figures"] += [
        f"kept figure {f} missing" for f in kept if not ck.has_figure(text, f)
    ]
    found["record_figures"] += [
        f"old figure {f} still there: ...{ck.figure_context(text, f)}..."
        for f in gone
        if ck.has_figure(text, f)
    ]
    limits = expect.get("limits") or {}
    for key, rows in (
        ("budget", reqs.budgets),
        ("staff", reqs.staff),
        ("deadline", reqs.deadlines),
    ):
        stored = [x.text for x in rows]
        if limits.get(key) and not any(limits[key] in t for t in stored):
            found["record_limits"].append(f"{key}: {limits[key]} not in {stored}")
        if key in (limits.get("absent") or []) and stored:
            found["record_limits"].append(f"{key} was never said but {stored} is stored")
    for sub in limits.get("cannot") or []:
        if not any(sub in x.text for x in reqs.cannot_change):
            found["record_limits"].append(f"cannot-change '{sub}' missing")
    for sub in expect.get("tried") or []:
        if not any(sub in t.what for t in reqs.tried):
            found["record_tried"].append(f"tried '{sub}' missing")
    causes = [p.cause for p in reqs.problems if p.cause]
    wanted = expect.get("cause")
    if wanted:
        if not any(c.status == wanted["status"] for c in causes):
            found["record_cause"].append(f"no cause with status {wanted['status']}: {causes}")
    for c in causes:
        if c.status in OWNER and not c.evidence_words:
            found["record_cause"].append(f"owner cause without the owner's words: {c.text}")
        if not wanted and c.status in OWNER:
            found["record_cause"].append(f"pi's guess stored as the owner's: {c.text}")
    replies = run.replies
    if not replies:
        found["replies"].append("pi sent nothing")
    for n, reply in enumerate(replies):
        if not ck.language_matches(journey["language"], reply):
            found["replies_language"].append(f"{n}: {ck.detect_language(reply)}: {reply[:60]}")
        if not ck.one_question_last(reply):
            found["replies_one_question"].append(f"{n}: {reply[-80:]}")
        if journey["language"] == "en" and ck.american_spelling(reply):
            found["replies_spelling"].append(f"{n}: {ck.american_spelling(reply)}")
        if ck.money_or_promise(reply):
            found["replies_money_promise"].append(f"{n}: {reply[:80]}")
    if ck.repeated_questions(replies):
        found["replies_repeat"].append(str(ck.repeated_questions(replies)))
    # a question pi wrote itself (not the scripted one) must not ask what the record already holds
    scripted = [t["pi"] for t in journey["turns"]]
    if expect.get("tried"):
        for reply in replies:
            own = not any(s[:30] in reply for s in scripted)
            if own and TRIED_ASK.search(ck.last_question(reply)):
                found["reply_asks_known"].append(f"asks what was tried again: {reply[-70:]}")
    return found


def gate_findings_from(journey, reqs):
    packed = option_wiring.requirements_context(reqs)
    again = option_wiring.requirements_from(packed)
    found = fl.gate_findings(journey, packed)
    # every idea through the live gate in one go: unknown is labelled, a question is one question
    wired = option_wiring.gate_ideas(
        [i["text"] for i in journey["ideas"]], again, journey["language"]
    )
    found.setdefault("gate_live", [])
    for text in wired.unknown:
        if not any(option_wiring.NOT_CHECKED in s for s in wired.shown if text.rstrip(". ") in s):
            found["gate_live"].append(f"unknown shown as checked: {text[:50]}")
    if wired.question and not (wired.question.count("?") == 1 and wired.question.endswith("?")):
        found["gate_live"].append(wired.question)
    return found


def blueprint_for(journey, views, owner_messages):
    bp = fl.build_blueprint(journey, views, owner_messages)
    return views, bp


def settle(found, pending, run=None):
    """Hard-fail what is landed; end the journey as an expected failure for what is pending."""
    hard = {k: v for k, v in found.items() if v and k not in pending}
    if hard and run is not None:
        hard["_sent"] = run.replies
        hard["_problems"] = [r.title for r in run.rows]
        hard["_rewrites"] = run.rewrites
        hard["_context_requirements"] = [c.get("requirements") for c in run.contexts]
    assert not hard, json.dumps(hard, ensure_ascii=False, indent=1)
    soft = {k: pending[k] for k, v in found.items() if v and k in pending}
    if soft:
        pytest.xfail(" | ".join(f"{k}: {why}" for k, why in sorted(soft.items())))


@pytest.mark.parametrize("journey_id", [j["id"] for j in JOURNEYS])
async def test_journey_end_to_end(journey_id, api, business_db, monkeypatch):
    journey = next(j for j in JOURNEYS if j["id"] == journey_id)
    run = await run_journey(api, business_db, monkeypatch, journey)
    scope = WorkspaceScope(
        tenant_id=run.conversation.tenant_id,
        environment_id=run.conversation.environment_id,
        permissions=frozenset(),
        actor_type="system",
    )
    reqs = await requirements_read.read_requirements(
        business_db, scope, conversation_id=run.conversation.id
    )
    assert reqs.columns_available
    found = record_findings(journey, run, reqs)
    found.update(gate_findings_from(journey, reqs))
    views = views_of(run.rows)
    views, bp = blueprint_for(journey, views, run.owner_messages)
    found.update(fl.blueprint_findings(journey, bp, views))
    again = blueprint_for(journey, views, run.owner_messages)[1]
    found["deterministic"] = (
        []
        if json.dumps(bp, sort_keys=True, ensure_ascii=False)
        == json.dumps(again, sort_keys=True, ensure_ascii=False)
        else ["two runs gave different blueprints"]
    )
    found["rerank"] = []
    if journey["rerank"] and run.snapshot:
        rr = journey["rerank"]
        before = blueprint_for(journey, run.snapshot, run.owner_messages)[1]
        idea = journey["ideas"][rr["idea"]]["text"]
        if idea in [r["option"] for r in before["recommendation"]["rejected"]]:
            found["rerank"].append("rejected before the owner changed the requirement")
        if idea not in [r["option"] for r in bp["recommendation"]["rejected"]]:
            found["rerank"].append("not rejected after the owner changed the requirement")
        if fl.recommended_idea(journey, bp) == rr["idea"]:
            found["rerank"].append("the rejected idea is still the recommendation")
    # brain mode carried what the owner stated to the model on the next turn
    found["context_requirements"] = []
    if fl.requirements_data(fl.fold_record(journey)) and not any(
        c.get("requirements") for c in run.contexts[1:]
    ):
        found["context_requirements"].append("the stored limits never reached the model's context")
    settle(found, fl.pending_components(journey), run)
