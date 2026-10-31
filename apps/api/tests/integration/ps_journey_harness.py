"""Harness for the PS-flow journeys: the real webhook, worker, compose_service_turn, note_problems
and database, with a scripted model (no model spend, no network).

Copied from the pattern of the flow lead's `test_pi_ps_flow_scenarios.py` (not imported from it, so
this suite does not move when that file does). Scripted: the model's reply and problem notes for
the owner message it is answering, taken from the journey. Real: everything else.
"""

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from test_pi_brain_flow import brain_on
from test_pi_pipeline import pi_workspace
from test_pi_service_conversations import turn as make_turn

from app.ai.manager import LLMManager
from app.modules.pi import box_doc
from app.modules.pi import problems as problems_mod
from app.modules.pi.models import PiMessage
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import ProblemNote, ProblemOp
from tests.support import ps_journey_checks as ck

REWRITES: list[str] = []


@dataclass
class Run:
    pi: Any
    conversation: Any
    rows: list[Any]
    replies: list[str]
    owner_messages: dict[str, str]
    contexts: list[dict[str, Any]] = field(default_factory=list)
    rewrites: list[str] = field(default_factory=list)  # the rewrite requests pi sent the model
    snapshot: list[Any] = field(default_factory=list)  # the problems just before the rerank turn


def script(monkeypatch, journey, upto: int | None = None) -> list[dict[str, Any]]:
    """The scripted model: ops and the reference reply for the owner message it is answering."""
    owners = ck.owner_texts(journey)
    turns = journey["turns"]
    contexts: list[dict[str, Any]] = []
    seen: dict[str, Any] = {"last": None}
    rewrites = REWRITES

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if not text.startswith("{"):  # a rewrite request: send the same draft again
            rewrites.append(text[:400])
            return SimpleNamespace(value=seen["last"], response=SimpleNamespace(attempts=[]))
        ctx = json.loads(text)
        contexts.append(ctx)
        said = str(ctx.get("latest_customer_message", ""))
        n = next(
            (i for i, o in enumerate(owners) if o.strip()[:14] == said.strip()[:14]),
            min(len(contexts) - 1, len(owners) - 1),
        )
        ops: list[ProblemOp] = []
        noted = ctx.get("noted_problems") or []
        for op in turns[n]["ops"]:
            note = ProblemNote(**op["note"], confidence=0.9)
            if op["op"] == "create":
                ops.append(ProblemOp(op="create", note=note))
            elif op["problem"] < len(noted):
                ref = noted[op["problem"]]["ref"]
                ops.append(ProblemOp(op="update", ref=ref, note=note, reason=op.get("reason", "")))
        value = make_turn(reply=turns[n]["pi"], language=journey["language"], problem_ops=ops)
        seen["last"] = value
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return contexts


def views_of(rows):
    """Plain views now: the rows are live objects that a later read refreshes."""
    return [box_doc.problem_view(p, problems_mod.short_ref(p.id)) for p in rows]


async def read_rows(db, pi):
    conversation = await pi.conversation()
    await db.refresh(conversation)
    rows = list(
        await db.scalars(
            select(PiProblem)
            .where(PiProblem.customer_id == conversation.customer_id)
            .order_by(PiProblem.number)
        )
    )
    for row in rows:
        await db.refresh(row)
        await db.refresh(row, ["constraints", "tried", "cause", "expected_outcome"])
    return conversation, rows


async def run_journey(api, db, monkeypatch, journey, upto: int | None = None) -> Run:
    """Say the owner's first `upto` messages (all when None) and read back what was stored."""
    REWRITES.clear()
    contexts = script(monkeypatch, journey, upto)
    pi = await pi_workspace(api, db, business_type="service_business")
    await brain_on(api)
    snapshot: list[Any] = []
    for n, text in enumerate(ck.owner_texts(journey)):
        if upto is not None and n >= upto:
            break
        if journey["rerank"] and n == journey["rerank"]["after_turn"]:
            snapshot = views_of((await read_rows(db, pi))[1])
        await pi.process(text, f"{journey['id']}-{n}")
        await pi.deliver_all()
    conversation, rows = await read_rows(db, pi)
    messages = list(
        await db.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id)
            .order_by(PiMessage.created_at)
        )
    )
    return Run(
        pi=pi,
        conversation=conversation,
        rows=rows,
        replies=[m.body or "" for m in messages if m.direction == "outbound"],
        owner_messages={str(m.id): m.body or "" for m in messages if m.direction == "inbound"},
        contexts=contexts,
        snapshot=snapshot,
        rewrites=list(REWRITES),
    )


UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def blob(row) -> str:
    return UUID.sub("", _blob(row))


def _blob(row) -> str:
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
