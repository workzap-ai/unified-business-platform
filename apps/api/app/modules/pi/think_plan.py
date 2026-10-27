"""The plan object of the thinking step on the wire (Engagement Engine, Book 5, spec 3.2 and 11.2).

With `response_rules.brain.thinking` on, the brain turn carries a small `move_plan`: the move,
a one-line reason, whether the reply asks a question, and an optional hypothesis update. This module
holds the output schema, the validation (`moves.check_plan` plus agreement with the written reply),
the rewrite instruction, and the two stores: `pi_move_log` (one row per pi message) and
`pi_hypotheses` (the ledger). Nothing here is read when thinking is off. The plan is internal and is
never sent to the owner; a plan that is still wrong after the rewrite is replaced by the code's own
suggestion before anything is stored.
"""

import logging
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import hypothesis_reply, moves, think_lint, think_prompt
from app.modules.pi import problems as problem_records
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

MAX_RECENT = 6  # earlier moves fed back into the context for the variety checks


class HypothesisUpdate(BaseModel):
    """What this message does to the ledger. `none` is the usual answer. pi never confirms."""

    action: Literal["none", "add", "against", "drop"] = "none"
    text: str = Field(default="", max_length=300)
    confidence: Literal["low", "medium", "high"] = "low"
    evidence: str = Field(default="", max_length=300)
    test: str = Field(default="", max_length=300)


class MovePlan(BaseModel):
    """The model's plan for this message (internal, English, never shown to the owner)."""

    move: str = Field(default="", max_length=300)
    reason: str = Field(default="", max_length=300)
    asks_question: bool = False
    hypothesis: HypothesisUpdate = Field(default_factory=HypothesisUpdate)

    @field_validator("hypothesis", mode="before")
    @classmethod
    def _tolerate_hypothesis(cls, value: Any) -> Any:
        """A malformed hypothesis update is cut or ignored, never a parse failure."""
        if isinstance(value, HypothesisUpdate):
            return value
        if not isinstance(value, dict):
            return {}
        if value.get("action") not in ("none", "add", "against", "drop"):
            return {}
        out = {
            k: (str(v)[:300] if k in ("text", "evidence", "test") else v) for k, v in value.items()
        }
        if out.get("confidence") not in ("low", "medium", "high"):
            out["confidence"] = "low"
        return out

    @field_validator("move", "reason", mode="before")
    @classmethod
    def _clip(cls, value: Any) -> Any:
        return str(value)[:300] if value is not None else ""


MOVE_KEYS_TEXT = think_prompt.MOVE_KEYS_TEXT


def ends_in_question(reply: str) -> bool:
    return think_lint.ends_in_question(reply)


def problems(plan: MovePlan, reply: str, context: dict[str, Any]) -> list[str]:
    """What is wrong with the plan (empty: it can be followed). Deterministic, no model."""
    out: list[str] = []
    asked = ends_in_question(reply)
    built = moves.Plan(
        move=plan.move,
        one_line_reason=plan.reason,
        ask=moves.Ask(text=reply.strip()[-200:]) if plan.asks_question else None,
    )
    out.extend(moves.check_plan(built, think_prompt.suggested(context)))
    if not plan.reason.strip():
        out.append("the plan has no reason")
    if plan.asks_question != asked:
        out.append(
            "asks_question says "
            + ("true" if plan.asks_question else "false")
            + " but the reply "
            + ("ends in a question" if asked else "does not end in a question")
        )
    move = moves.parse_move(plan.move)
    if move is not None and moves.question_free(move) and asked:
        out.append(f"the move {move.value} carries no question, but the reply asks one")
    h = plan.hypothesis
    if h.action in ("add", "against", "drop") and not h.text.strip():
        out.append("the hypothesis update names no hypothesis")
    return out


def instruction(found: list[str]) -> str:
    """The rewrite request for a bad plan (joined to the other problems by the caller)."""
    return (
        "your move_plan is not valid: "
        + "; ".join(found)
        + f". Fill move_plan again with a valid move key from [{MOVE_KEYS_TEXT}], a one-line "
        "reason, asks_question matching whether the reply ends in a question, and write the reply "
        "to match that move"
    )


def fallback(context: dict[str, Any], reply: str) -> MovePlan:
    """A plan the code can stand behind, used when the model's stayed wrong after the rewrite: the
    suggested move, and asks_question as the reply really is. Never the model's bad plan."""
    choice = think_prompt.suggested(context)
    return MovePlan(
        move=choice.move.value if choice is not None else moves.Move.M1.value,
        reason=("code fallback: " + (choice.reason if choice is not None else "no suggestion"))[
            :300
        ],
        asks_question=ends_in_question(reply),
    )


def settle(plan: MovePlan, reply: str, context: dict[str, Any]) -> tuple[MovePlan, list[str]]:
    """The plan to keep and what was wrong with the model's: a bad plan becomes the fallback."""
    found = problems(plan, reply, context)
    if not found:
        return plan, []
    return fallback(context, reply), found


def current_move(plan: MovePlan) -> dict[str, Any]:
    """The `plan` key the think-lint move-repeat check reads (spec 3.9)."""
    parsed = moves.parse_move(plan.move)
    return {"move": parsed.value} if parsed is not None else {}


# --- stores --------------------------------------------------------------------------------


async def recent(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, limit: int = MAX_RECENT
) -> dict[str, str]:
    """message id (text) -> move, for the latest messages of the chat, oldest dropped first."""
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiMoveLog, scope)
            .select()
            .where(PiMoveLog.conversation_id == conversation_id, PiMoveLog.message_id.is_not(None))
            .order_by(PiMoveLog.created_at.desc(), PiMoveLog.id.desc())
            .limit(limit)
        )
    )
    return {str(r.message_id): r.move for r in rows}


async def recent_safely(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> dict[str, str]:
    """`recent`, but a missing table (migration not applied yet) only means no earlier moves."""
    try:
        async with session.begin_nested():
            return await recent(session, scope, conversation_id)
    except DBAPIError:
        return {}


async def record(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    message_id: UUID | None,
    plan: MovePlan,
    reply: str,
) -> None:
    """One move_log row for the pi message, and the hypothesis update applied to the ledger. A move
    the code does not know is never stored."""
    move = moves.parse_move(plan.move)
    if move is None:
        return
    session.add(
        PiMoveLog(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            conversation_id=conversation_id,
            message_id=message_id,
            move=move.value,
            reason=problem_records.redact(plan.reason)[0][:300],
            had_question=ends_in_question(reply),
        )
    )
    await apply_hypothesis(session, scope, conversation_id, plan.hypothesis)
    await session.flush()


async def ledger(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> tuple[moves.HypothesisLedger, dict[int, PiHypothesis]]:
    """The conversation's ledger, and the row behind each entry (by position)."""
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiHypothesis, scope)
            .select()
            .where(PiHypothesis.conversation_id == conversation_id)
            .order_by(PiHypothesis.created_at, PiHypothesis.id)
        )
    )
    book = moves.HypothesisLedger()
    by_index: dict[int, PiHypothesis] = {}
    for row in rows:
        book.items.append(
            moves.Hypothesis(
                text=row.text,
                evidence_for=[str(e) for e in row.evidence_for or []],
                evidence_against=[str(e) for e in row.evidence_against or []],
                confidence=moves.Confidence(row.confidence),
                cheapest_test=row.cheapest_test,
                status=moves.Status(row.status),
                ignored=row.ignored,
            )
        )
        by_index[len(book.items) - 1] = row
    return book, by_index


async def apply_hypothesis(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, update: HypothesisUpdate
) -> None:
    """add / against / drop through the ledger rules (the confirmed state is never reached here)."""
    if update.action == "none" or not update.text.strip():
        return
    # Hypotheses and their evidence hold the owner's own words: card, ID, phone and email patterns
    # are removed before anything is stored (the same redaction the problem records use).
    update = update.model_copy(
        update={
            "text": problem_records.redact(update.text)[0],
            "evidence": problem_records.redact(update.evidence)[0],
            "test": problem_records.redact(update.test)[0],
        }
    )
    book, rows = await ledger(session, scope, conversation_id)
    text = update.text.strip()[:300]
    if update.action == "add":
        before = len(book.items)
        h = book.add(
            text,
            evidence_for=[update.evidence] if update.evidence else [],
            confidence=moves.Confidence(update.confidence),
            cheapest_test=update.test[:300],
        )
        if len(book.items) > before:
            session.add(
                PiHypothesis(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    conversation_id=conversation_id,
                    text=h.text,
                    evidence_for=h.evidence_for,
                    evidence_against=[],
                    confidence=h.confidence.value,
                    cheapest_test=h.cheapest_test,
                    status=h.status.value,
                    ignored=False,
                )
            )
            return
    else:
        h = next((x for x in book.items if x.text.strip().lower() == text.lower()), None)  # type: ignore[assignment]
        if h is None:
            return
        if update.action == "against":
            book.against(h, update.evidence or "owner said otherwise")
        else:
            book.drop(h)
    index = next((i for i, x in enumerate(book.items) if x is h), None)
    row = rows.get(index) if index is not None else None
    if row is not None:
        row.evidence_for = list(h.evidence_for)
        row.evidence_against = list(h.evidence_against)
        row.confidence = h.confidence.value
        row.status = h.status.value


def _mark(h: moves.Hypothesis, row: PiHypothesis | None) -> None:
    if row is not None:
        row.evidence_for = list(h.evidence_for)
        row.evidence_against = list(h.evidence_against)
        row.confidence = h.confidence.value
        row.status = h.status.value
        row.ignored = h.ignored


def _apply_verdict(
    book: moves.HypothesisLedger, h: moves.Hypothesis, verdict: str, words: str
) -> bool:
    """The owner's reply applied to one hypothesis. Evidence only; the confirmed state is reached
    by an explicit owner yes to the hypothesis question and by nothing else."""
    if verdict == "none":
        return False
    if verdict == "ignored":
        changed = not h.ignored
        h.ignored = True
        return changed
    if words in h.evidence_for or words in h.evidence_against:
        return False  # the same message processed twice
    h.ignored = False  # it was answered after all
    if verdict == "against":
        book.against(h, words)
    else:
        h.evidence_for.append(words)
        if verdict == "confirm":
            book.confirm(h, by="owner")
        elif h.confidence == moves.Confidence.LOW:
            h.confidence = moves.Confidence.MEDIUM  # supported, never confirmed
    return True


async def reflect(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    *,
    previous_ai: str,
    previous_move: str | None,
    said: str,
) -> str | None:
    """Update the ledger from the owner's reply to pi's last message (the statuses used to change
    only when the model sent add/against/drop). A reply that supports or contradicts an open
    hypothesis's cause adds evidence_for or evidence_against (stored redacted); the hypothesis pi
    put to the owner as a question is `ignored` when the reply deflects or asks something else, and
    `confirmed` only on an explicit owner yes. Returns the verdict for that hypothesis (or None)."""
    if not said.strip():
        return None
    book, rows = await ledger(session, scope, conversation_id)
    live = [(i, h) for i, h in enumerate(book.items) if h.status == moves.Status.OPEN]
    if not live:
        return None
    put: int | None = None
    if hypothesis_reply.is_question(previous_ai):
        asked = hypothesis_reply.stems(previous_ai)
        shared, best = max(
            ((len(asked & hypothesis_reply.stems(h.text)), i) for i, h in live),
            key=lambda pair: (pair[0], pair[1]),
        )
        if shared >= hypothesis_reply.MIN_SHARED:
            put = best
        elif previous_move == moves.Move.M4.value:
            unanswered = [i for i, h in live if not h.ignored]
            put = max(unanswered) if unanswered else None
    words = problem_records.redact(" ".join(said.split()))[0][:300]
    out: str | None = None
    for i, h in live:
        is_put = i == put
        verdict = hypothesis_reply.judge(said, h.text, put_to_owner=is_put)
        changed = _apply_verdict(book, h, verdict, words)
        if changed:
            _mark(h, rows.get(i))
        if is_put:
            out = verdict
    await session.flush()
    return out


async def reflect_safely(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    *,
    previous_ai: str,
    previous_move: str | None,
    said: str,
) -> str | None:
    """`reflect`, but a missing table or any failure only means the ledger is left as it was."""
    try:
        async with session.begin_nested():
            return await reflect(
                session,
                scope,
                conversation_id,
                previous_ai=previous_ai,
                previous_move=previous_move,
                said=said,
            )
    except Exception:  # an aid to the thinking step; the reply must never wait on it
        logging.getLogger(__name__).warning("pi_hypothesis_reflect_failed", exc_info=True)
        return None


# --- the turn-level helpers the conversation flow calls -----------------------------------------


def turn_plan(turn: Any) -> MovePlan | None:
    plan = getattr(turn, "move_plan", None)
    return plan if isinstance(plan, MovePlan) else None


def check_turn(turn: Any, context: dict[str, Any]) -> str:
    """The rewrite instruction for a bad plan on this turn, or "" when it can be followed."""
    plan = turn_plan(turn)
    if plan is None:
        return ""
    found = problems(plan, str(getattr(turn, "reply", "")), context)
    return instruction(found) if found else ""


def settle_turn(turn: Any, context: dict[str, Any]) -> None:
    """Keep the model's plan when it is valid, else the code's own (never a bad plan on the turn),
    and give the think-lint move-repeat check the move of this message (context key `plan`)."""
    plan = turn_plan(turn)
    if plan is None:
        return
    kept, _ = settle(plan, str(getattr(turn, "reply", "")), context)
    turn.move_plan = kept
    context["plan"] = current_move(kept)


def move_of_sent(turn: Any) -> MovePlan | None:
    """The plan to store for what was actually sent. A reply the application wrote itself (a gate's
    fixed answer, the sorted summary) is not the model's move: it is stored as the matching plain
    move, with the reason saying so."""
    plan = turn_plan(turn)
    if plan is None:
        return None
    if getattr(turn, "_summary", False):
        return MovePlan(
            move=moves.Move.SUMMARISE.value, reason="the sorted summary replaced the reply"
        )
    if getattr(getattr(turn, "_decision", None), "reply", None):
        return MovePlan(move=moves.Move.HONOUR.value, reason="a decision gate wrote the reply")
    return plan


async def record_sent(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    message_id: UUID,
    turn: Any,
    sent_text: str,
) -> None:
    """Store the move of the message that went out. Never breaks the send: a failure is logged."""
    plan = move_of_sent(turn)
    if plan is None:
        return
    try:
        async with session.begin_nested():
            await record(session, scope, conversation_id, message_id, plan, sent_text)
    except Exception:  # the log is an aid; the reply has already been queued
        logging.getLogger(__name__).warning("pi_move_log_failed", exc_info=True)
