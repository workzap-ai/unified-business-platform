"""Daily learning for solutions, part one (Addendum 2 to the pi Brain v3, Part 3.4).

S1 scores every solution reply by what the person did next; S2 updates the idea leaderboards from
those scores; S4 retires ideas that keep scoring low, are often "already tried" or are too generic;
S8 learns which single question to ask first. `add_candidate` is how every new idea enters, whoever
found it: it runs the idea through the same guard (`solution_rules`) and starts it in testing at a
tenth of the traffic. Parts two (S3 find, S5 replace samples, S6 grow, S7 audit failed chats) are in
`learning_solutions_grow`. Every job runs inside the nightly gate and stops while learning is
frozen.
"""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning,
    learning_rules,
    solution_ideas,
    solution_rules,
    solution_score,
    solution_versions,
)
from app.modules.pi.experience_models import PiExperience
from app.modules.pi.language import detect_language
from app.modules.pi.models import PiAgentRun, PiConversation, PiMessage
from app.modules.pi.solution_models import PiIdeaArm, PiIdeaFeedback, PiIdeaSource
from app.shared.scope import WorkspaceScope

OVERLAP_AT = 0.35  # of an idea's words that must be in the reply for it to count as given
SETTLE_AFTER = timedelta(hours=6)  # S1 waits this long for the person's answer
NEXT_MESSAGES = 3  # the reaction may come a message or two later
MIN_FEEDBACK = 20  # before an idea can be retired
ASK_ENGAGED_WORDS = 8
STAT_KEYS = {
    "idea_will_try": "tried",
    "idea_worked": "worked",
    "idea_followup": "engaged",
    "idea_more": "engaged",
    "idea_new_problems": "engaged",
    "idea_already_doing": "already",
    "idea_not_possible": "not_possible",
    "idea_generic": "generic",
    "idea_confused": "confused",
    "idea_impatient": "impatient",
    "idea_no_help": "no_help",
    "idea_ok_only": "ok",
    "ask_engaged": "ask_engaged",
    "ask_flat": "ask_flat",
}


def _stamps(conversation: PiConversation) -> list[dict[str, Any]]:
    return list((conversation.service_brief or {}).get("learning_used") or [])


def _save_stamps(conversation: PiConversation, stamps: list[dict[str, Any]]) -> None:
    brief = dict(conversation.service_brief or {})
    brief["learning_used"] = stamps
    conversation.service_brief = brief


def overlap(idea: str, reply: str) -> float:
    words = {w for w in re.findall(r"[a-z]{4,}", idea.lower())}
    return len(words & set(re.findall(r"[a-z]{4,}", reply.lower()))) / len(words) if words else 0.0


def reply_gave(reply: str, arms: list[PiIdeaArm]) -> list[PiIdeaArm]:
    """The ideas a reply actually gave. A reply with numbered or bulleted ideas gave the ones it was
    offered; otherwise an idea counts when most of its words are there (the model may rephrase)."""
    listed = solution_rules.count_ideas(reply) > 0
    return [a for a in arms if listed or overlap(a.text, reply) >= OVERLAP_AT]


async def _reply_of(
    session: AsyncSession, stamp: dict[str, Any]
) -> tuple[PiMessage | None, PiMessage | None]:
    """(pi's reply, the customer message it answered) for a stamp."""
    if not stamp.get("message_id"):
        return None, None
    asked = await session.get(PiMessage, UUID(stamp["message_id"]))
    run = await session.scalar(
        select(PiAgentRun).where(PiAgentRun.message_id == UUID(stamp["message_id"]))
    )
    reply = (
        await session.get(PiMessage, run.response_message_id)
        if run is not None and run.response_message_id is not None
        else None
    )
    return reply, asked


async def _next_texts(session: AsyncSession, reply: PiMessage) -> list[tuple[UUID, str]]:
    rows = await session.scalars(
        select(PiMessage)
        .where(
            PiMessage.conversation_id == reply.conversation_id,
            PiMessage.direction == "inbound",
            PiMessage.created_at > reply.created_at,
        )
        .order_by(PiMessage.created_at)
        .limit(NEXT_MESSAGES)
    )
    return [(m.id, m.body or "") for m in rows if (m.body or "").strip()]


async def _arms(session: AsyncSession, ids: list[str]) -> list[PiIdeaArm]:
    found = [await session.get(PiIdeaArm, UUID(i)) for i in ids]
    return [a for a in found if a is not None]


async def settle(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    stamp: dict[str, Any],
    now: datetime,
    *,
    final: bool,
) -> str:
    """Settle one stamp that offered ideas: remember what was given, and score it by what the
    person said next. `final` False is the instant look at the first message after the ideas;
    True is the nightly catch-up. Returns what happened."""
    if stamp.get("ideas_scored") or conversation.customer_id is None:
        return "done"
    reply, asked = await _reply_of(session, stamp)
    if reply is None:
        return "waiting"
    arms = await _arms(session, stamp.get("ideas") or [])
    given = reply_gave(reply.body or "", arms)
    nexts = await _next_texts(session, reply)
    reaction = None
    # At the readiness step pi asks about the solution document: a "yes" or "makes sense" there
    # answers the offer, not the ideas, and an offer never scores (Part 3.2).
    asked_offer = stamp.get("state") == "S5_READINESS" or "document" in (reply.body or "").lower()
    for message_id, text in [] if asked_offer else nexts:
        reaction = solution_score.classify(text)
        if reaction is not None:
            reaction_message = message_id
            break
    if reaction is None and not final and not nexts:
        return "waiting"
    if reaction is None and not final:
        return "waiting"  # a plain next message: wait for the nightly look
    if reaction is None and not nexts and now - reply.created_at < SETTLE_AFTER:
        return "waiting"
    if given and not stamp.get("recorded"):
        await solution_ideas.record_given(
            session,
            scope,
            customer_id=conversation.customer_id,
            conversation_id=conversation.id,
            arms=given,
            now=reply.created_at,
        )
        if reaction is not None:
            await solution_ideas.react(
                session,
                scope,
                customer_id=conversation.customer_id,
                arms=given,
                reaction=reaction,
                message_id=reply.id,
            )
            await _add_signal(session, reply, reaction)
            stamp["reaction"] = reaction.signal
            stamp["reaction_message_id"] = str(reaction_message)
    if stamp.get("ask_arm"):
        await _settle_ask(session, scope, conversation, stamp, nexts, reply)
    stamp["ideas_scored"] = True
    stamp["ideas_given"] = [str(a.id) for a in given]
    return "scored" if given else "not_given"


async def _settle_ask(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    stamp: dict[str, Any],
    nexts: list[tuple[UUID, str]],
    reply: PiMessage,
) -> None:
    """The question asked before the ideas (Job S8): did the person answer with something?"""
    arm = await session.get(PiIdeaArm, UUID(stamp["ask_arm"]))
    if arm is None or conversation.customer_id is None:
        return
    text = nexts[0][1] if nexts else ""
    engaged = len(text.split()) >= ASK_ENGAGED_WORDS and "confusion" not in learning.signals_after(
        learning.Next(reply=text)
    )
    session.add(
        PiIdeaFeedback(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            idea_arm_id=arm.id,
            customer_id=conversation.customer_id,
            industry_key=arm.industry_key,
            language=arm.language,
            signal="ask_engaged" if engaged else "ask_flat",
            score=1 if engaged else 0,
            message_id=reply.id,
        )
    )


async def _add_signal(
    session: AsyncSession, reply: PiMessage, reaction: solution_score.Reaction
) -> None:
    """The reaction adds to the reward of pi's reply (the reward model of Part 8.3)."""
    row = await session.scalar(select(PiExperience).where(PiExperience.message_id == reply.id))
    if row is None or any(s.startswith("idea_") for s in row.signals or []):
        return
    row.signals = [*(row.signals or []), reaction.signal]
    row.reward = learning.reward(row.signals)


async def score_replies(
    session: AsyncSession, scope: WorkspaceScope, now: datetime | None = None
) -> dict[str, int]:
    """Job S1: score every solution reply that has not been scored yet."""
    now = now or datetime.now(UTC)
    counts = {"scored": 0, "not_given": 0, "waiting": 0}
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.last_message_at >= now - timedelta(days=10),
        )
    )
    for conversation in rows:
        stamps = _stamps(conversation)
        changed = False
        for stamp in stamps:
            if not stamp.get("ideas") or stamp.get("ideas_scored"):
                continue
            outcome = await settle(session, scope, conversation, stamp, now, final=True)
            if outcome in counts:
                counts[outcome] += 1
            changed = changed or bool(stamp.get("ideas_scored"))
        if changed:
            _save_stamps(conversation, stamps)
    await session.flush()
    return counts


# --- S2: the leaderboards -----------------------------------------------------------------------


def _is_success(score: int) -> bool:
    return score >= 2


def _is_failure(score: int) -> bool:
    return score <= -1


async def update_leaderboards(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """Job S2: count the new feedback in each idea's statistics. The best ideas are then given
    more often and newer ones still get tried some of the time (Thompson sampling)."""
    rows = list(
        await session.scalars(
            select(PiIdeaFeedback).where(
                PiIdeaFeedback.tenant_id == scope.tenant_id,
                PiIdeaFeedback.environment_id == scope.environment_id,
                PiIdeaFeedback.applied.is_(False),
            )
        )
    )
    touched: set[UUID] = set()
    for row in rows:
        arm = await session.get(PiIdeaArm, row.idea_arm_id)
        row.applied = True
        if arm is None:
            continue
        stats = dict(arm.stats or {})
        key = STAT_KEYS.get(row.signal, row.signal)
        stats[key] = int(stats.get(key, 0)) + 1
        stats["n"] = int(stats.get("n", 0)) + 1
        stats["score_sum"] = int(stats.get("score_sum", 0)) + row.score
        arm.stats = stats
        if _is_success(row.score):
            arm.alpha += 1
        elif _is_failure(row.score):
            arm.beta += 1
        if arm.status == "testing" and arm.uses >= 50:
            arm.status, arm.traffic_cap = "active", 1.0
        touched.add(arm.id)
    await session.flush()
    return {"feedback": len(rows), "ideas": len(touched)}


# --- S4: retire ideas that do not earn their place ----------------------------------------------


def should_retire(stats: dict[str, int]) -> str:
    """Why an idea should be retired, or an empty string. Needs enough feedback to judge."""
    n = int(stats.get("n", 0))
    if n < MIN_FEEDBACK:
        return ""
    if int(stats.get("score_sum", 0)) / n < -0.5:
        return "keeps scoring low"
    if int(stats.get("already", 0)) / n >= 0.4:
        return 'often "already tried": everyone does it, so it adds nothing'
    if int(stats.get("generic", 0)) / n >= 0.3:
        return 'flagged "too generic"'
    return ""


async def retire_ideas(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any]:
    """Job S4. A retired idea stays in history with its reason; a problem is never left with fewer
    than two live ideas."""
    arms = list(
        await session.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.tenant_id == scope.tenant_id,
                PiIdeaArm.environment_id == scope.environment_id,
                PiIdeaArm.kind != solution_ideas.ASK,
                PiIdeaArm.status.in_(solution_ideas.LIVE),
            )
        )
    )
    live: dict[tuple[str, str], int] = {}
    for arm in arms:
        live[(arm.industry_key, arm.problem_id)] = (
            live.get((arm.industry_key, arm.problem_id), 0) + 1
        )
    gone: dict[str, list[dict[str, str]]] = {}
    for arm in sorted(arms, key=lambda a: (a.stats or {}).get("score_sum", 0)):
        why = should_retire(arm.stats or {})
        key = (arm.industry_key, arm.problem_id)
        if not why or live[key] <= 2:
            continue
        gone.setdefault(arm.industry_key, []).append(
            {"id": str(arm.id), "from": arm.status, "reason": why}
        )
        arm.status, arm.retired_reason = "retired", why
        live[key] -= 1
    for industry, entries in gone.items():
        await solution_versions.bump(
            session,
            scope,
            industry,
            {"retired": entries},
            {"reasons": sorted({e["reason"] for e in entries}), "count": len(entries)},
        )
    await session.flush()
    return {"retired": sum(len(v) for v in gone.values()), "industries": sorted(gone)}


# --- S8: the question asked first ---------------------------------------------------------------


async def learn_ask_first(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """Job S8. A question that leaves people with nothing to say is retired when another one for
    the same problem does better. Their statistics come from S2."""
    asks = list(
        await session.scalars(
            select(PiIdeaArm).where(
                PiIdeaArm.tenant_id == scope.tenant_id,
                PiIdeaArm.environment_id == scope.environment_id,
                PiIdeaArm.kind == solution_ideas.ASK,
                PiIdeaArm.status.in_(solution_ideas.LIVE),
            )
        )
    )
    by_problem: dict[tuple[str, str], list[PiIdeaArm]] = {}
    for arm in asks:
        by_problem.setdefault((arm.industry_key, arm.problem_id), []).append(arm)
    retired = 0
    for group in by_problem.values():
        if len(group) < 2:
            continue

        def rate(a: PiIdeaArm) -> float:
            s = a.stats or {}
            seen = int(s.get("ask_engaged", 0)) + int(s.get("ask_flat", 0))
            return int(s.get("ask_engaged", 0)) / seen if seen else 0.5

        best = max(group, key=rate)
        for arm in group:
            seen = int((arm.stats or {}).get("ask_engaged", 0)) + int(
                (arm.stats or {}).get("ask_flat", 0)
            )
            if arm is not best and seen >= 30 and rate(best) - rate(arm) >= 0.2:
                arm.status, arm.retired_reason = (
                    "retired",
                    "people answer it with less than the others",
                )
                retired += 1
    await session.flush()
    return {"asks_retired": retired}


# --- how any new idea enters --------------------------------------------------------------------


def normal_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


async def add_candidate(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    industry_key: str,
    problem_id: str,
    text: str,
    source: str,
    evidence_ids: list[str],
    language: str | None = None,
    redaction_confidence: float = 1.0,
) -> PiIdeaArm | None:
    """A new idea from an owner, a document, the miner or a neighbouring industry. It must pass the
    same guard as every idea (one line, no steps, no vendors, no claims). It starts in testing at
    10% of the traffic, or in review when it touches money or a regulated topic. None when refused
    or already there."""
    line = " ".join((text or "").split())
    verdict = solution_rules.check_idea(line)
    if not verdict.ok or redaction_confidence < learning_rules.PROMOTE_REDACTION:
        return None
    existing = await session.scalars(
        select(PiIdeaArm).where(
            PiIdeaArm.tenant_id == scope.tenant_id,
            PiIdeaArm.environment_id == scope.environment_id,
            PiIdeaArm.industry_key == industry_key,
            PiIdeaArm.problem_id == problem_id,
        )
    )
    if any(normal_text(a.text) == normal_text(line) for a in existing):
        return None
    count = len(
        list(
            await session.scalars(
                select(PiIdeaArm.id).where(
                    PiIdeaArm.tenant_id == scope.tenant_id,
                    PiIdeaArm.environment_id == scope.environment_id,
                    PiIdeaArm.industry_key == industry_key,
                )
            )
        )
    )
    arm = PiIdeaArm(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        arm_key=f"{industry_key}:{problem_id}:L{count + 1}{source[:1]}",
        industry_key=industry_key,
        problem_id=problem_id,
        language=language or detect_language(line) or "en",
        text=line[:500],
        kind=solution_rules.idea_kind(line),
        status="review" if verdict.needs_review else "testing",
        traffic_cap=0.10,
        source=source,
    )
    session.add(arm)
    await session.flush()
    session.add(
        PiIdeaSource(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            idea_arm_id=arm.id,
            source=source,
            evidence_ids=evidence_ids,
            redaction_confidence=Decimal(str(round(redaction_confidence, 3))),
        )
    )
    await session.flush()
    return arm
