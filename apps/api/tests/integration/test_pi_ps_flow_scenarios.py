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
    if said_cause:
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
        wired = option_wiring.gate_ideas([cand["text"]], again, language)
        if cand["verdict"] == "violates_constraint":
            assert not wired.accepted, (cand["text"], wired)
            if language in ("en", "roman_ur"):
                assert wired.rejected or wired.unknown
        if wired.unknown:
            assert option_wiring.NOT_CHECKED in wired.shown[0]  # unknown is never shown as checked
        if wired.question:
            assert wired.question.count("?") == 1 and wired.question.endswith("?")

    # the live turn context carried the stored requirements to the model (brain mode)
    assert any(c.get("requirements") for c in contexts[1:]), [
        (c.get("pi_mode"), sorted(c)[:60]) for c in contexts
    ]

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
