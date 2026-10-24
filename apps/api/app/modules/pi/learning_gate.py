"""The release gate for automatic changes (pi Brain spec 8.5 job 9, steps 1 and 2).

Step 1 (the golden and red-team tests) is run by `scripts/pi_release_gate.py`. Step 2, the replay,
lives here: a sample of recent stored conversations is replayed through the reply linter and the
spec 10.3 release bar (`learning_grader.release_gate`): no rule-break item anywhere, mean 1.7 or
more, no language below 1.65. The result is written to the change log (`kind="release_gate"`), and
no change may start its canary or be promoted while the last recorded result is failing
(`allows`). Rolling back is always allowed. With no result recorded yet nothing is held, so a
workspace that never ran the gate behaves as before.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import constitution, learning_grader
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

KIND = "release_gate"
SAMPLE = 200


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    conversations: int = 0
    mean: float = 0.0
    by_language: dict[str, float] = field(default_factory=dict)
    broken: list[str] = field(default_factory=list)  # conversation ids with a rule break

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reasons": self.reasons,
            "conversations": self.conversations,
            "mean": self.mean,
            "by_language": self.by_language,
            "broken": self.broken[:20],
        }


def grade_replies(replies: list[tuple[str, dict[str, Any]]]) -> learning_grader.Grade:
    """A grade for one conversation from the linter alone: a hard violation is a rule break (an
    item at 0), a soft one costs the reply a point, a clean reply scores 2."""
    scores: list[float] = []
    reasons: list[str] = []
    for text, context in replies:
        found = constitution.lint(text, context)
        hard = constitution.hard(found)
        reasons += [f"{v.rule}: {v.message}" for v in hard]
        scores.append(2.0 if not found else 1.0)
    mean = round(sum(scores) / len(scores), 2) if scores else 2.0
    return learning_grader.Grade(rule_break=bool(reasons), mean=mean, reasons=reasons[:5])


async def _conversation_replies(
    session: AsyncSession, conversation_id: UUID
) -> list[tuple[str, dict[str, Any]]]:
    """pi's stored replies in one chat with the linter context each one had (its state is the one
    scored for it)."""
    messages = list(
        await session.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation_id)
            .order_by(PiMessage.created_at)
        )
    )
    states = dict(
        (str(mid), (sit or {}).get("state", ""))
        for mid, sit in await session.execute(
            select(PiExperience.message_id, PiExperience.situation).where(
                PiExperience.conversation_id == conversation_id
            )
        )
    )
    out: list[tuple[str, dict[str, Any]]] = []
    history: list[dict[str, str]] = []
    latest = ""
    for m in messages:
        body = (m.body or "").strip()
        if not body:
            continue
        if m.direction == "inbound":
            latest = body
            history.append({"role": "customer", "text": body})
            continue
        if m.sender_type == "ai" and str(m.id) in states:
            context = {
                "pi_mode": "brain",
                "strict_voice": True,
                "flow": {"state": states[str(m.id)]},
                "history": list(history),
                "latest_customer_message": latest,
            }
            out.append((body, context))
        history.append({"role": "ai", "text": body})
    return out


async def replay(
    session: AsyncSession, scope: WorkspaceScope | None = None, n: int = SAMPLE
) -> GateResult:
    """Replay the most recent `n` scored conversations (of one workspace, or of every workspace
    when `scope` is None, for the disposable test database) and apply the release bar."""
    recent = (
        select(PiExperience.conversation_id, PiExperience.scored_at)
        .order_by(PiExperience.scored_at.desc())
        .limit(n * 20)
    )
    if scope is not None:
        recent = recent.where(
            PiExperience.tenant_id == scope.tenant_id,
            PiExperience.environment_id == scope.environment_id,
        )
    ids: list[UUID] = []
    for conversation_id, _ in await session.execute(recent):
        if conversation_id not in ids:
            ids.append(conversation_id)
        if len(ids) >= n:
            break
    graded: list[tuple[str, learning_grader.Grade]] = []
    broken: list[str] = []
    for conversation_id in ids:
        replies = await _conversation_replies(session, conversation_id)
        if not replies:
            continue
        conversation = await session.get(PiConversation, conversation_id)
        language = (conversation.language if conversation else None) or "en"
        grade = grade_replies(replies)
        graded.append((language, grade))
        if grade.rule_break:
            broken.append(str(conversation_id))
    verdict = learning_grader.release_gate(graded)
    by_language: dict[str, list[float]] = {}
    for language, g in graded:
        by_language.setdefault(language, []).append(g.mean)
    return GateResult(
        ok=verdict.ok,
        reasons=verdict.reasons,
        conversations=len(graded),
        mean=round(sum(g.mean for _, g in graded) / len(graded), 2) if graded else 0.0,
        by_language={k: round(sum(v) / len(v), 2) for k, v in by_language.items()},
        broken=broken,
    )


async def record(
    session: AsyncSession, scope: WorkspaceScope, result: GateResult, step: str = "replay"
) -> PiLearningChange:
    row = PiLearningChange(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        kind=KIND,
        created_at=datetime.now(UTC),  # not the transaction's now(): two results can share one
        risk="low",
        before={},
        after={"step": step, **result.as_dict()},
        evidence={"at": datetime.now(UTC).isoformat()},
        # Nothing graded is "nothing to check", not a failing release: it must never hold back
        # learning on a workspace that has no scored conversations yet (a fresh deployment).
        status="passed" if result.ok else ("skipped" if result.conversations == 0 else "failed"),
        reason=(
            "gate passed"
            if result.ok
            else "gate skipped: nothing graded yet"
            if result.conversations == 0
            else "gate failed: " + "; ".join(result.reasons)
        )[:300],
    )
    session.add(row)
    await session.flush()
    return row


async def last_result(session: AsyncSession, scope: WorkspaceScope) -> PiLearningChange | None:
    found: PiLearningChange | None = await session.scalar(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.kind == KIND,
        )
        .order_by(PiLearningChange.created_at.desc())
        .limit(1)
    )
    return found


async def allows(session: AsyncSession, scope: WorkspaceScope) -> bool:
    """False while the last recorded gate result is failing. No result recorded: allowed."""
    last = await last_result(session, scope)
    return last is None or last.status != "failed"
