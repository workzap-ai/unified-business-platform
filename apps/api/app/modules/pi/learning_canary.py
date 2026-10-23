"""Canary rollout for new examples (pi Brain spec 8.5 job 9, 9.10 rule 3, eval L9).

A candidate a day old does not go live for everyone. It becomes a canary: only a small, fixed share
of conversations (chosen by a hash of the conversation id, so one conversation is always in or out)
may be shown it. Each night the replies that used it are compared with replies from the same kind of
situation that used no example. A guardrail that rises (rule break, opt-out, complaint, confusion,
correction) rolls it back at once; enough use with at least the control's reward promotes it. A
canary with no verdict after four weeks is retired. Every move is written to the change log.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning_rules
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiLearningChange, PiLearningExample
from app.shared.scope import WorkspaceScope

STALE_AFTER = timedelta(days=56)  # eight weeks without a verdict
LONG_RUN = timedelta(days=28)
MIN_FOR_ROLLBACK = 5  # replies before a guardrail can roll back (one odd chat is not evidence)


def in_canary(conversation_id: UUID | str, percent: int) -> bool:
    """Whether this conversation is in the canary share. Stable for a conversation."""
    digest = hashlib.sha256(str(conversation_id).encode()).hexdigest()
    return int(digest[:8], 16) % 100 < percent


def rates(rows: list[PiExperience]) -> learning_rules.Rates:
    """Per-reply rates for one arm of the comparison."""
    n = len(rows)
    if n == 0:
        return learning_rules.Rates(conversations=0, reward=0.0)

    def share(signal: str) -> float:
        return sum(1 for r in rows if signal in (r.signals or [])) / n

    return learning_rules.Rates(
        conversations=len({r.conversation_id for r in rows}),
        reward=sum(r.reward for r in rows) / n,
        opt_out=share("opt_out"),
        complaint=share("complaint"),
        confusion=share("confusion"),
        correction=share("correction"),
        rule_break=share("rule_break"),
    )


def judge(
    example_id: str,
    situation: dict[str, str],
    window: list[PiExperience],
    age: timedelta,
    *,
    min_days: int,
    min_uses: int,
) -> tuple[str, dict[str, Any]]:
    """promote, rollback or continue for one canary, from the experiences since it started."""
    used = [r for r in window if example_id in (r.example_ids or [])]
    control = [
        r
        for r in window
        if not r.example_ids
        and r.situation.get("state") == situation.get("state")
        and r.situation.get("language") == situation.get("language")
    ]
    canary_rates, control_rates = rates(used), rates(control)
    # Spec 9.10 rule 3: 300 conversations, or four weeks with a smaller floor.
    needed = min_uses if age >= LONG_RUN else learning_rules.MIN_CANARY
    verdict = learning_rules.canary_decision(control_rates, canary_rates, min_conversations=needed)
    if verdict == "rollback" and len(used) < MIN_FOR_ROLLBACK:
        verdict = "continue"
    if verdict == "promote" and age < timedelta(days=min_days):
        verdict = "continue"
    return verdict, {
        "canary_replies": len(used),
        "control_replies": len(control),
        "canary_reward": round(canary_rates.reward, 2),
        "control_reward": round(control_rates.reward, 2),
        "breached": learning_rules.breached(control_rates, canary_rates),
    }


async def evaluate(
    session: AsyncSession,
    scope: WorkspaceScope,
    now: datetime,
    *,
    min_days: int,
    min_uses: int,
) -> dict[str, int]:
    """Decide every canary: promote, roll back, keep watching, or retire when stale."""
    where = (
        PiExperience.tenant_id == scope.tenant_id,
        PiExperience.environment_id == scope.environment_id,
    )
    canaries = list(
        await session.scalars(
            select(PiLearningExample).where(
                PiLearningExample.tenant_id == scope.tenant_id,
                PiLearningExample.environment_id == scope.environment_id,
                PiLearningExample.status == "canary",
            )
        )
    )
    result = {"canaries": len(canaries), "promoted": 0, "rolled_back": 0, "stale": 0}
    for example in canaries:
        since = example.canary_since or example.created_at
        window = list(
            await session.scalars(
                select(PiExperience).where(*where, PiExperience.scored_at >= since)
            )
        )
        verdict, evidence = judge(
            str(example.id),
            example.situation,
            window,
            now - since,
            min_days=min_days,
            min_uses=min_uses,
        )
        if verdict == "promote":
            _move(session, scope, example, "active", "canary held up", "promoted", evidence)
            result["promoted"] += 1
        elif verdict == "rollback":
            why = "guardrail rose: " + ", ".join(map(str, evidence["breached"]))
            _move(session, scope, example, "retired", why, "rolled_back", evidence)
            result["rolled_back"] += 1
        elif now - since > STALE_AFTER:
            _move(
                session, scope, example, "retired", "no verdict in eight weeks", "stale", evidence
            )
            result["stale"] += 1
    await session.flush()
    return result


def _move(
    session: AsyncSession,
    scope: WorkspaceScope,
    example: PiLearningExample,
    status: str,
    reason: str,
    outcome: str,
    evidence: dict[str, Any],
) -> None:
    before = example.status
    example.status = status
    if status == "retired":
        example.retired_reason = reason[:200]
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=f"example_canary_{outcome}",
            target_id=example.id,
            before={"status": before},
            after={"status": status},
            evidence=dict(evidence),
            status="rolled_back" if outcome == "rolled_back" else "live",
            reason=reason[:300],
        )
    )


def start(example: PiLearningExample, now: datetime) -> None:
    example.status = "canary"
    example.canary_since = now or datetime.now(UTC)
