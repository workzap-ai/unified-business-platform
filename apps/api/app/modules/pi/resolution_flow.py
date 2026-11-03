"""PS-flow: read the owner's answer to the ONE question pi asked about what it could not check.

`option_voice` stores the question it asked (`brief["pending_question"]`). On the owner's next
message `absorb_answer` reads it with PS-5's `apply_answer` and, when a value was read, saves it on
the record through the ordinary problem ops (so it is stored as the owner's own words, redacted and
capped like every other limit). The proposal never marks anything satisfied: the options are
checked again by the real L2-1 gate the next time ideas are listed. A non-answer is counted so the
question is asked again once, reworded, and never a third time.

Brain mode only; read from and written to the owner's own customer record (tenant and environment
scope come from `scope`).
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import problems, unknown_resolution
from app.modules.pi.problems import ProblemNote, ProblemOp
from app.modules.pi.requirements_types import Requirements
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

_TUPLE_FIELDS = ("why", "options", "option_texts", "problems", "codes", "target_limits")


def question_from(stored: Any) -> unknown_resolution.Question | None:
    """The stored question back as a `Question`; anything unreadable is None."""
    if not isinstance(stored, dict):
        return None
    try:
        data = {k: (tuple(v) if k in _TUPLE_FIELDS else v) for k, v in stored.items()}
        return unknown_resolution.Question(**data)
    except (TypeError, ValueError):
        return None


def note_for(update: unknown_resolution.FieldUpdate) -> ProblemNote:
    """The problem note that stores one proposed update (only what the owner said)."""
    base: dict[str, Any] = {}
    if update.field in ("budget", "staff", "deadline"):
        base[update.field] = update.value
    elif update.field == "cannot_change":
        base["cannot_change"] = [update.value]
        if update.replaces:
            base["cannot_change_remove"] = [update.replaces]
    elif update.field == "tried":
        base["tried"] = [{"what": update.replaces or "", "outcome": update.value}]
    return ProblemNote(**base)


async def absorb_answer(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: Any,
    message: Any,
    reqs: Requirements,
    language: str,
) -> bool:
    """True when the owner's message filled a requirement (the caller reads the record again)."""
    brief = dict(conversation.service_brief or {})
    question = question_from(brief.get("pending_question"))
    if question is None or conversation.customer_id is None:
        return False
    body = str(getattr(message, "body", "") or "")
    proposal = unknown_resolution.apply_answer(reqs, question, body, language)
    brief.pop("pending_question", None)  # one question at a time; it is asked again only if needed
    # PS-5 `record_outcome`: the key counts as asked, an answer that stays unknown as a non-answer
    state = unknown_resolution.record_outcome(
        unknown_resolution.ResolutionState(
            tuple(str(k) for k in brief.get("resolution_asked") or []),
            tuple(
                sorted(
                    (str(k), int(v))
                    for k, v in dict(brief.get("resolution_non_answers") or {}).items()
                )
            ),
        ),
        question,
        proposal,
    )
    brief["resolution_asked"] = list(state.asked)
    brief["resolution_non_answers"] = state.non_answer_map
    filled = proposal.status is unknown_resolution.Status.FILLED and bool(proposal.updates)
    if filled and question.key == unknown_resolution.LANGUAGE_KEY:
        code = str(proposal.updates[0].value)
        brief["language_pin"] = {
            "code": code,
            "script": "arabic" if code in ("ur", "ar") else "latin",
        }
        conversation.service_brief = brief
        return False  # the language is settled; the requirement question is asked next time
    if filled:
        book = problems.ProblemBook(session, scope, conversation.customer_id, "en")
        active = await book.active()
        by_number = {p.number: p for p in active}
        ops: list[ProblemOp] = []
        for update in proposal.updates:
            target = by_number.get(update.problem_number or 0) or (active[0] if active else None)
            if target is None:
                continue
            ops.append(
                ProblemOp(op="update", ref=problems.short_ref(target.id), note=note_for(update))
            )
        if ops:
            await problems.apply_ops(
                session,
                scope,
                conversation.customer_id,
                conversation.id,
                getattr(message, "id", None)
                if isinstance(getattr(message, "id", None), UUID)
                else None,
                ops,
                "en",
                owner_text=body,
            )
        conversation.service_brief = brief
        return True
    conversation.service_brief = brief
    return False
