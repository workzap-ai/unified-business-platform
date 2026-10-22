"""Score pi's replies by what happened next (pi Brain spec 8.3, 8.5 job 1).

A reply is scored once its outcome is known: the person's next message, or 24 hours of silence.
The row stores signals and reward only, never text. Scoring only observes; it changes nothing about
how pi replies, so it runs whether or not learning is frozen.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning, learning_bank
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.learning_models import PiQuestionArm
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.shared.scope import WorkspaceScope

SILENCE = timedelta(hours=24)


def situation_of(conversation: PiConversation, message: PiMessage) -> dict[str, str]:
    """The situation key (spec 8.2) with what is known here: state, language, kind of turn."""
    body = (message.body or "").rstrip()
    return {
        "state": conversation.flow_state or "",
        "language": conversation.language or "en",
        "turn_kind": "question" if body.endswith(("?", "؟")) else "statement",
    }


def outcome_of(message: PiMessage, following: PiMessage | None, now: datetime) -> learning.Next:
    asked = (message.body or "").rstrip().endswith(("?", "؟"))
    noted = (
        "noted" in (message.body or "").lower() or "note kar liya" in (message.body or "").lower()
    )
    if following is None:
        return learning.Next(
            None, (now - message.created_at).total_seconds() / 3600, pi_asked_a_question=asked
        )
    gap = (following.created_at - message.created_at).total_seconds() / 86400
    return learning.Next(
        following.body,
        pi_asked_a_question=asked,
        noted_confirmed=noted,
        gap_days=gap,
    )


async def attribution(
    session: AsyncSession, conversation: PiConversation, reply: PiMessage
) -> tuple[UUID | None, list[str]]:
    """Which question wording and which examples were shown when this reply was written. The
    stamp is found through the agent run that produced the reply; the wording is credited only if
    the reply really used it (otherwise the reward would teach the wrong lesson)."""
    stamps = (conversation.service_brief or {}).get("learning_used") or []
    if not stamps:
        return None, []
    run = await session.scalar(select(PiAgentRun).where(PiAgentRun.response_message_id == reply.id))
    if run is None:
        return None, []
    stamp = next((x for x in reversed(stamps) if x.get("message_id") == str(run.message_id)), None)
    if stamp is None:
        return None, []
    arm_id: UUID | None = None
    if stamp.get("arm"):
        arm = await session.get(PiQuestionArm, UUID(stamp["arm"]))
        if arm is not None and learning_bank.similarity(reply.body or "", arm.text) >= 0.4:
            arm_id = arm.id
    return arm_id, [str(e) for e in stamp.get("examples") or []]


async def score_new(session: AsyncSession, now: datetime | None = None, limit: int = 200) -> int:
    """Score pi's unscored replies whose outcome is known. Returns how many rows were written."""
    now = now or datetime.now(UTC)
    already = select(PiExperience.message_id)
    replies = list(
        await session.scalars(
            select(PiMessage)
            .join(PiConversation, PiConversation.id == PiMessage.conversation_id)
            .where(
                PiMessage.direction == "outbound",
                PiMessage.sender_type == "ai",
                PiMessage.status.in_(("sent", "delivered", "read")),
                PiConversation.flow_state.is_not(None),
                PiMessage.id.not_in(already),
            )
            .order_by(PiMessage.created_at)
            .limit(limit)
        )
    )
    written = 0
    for reply in replies:
        following = await session.scalar(
            select(PiMessage)
            .where(
                PiMessage.conversation_id == reply.conversation_id,
                PiMessage.direction == "inbound",
                PiMessage.created_at > reply.created_at,
            )
            .order_by(PiMessage.created_at)
            .limit(1)
        )
        if following is None and now - reply.created_at < SILENCE:
            continue  # the outcome is not known yet
        conversation = await session.get(PiConversation, reply.conversation_id)
        if conversation is None:
            continue
        signals = learning.signals_after(outcome_of(reply, following, now))
        arm_id, example_ids = await attribution(session, conversation, reply)
        session.add(
            PiExperience(
                tenant_id=reply.tenant_id,
                environment_id=reply.environment_id,
                message_id=reply.id,
                conversation_id=reply.conversation_id,
                situation=situation_of(conversation, reply),
                signals=signals,
                reward=learning.reward(signals),
                scored_at=now,
                arm_id=arm_id,
                example_ids=example_ids,
            )
        )
        written += 1
    await session.flush()
    return written


async def health(
    session: AsyncSession, since: datetime, scope: WorkspaceScope | None = None
) -> dict[str, Any]:
    """The learning metrics for a period (spec 8.13), for a status screen or a digest.
    With a scope, only that workspace's replies are counted."""
    query = select(PiExperience).where(PiExperience.scored_at >= since)
    if scope is not None:
        query = query.where(
            PiExperience.tenant_id == scope.tenant_id,
            PiExperience.environment_id == scope.environment_id,
        )
    rows = list(await session.scalars(query))
    if not rows:
        return {"scored": 0}
    counts: dict[str, int] = defaultdict(int)
    by_language: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_language[row.situation.get("language", "en")].append(row.reward)
        for signal in row.signals:
            counts[signal] += 1
    total = len(rows)
    return {
        "scored": total,
        "average_reward": round(sum(r.reward for r in rows) / total, 2),
        "signals": dict(counts),
        "confusion_rate": round(counts["confusion"] / total, 3),
        "correction_rate": round(counts["correction"] / total, 3),
        "opt_out_rate": round(counts["opt_out"] / total, 3),
        "average_reward_by_language": {
            lang: round(sum(vals) / len(vals), 2) for lang, vals in by_language.items()
        },
    }
