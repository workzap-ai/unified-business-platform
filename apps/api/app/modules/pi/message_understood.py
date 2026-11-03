"""What pi had understood when it sent a message (pi platform spec 8.11.1 "Conversation trace",
10.7 labels): the move it made and why, the problems it noted from the owner's last message, the
hypotheses it formed, and the offer decision, shown next to each pi message in the team's thread.

Read-only and built only from rows already stored (`pi_move_log`, `pi_problems`, `pi_hypotheses`,
`pi_offer_log`, `pi_solution_boxes`); nothing here calls a model or writes. `public_understood` is
the whitelist (same idea as `MessageView.public_media`): only the keys named here leave the server,
every text is redacted again and shortened, and the customer is never named.

"At that moment" means the window from the owner's previous message to the pi message: problems
whose source message is that owner message, hypotheses created in the window, offer decisions
logged in the window.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.box_models import PiOfferLog, PiSolutionBox
from app.modules.pi.models import PiMessage
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import redact
from app.modules.pi.think_models import PiHypothesis, PiMoveLog
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

# The spec 10.7 label of a move (the same words staff_review shows beside the thread).
LABELS = {
    "ask": "Listening",
    "invite": "Listening",
    "M16_hold_space": "Listening",
    "M1_reflect": "Listening",
    "summarise": "Noted",
    "give_ideas": "Ideas",
}
MAX_PROBLEMS = 6
MAX_HYPOTHESES = 3
CONFIDENCES = frozenset({"low", "medium", "high"})
OFFER_RULES = frozenset({"R1", "R2", "R3", "B"})


def _text(value: Any, limit: int) -> str:
    return redact(str(value or ""))[0][:limit].strip()


def public_understood(value: Any) -> dict[str, Any] | None:
    """The whitelist: anything not named here is dropped; None when nothing is left."""
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    move = _text(value.get("move"), 32)
    if move:
        out["move"] = move
        label = value.get("label") if value.get("label") in set(LABELS.values()) else None
        if label:
            out["label"] = label
    reason = _text(value.get("reason"), 300)
    if reason:
        out["reason"] = reason
    problems = []
    for p in (value.get("problems") or [])[:MAX_PROBLEMS]:
        if not isinstance(p, dict) or not _text(p.get("title"), 120):
            continue
        entry: dict[str, Any] = {"title": _text(p.get("title"), 120)}
        if isinstance(p.get("number"), int) and not isinstance(p.get("number"), bool):
            entry["number"] = p["number"]
        if p.get("category"):
            entry["category"] = _text(p.get("category"), 40)
        problems.append(entry)
    if problems:
        out["problems"] = problems
    hypotheses = []
    for h in (value.get("hypotheses") or [])[:MAX_HYPOTHESES]:
        if not isinstance(h, dict) or not _text(h.get("text"), 300):
            continue
        confidence = h.get("confidence")
        hypotheses.append(
            {
                "text": _text(h.get("text"), 300),
                "confidence": confidence if confidence in CONFIDENCES else "low",
            }
        )
    if hypotheses:
        out["hypotheses"] = hypotheses
    offer = value.get("offer")
    if isinstance(offer, dict) and offer.get("rule") in OFFER_RULES:
        out["offer"] = {
            "rule": offer["rule"],
            "allowed": bool(offer.get("allowed")),
            "blocked_reason": _text(offer.get("blocked_reason"), 300) or None,
        }
    box_state = _text(value.get("box_state"), 16)
    if box_state:
        out["box_state"] = box_state
    return out or None


def windows(rows: list[PiMessage]) -> dict[UUID, tuple[datetime | None, UUID | None]]:
    """For each pi message: when the window opened (the owner's previous message) and its id."""
    found: dict[UUID, tuple[datetime | None, UUID | None]] = {}
    last_in: PiMessage | None = None
    for row in rows:  # oldest first
        if row.direction == "inbound":
            last_in = row
        elif row.sender_type == "ai":
            found[row.id] = (last_in.created_at, last_in.id) if last_in else (None, None)
    return found


async def load(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID, rows: list[PiMessage]
) -> dict[UUID, dict[str, Any]]:
    """The raw annotation of each pi message in `rows` (oldest first); {} when nothing is stored.

    A workspace whose brain tables are not migrated yet shows no annotations; it never fails
    the thread.
    """
    span = windows(rows)
    if not span:
        return {}
    try:
        async with session.begin_nested():
            return await _load(session, scope, conversation_id, rows, span)
    except DBAPIError:
        return {}


async def _load(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation_id: UUID,
    rows: list[PiMessage],
    span: dict[UUID, tuple[datetime | None, UUID | None]],
) -> dict[UUID, dict[str, Any]]:
    ai_ids = list(span)
    moves = {
        m.message_id: m
        for m in await session.scalars(
            WorkspaceRepository(session, PiMoveLog, scope)
            .select()
            .where(PiMoveLog.message_id.in_(ai_ids))
        )
    }
    problems = list(
        await session.scalars(
            WorkspaceRepository(session, PiProblem, scope)
            .select()
            .where(PiProblem.conversation_id == conversation_id)
            .order_by(PiProblem.number)
        )
    )
    hypotheses = list(
        await session.scalars(
            WorkspaceRepository(session, PiHypothesis, scope)
            .select()
            .where(PiHypothesis.conversation_id == conversation_id, PiHypothesis.ignored.is_(False))
            .order_by(PiHypothesis.created_at)
        )
    )
    offers = list(
        await session.scalars(
            WorkspaceRepository(session, PiOfferLog, scope)
            .select()
            .where(PiOfferLog.conversation_id == conversation_id)
            .order_by(PiOfferLog.created_at)
        )
    )
    customer_id = problems[0].customer_id if problems else None
    boxes: list[PiSolutionBox] = []
    if offers and customer_id is not None:
        boxes = list(
            await session.scalars(
                select(PiSolutionBox)
                .where(
                    PiSolutionBox.tenant_id == scope.tenant_id,
                    PiSolutionBox.environment_id == scope.environment_id,
                    PiSolutionBox.customer_id == customer_id,
                )
                .order_by(PiSolutionBox.version)
            )
        )
    by_id = {r.id: r for r in rows}
    result: dict[UUID, dict[str, Any]] = {}
    for message_id, (opened, source_id) in span.items():
        sent = by_id[message_id].created_at
        entry: dict[str, Any] = {}
        move = moves.get(message_id)
        if move is not None:
            entry["move"] = move.move
            entry["reason"] = move.reason
            if move.move in LABELS:
                entry["label"] = LABELS[move.move]
        if source_id is not None:
            entry["problems"] = [
                {"number": p.number, "title": p.title, "category": p.category}
                for p in problems
                if str(source_id) in (p.source_message_ids or [])
            ]
        entry["hypotheses"] = [
            {"text": h.text, "confidence": h.confidence}
            for h in hypotheses
            if (opened is None or h.created_at >= opened) and h.created_at <= sent
        ]
        in_window = [
            o for o in offers if (opened is None or o.created_at >= opened) and o.created_at <= sent
        ]
        if in_window:
            last = in_window[-1]
            entry["offer"] = {
                "rule": last.rule,
                "allowed": last.allowed,
                "blocked_reason": last.blocked_reason,
            }
            then = [b for b in boxes if b.created_at <= sent]
            if then:
                entry["box_state"] = then[-1].state
        if public_understood(entry) is not None:
            result[message_id] = entry
    return result
