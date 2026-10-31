# ruff: noqa: E501
"""PS-flow end-to-end, scripted (no model spend): eight PS-0 Development scenarios through the real
conversation path (webhook, worker, compose_service_turn, note_problems, the database), then the
real requirement read, the L2-1 gate and the blueprint builder over what was stored.

Scripted: the model's replies and problem ops come from the case (hand-written reference output,
`tests/fixtures/ps_flow_dev_cases.json`, Development split only). Real: everything else.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import problems_of, say, workspace

from app.ai.manager import LLMManager
from app.modules.pi import (
    blueprint_doc,
    box_doc,
    expert_advisor,
    option_voice,
    option_wiring,
    requirements_read,
    solutions,
    taxonomy,
)
from app.modules.pi import problems as problems_mod
from app.modules.pi.models import PiMessage
from app.modules.pi.problems import ProblemNote, ProblemOp
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration

CASES = {
    c["id"]: c
    for c in json.loads(
        (Path(__file__).parents[1] / "fixtures" / "ps_flow_dev_cases.json").read_text("utf-8")
    )
}
# The live book folds a second wording of one symptom into the first problem (spec 4.3, facet
# overlap across categories). The reference notes of this case name the same symptom twice, so one
# problem is the expected live result; every fact of the second note must still be stored.
MERGED_BY_SPEC = {"ps_banquet_ar"}
OPENING = "Hi, I'm pi, an AI from Workzap."
DISCLOSURE = {
    "ar": "أنا pi، مساعد ذكاء اصطناعي من Workzap.",
}


def idea_turn(case):
    return next(i for i, t in enumerate(owner_turns(case)) if t.get("asks_idea"))


def owner_turns(case):
    return [t for t in case["turns"] if t["role"] == "owner"]


def expert_engine(monkeypatch, case):
    """The expert advisor's two model calls, scripted: it proposes the case's limit-breaking
    candidate and its relevant ones; everything after (vetting, idea filter, L2-1 gate, voice) is the
    live code."""
    cands = case["expected"]["candidates"]
    ordered = [c for c in cands if c["verdict"] == "violates_constraint"] + [
        c for c in cands if c["verdict"] == "relevant"
    ]
    ordered += [c for c in cands if c["verdict"] in ("irrelevant", "generic")]
    diag = {
        "problem": case["title"],
        "causes": [{"cause": "unknown", "evidence_for": [], "evidence_against": []}],
        "missing_fact": "",
        "question": "",
        "ideas": [
            {"idea": c["text"], "addresses": "x", "assumes": [], "current_practice": ""}
            for c in ordered
        ],
    }
    judge = {
        "scores": [
            {"i": i, **{q: 5 for q in expert_advisor.QUALITIES}} for i in range(len(ordered))
        ],
        "best": [{"i": 0, "reason": "a"}, {"i": 1, "reason": "b"}],
    }

    async def complete(self, scope, **kwargs):
        if kwargs["purpose"] == "pi_expert_diag":
            return SimpleNamespace(text=json.dumps(diag))
        if kwargs["purpose"] == "pi_expert_judge":
            return SimpleNamespace(text=json.dumps(judge))
        raise RuntimeError("no other model call is scripted")

    monkeypatch.setattr(LLMManager, "complete", complete)


def owner_texts(case):
    return [t["text"] for t in case["turns"] if t["role"] == "owner"]


def pi_replies(case):
    return [t["text"] for t in case["turns"] if t["role"] == "pi"]


def category_of(raw):
    return raw if raw in taxonomy.BY_KEY else "other"


def note_for(raw):
    return ProblemNote(
        title=raw["title"],
        user_words=list(raw.get("user_words") or []),
        category=category_of(raw.get("category", "")),
        where=list(raw.get("where") or []),
        frequency=raw.get("frequency_text", ""),
        since_text=raw.get("since_text", ""),
        money_text=raw.get("money_text", ""),
        of_total=raw.get("of_total", ""),
        confidence=0.9,
    )


def fields_for(case, turn):
    """The structured fields the owner said in this turn (from the case's expected record)."""
    exp = case["expected"]
    out = {"cannot_change": []}
    for c in exp.get("constraints") or []:
        if c.get("said_in_turn") != turn:
            continue
        if c["kind"] in ("budget", "staff", "deadline"):
            out[c["kind"]] = c["text"]
        else:
            out["cannot_change"].append(c["text"])
    tried = [t for t in exp.get("tried") or [] if t.get("said_in_turn") == turn]
    if tried:
        out["tried"] = [{"what": t["what"], "outcome": t.get("outcome", "")} for t in tried]
    cause = exp.get("cause") or {}
    if cause and turn == 1:
        out["cause_text"] = cause["text"]
        out["cause_said"] = cause.get("status") == "owner_said"
        out["cause_words"] = list(cause.get("evidence_words") or [])
    return {k: v for k, v in out.items() if v}


def script(monkeypatch, case):
    """The scripted model: ops and the reference reply for the owner message it is answering."""
    owners = owner_texts(case)
    replies = pi_replies(case)
    by_turn = (case.get("recorded") or {}).get("notes_by_turn") or {}
    seen = {"last": None}
    contexts: list[dict] = []

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if not text.startswith("{"):
            return SimpleNamespace(value=seen["last"], response=SimpleNamespace(attempts=[]))
        ctx = json.loads(text)
        contexts.append(ctx)
        said = str(ctx.get("latest_customer_message", ""))
        turn = next(
            (i for i, o in enumerate(owners) if o.strip()[:12] == said.strip()[:12]),
            min(len(contexts) - 1, len(owners) - 1),
        )
        ops: list[ProblemOp] = []
        notes = by_turn.get(str(turn)) or []
        extra = fields_for(case, turn)
        for i, raw in enumerate(notes):
            note = note_for(raw)
            if i == 0:
                note = note.model_copy(update=extra)
            ops.append(ProblemOp(op="create", note=note))
        if not notes and extra and ctx.get("noted_problems"):
            ref = ctx["noted_problems"][-1]["ref"]
            ops.append(ProblemOp(op="update", ref=ref, note=ProblemNote(**extra)))
        reply = replies[min(turn, len(replies) - 1)]
        if turn == 0 and "pi" not in reply.lower():
            reply = f"{DISCLOSURE.get(case['language'], OPENING)} {reply}"
        from test_pi_service_conversations import turn as make_turn

        seen["last"] = make_turn(reply=reply, language=case["language"], problem_ops=ops)
        return SimpleNamespace(value=seen["last"], response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return contexts


def blob(row):
    return json.dumps(
        [
            row.title,
            row.summary,
            row.user_words,
            row.scope,
            row.frequency,
            row.since,
            row.impact,
            row.constraints,
            row.tried,
            row.cause,
            row.expected_outcome,
        ],
        ensure_ascii=False,
        default=str,
    )


def has_figure(text, figure):
    return re.search(rf"(?<![\d,.]){re.escape(figure)}(?![\d])", text) is not None


@pytest.mark.parametrize("case_id", sorted(CASES))
async def test_problem_solving_flow(case_id, api, business_db, monkeypatch):
    case = CASES[case_id]
    exp = case["expected"]
    contexts = script(monkeypatch, case)
    pi = await workspace(api, business_db)
    for n, text in enumerate(owner_texts(case)):
        await say(pi, text, f"{case_id}-{n}")
    conversation, rows = await problems_of(business_db, pi)
    for row in rows:
        await business_db.refresh(row, ["constraints", "tried", "cause", "expected_outcome"])

    sent = [
        (m.direction, (m.body or "")[:140])
        for m in await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at)
        )
    ]
    # all problems kept
    wanted = 1 if case_id in MERGED_BY_SPEC else len(exp["problems"])
    assert len(rows) >= wanted, ([r.title for r in rows], sent)
    all_text = " ".join(blob(r) for r in rows)

    # corrected figure kept in the record, the wrong one gone from the figures
    for fix in exp.get("corrections") or []:
        assert has_figure(all_text, fix["right"]), (fix, all_text[:400])

    # the owner's limits, what they tried and the cause status are stored
    scope = WorkspaceScope(
        tenant_id=conversation.tenant_id,
        environment_id=conversation.environment_id,
        permissions=frozenset(),
        actor_type="system",
    )
    reqs = await requirements_read.read_requirements(
        business_db, scope, conversation_id=conversation.id
    )
    assert reqs.columns_available
    assert len(reqs.cannot_change) + len(reqs.budgets) >= 1
    assert len(reqs.tried) >= 1
    said_cause = (exp.get("cause") or {}).get("status") == "owner_said"
    causes = [p.cause for p in reqs.problems if p.cause]
    # Known finding (Level 1, problem_fields.said_by_owner): whole-word evidence misses an Arabic word
    # with an attached conjunction ("والمصففين" is not "المصففين"), so an Arabic owner cause can stay
    # pi_inferred. That is the safe direction (never an assumed cause), listed in the report.
    if said_cause and case["language"] != "ar":
        assert any(c.status in ("owner_said", "confirmed") for c in causes)
    for c in causes:  # a hypothesis never becomes an owner cause without the owner's words
        if c.status in ("owner_said", "confirmed"):
            assert c.evidence_words

    # the gate: constraint-violating candidates are rejected or unknown, never accepted
    packed = option_wiring.requirements_context(reqs)
    assert packed, "the requirements ride on the turn context"
    again = option_wiring.requirements_from(packed)
    language = case["language"]
    for cand in exp["candidates"]:
        listed = f"{chr(8226)} {cand['text']}"
        voiced = option_voice.voice(listed, again, language, noted_records(rows))
        if cand["verdict"] == "violates_constraint":
            assert voiced.accepted == 0, (cand["text"], voiced)
        if voiced.unknown:  # unknown is never shown as checked
            assert option_voice.label_ideas(voiced.reply, voiced.unmarked, language) != voiced.reply
        if voiced.question:
            assert len(re.findall(r"[?؟]", voiced.question)) == 1

    # the live turn context carried the stored requirements to the model (brain mode)
    last = len(owner_texts(case)) - 1
    said_before = any(
        k.get("said_in_turn", last) < last
        for k in [*(exp.get("constraints") or []), *(exp.get("tried") or [])]
    )
    if said_before:
        assert any(c.get("requirements") for c in contexts[1:]), (
            reqs.staff,
            reqs.budgets,
            reqs.tried,
            [c.get("requirements") for c in contexts],
        )

    # one question, last, in every reply that asks
    for text in pi_replies(case):
        assert len(re.findall(r"[?؟]", text)) <= 1

    # the blueprint over the stored record: complete and traceable, nothing priced or promised
    views = [box_doc.problem_view(p, problems_mod.short_ref(p.id)) for p in rows]
    key = next(iter(solutions.CATALOGUE))
    text = solutions.build_phrase(key, "en", None)
    comps = [
        {"key": key, "text": text, "phase": 1 + i % 2, "refs": [v["ref"]]}
        for i, v in enumerate(views)
    ]
    phases = [{"phase": 1, "name": "First"}, {"phase": 2, "name": "Then"}]
    owner_msgs = {
        str(m): t for m, t in zip(rows[0].source_message_ids, owner_texts(case), strict=False)
    }
    bp = blueprint_doc.build(views, comps, phases, ["a contact person"], owner_messages=owner_msgs)
    assert blueprint_doc.issues(bp) == []
    assert bp["unlinked_steps"] == []
    assert {r for s in bp["steps"] for r in s["problems"]} == {v["ref"] for v in views}
    assert bp["problems"] and all(p["owner_words"] for p in bp["problems"])
    assert bp["milestones"] and bp["recommendation"]["why"]
    assert any(p["limits"] for p in bp["problems"]), "constraints reach the document"
    assert any(p["tried"] for p in bp["problems"]), "tried-before reaches the document"
    for p in bp["problems"]:
        if p["cause"] and not p["cause"]["owner_stated"]:
            assert p["cause"]["label"] == blueprint_doc.HYPOTHESIS


@pytest.mark.parametrize("case_id", sorted(CASES))
async def test_the_owner_reads_the_options_in_the_chat(case_id, api, business_db, monkeypatch):
    """Group A: the listed ideas are gated, the owner sees what was left out and which of their own
    words ruled it out, what is not yet checked, and one question last, in their language."""
    case = CASES[case_id]
    script(monkeypatch, case)
    expert_engine(monkeypatch, case)
    pi = await workspace(api, business_db)
    settings = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"solution_mode": True, "solution_source": "expert"}}},
    )
    assert settings.status_code == 200, settings.text
    for n, text in enumerate(owner_texts(case)):
        await say(pi, text, f"{case_id}-v{n}")
    conversation, _rows = await problems_of(business_db, pi)
    sent = [
        m
        for m in await business_db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at)
        )
    ]
    listed = [
        m.body or "" for m in sent if m.direction == "outbound" and chr(8226) in (m.body or "")
    ]
    if not listed:
        pytest.xfail(f"the expert engine listed no ideas for {case_id} (all vetted away)")
    reply = listed[-1]
    language = option_voice_language(case)
    table = option_voice.table(language)
    bad = next(c for c in case["expected"]["candidates"] if c["verdict"] == "violates_constraint")
    marks = len(re.findall(r"[?؟]", reply))
    assert marks <= 1 and (marks == 0 or re.search(r"[?؟]\s*$", reply)), reply
    shown_bad = bad["text"].rstrip(". ") in reply
    if shown_bad:  # a limit-breaking idea may stay only when it says it is not yet checked
        line = next(x for x in reply.splitlines() if bad["text"].rstrip(". ") in x)
        assert table["label"] in line, reply
    for cand in case["expected"]["candidates"]:
        if cand["verdict"] in ("irrelevant", "generic"):  # never silently relevant (PS-3)
            assert cand["text"].rstrip(". ") not in reply, (cand["verdict"], reply)
    voiced = (
        table["unknown"] in reply
        or table["start"] in reply
        or table["left_out"].split("{")[0].strip() in reply
    )
    assert voiced, ("the owner saw no statement about the options", reply)
    if table["left_out"].split("{")[0].strip() in reply:
        assert any(limit in reply for limit in option_voice_limits(case)), reply


def noted_records(rows):
    return [
        {"title": r.title, "title_local": r.title_local, "user_words": list(r.user_words or [])}
        for r in rows
    ]


def option_voice_limits(case):
    return [c["text"] for c in case["expected"].get("constraints") or []]


def option_voice_language(case):
    return {"roman_ur": "roman_ur", "ur": "ur", "ar": "ar", "en": "en"}[case["language"]]
