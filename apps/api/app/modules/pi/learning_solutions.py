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
from app.modules.pi.solution_models import (
    PiIdeaArm,
    PiIdeaFeedback,
    PiIdeaSource,
    PiSolutionVersion,
)
from app.shared.scope import WorkspaceScope

OVERLAP_AT = 0.35  # of an idea's words that must be in the reply for it to count as given
STAMP_WINDOW = timedelta(days=14)  # a stamp stays open this long for a reaction (Part 3.3)
LATE_SIGNALS = frozenset({"idea_worked", "idea_no_help"})  # what a late return may still score
LATE_MESSAGES = 20
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


async def _next_texts(
    session: AsyncSession, reply: PiMessage, *, late: bool = False
) -> list[tuple[UUID, str]]:
    """What the person said after the reply: the first few messages, or with `late` the ones that
    come after those within the stamp window (someone coming back to say it worked)."""
    query = (
        select(PiMessage)
        .where(
            PiMessage.conversation_id == reply.conversation_id,
            PiMessage.direction == "inbound",
            PiMessage.created_at > reply.created_at,
        )
        .order_by(PiMessage.created_at)
    )
    if late:
        query = query.where(PiMessage.created_at <= reply.created_at + STAMP_WINDOW)
        query = query.offset(NEXT_MESSAGES).limit(LATE_MESSAGES)
    else:
        query = query.limit(NEXT_MESSAGES)
    return [(m.id, m.body or "") for m in await session.scalars(query) if (m.body or "").strip()]


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
    current: str | None = None,
) -> str:
    """Settle one stamp that offered ideas: remember what was given, and score it by what the
    person said next. `final` False is the instant look at the first message after the ideas
    (`current` is that message when it may not be stored yet); True is the nightly catch-up. A
    stamp stays open until a reaction or STAMP_WINDOW, so a late "it worked" still counts.
    Returns what happened."""
    if stamp.get("ideas_scored") or conversation.customer_id is None:
        return "done"
    reply, asked = await _reply_of(session, stamp)
    if reply is None:
        return "waiting"
    arms = await _arms(session, stamp.get("ideas") or [])
    given = reply_gave(reply.body or "", arms)
    nexts = await _next_texts(session, reply)
    if current and current.strip() and all(text != current for _, text in nexts):
        nexts = [*nexts, (reply.id, current)][:NEXT_MESSAGES]
    reaction = None
    reaction_message: UUID | None = None
    # At the readiness step pi asks about the solution document: a "yes" or "makes sense" there
    # answers the offer, not the ideas, and an offer never scores (Part 3.2).
    asked_offer = (
        stamp.get("state") == "S5_READINESS"
        or bool(stamp.get("offer_appended"))
        or "document" in (reply.body or "").lower()
    )
    for message_id, text in [] if asked_offer else nexts:
        reaction = solution_score.classify(text)
        if reaction is not None:
            reaction_message = message_id
            break
    if reaction is None and final and not asked_offer:
        # someone back after days to say "it worked" or "it did not help" (Part 3.2)
        for message_id, text in await _next_texts(session, reply, late=True):
            late = solution_score.classify(text)
            if late is not None and late.signal in LATE_SIGNALS:
                reaction, reaction_message = late, message_id
                break
    if reaction is None and not final:
        return "waiting"  # a plain next message: wait for the nightly look
    if reaction is None and now - reply.created_at < STAMP_WINDOW:
        return "waiting"  # nothing yet: the stamp stays open until a reaction or the window ends
    if given and not stamp.get("recorded"):
        await solution_ideas.record_given(
            session,
            scope,
            customer_id=conversation.customer_id,
            conversation_id=conversation.id,
            arms=given,
            now=reply.created_at,
        )
    if given and reaction is not None:
        await solution_ideas.react(
            session,
            scope,
            customer_id=conversation.customer_id,
            arms=given,
            reaction=reaction,
            message_id=reaction_message,
        )
        await _add_signal(session, reply, reaction)
        await _after_reaction(session, scope, given, reaction)
        stamp["reaction_message_id"] = str(reaction_message)
        stamp["reaction"] = reaction.signal
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


async def _after_reaction(
    session: AsyncSession,
    scope: WorkspaceScope,
    arms: list[PiIdeaArm],
    reaction: solution_score.Reaction,
) -> None:
    """What a reaction sets going besides its score: an idea that was tried and did not help has
    its fit for that problem reviewed (Part 3.2)."""
    if reaction.signal == "idea_no_help":
        for arm in arms:
            await solution_ideas.flag_fit(
                session, scope, arm, why="tried by an owner and it did not help: is the fit right?"
            )


async def react_to_followup(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    arm_ids: list[str],
    said: str,
) -> solution_score.Reaction | None:
    """The instant reaction to "Welcome back, did anything start?" (Part 3.3): classify what the
    person said and apply it to the ideas the follow-up asked about."""
    reaction = solution_score.classify(said)
    if reaction is None:
        return None
    arms = await _arms(session, arm_ids)
    await solution_ideas.react(
        session, scope, customer_id=customer_id, arms=arms, reaction=reaction, message_id=None
    )
    await _after_reaction(session, scope, arms, reaction)
    return reaction


async def _add_signal(
    session: AsyncSession, reply: PiMessage, reaction: solution_score.Reaction
) -> None:
    """The reaction adds to the reward of pi's reply (the reward model of Part 8.3)."""
    if reaction.signal in solution_ideas.NO_FEEDBACK:
        return
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
            PiConversation.last_message_at >= now - STAMP_WINDOW - timedelta(days=1),
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
        touched.add(arm.id)
    await session.flush()
    return {"feedback": len(rows), "ideas": len(touched)}


# --- the 10% canary of an idea ------------------------------------------------------------------

PROMOTE_USES = 50
PEER_MIN_FEEDBACK = 5  # a live idea needs this much feedback to be the one a newcomer must match


def success_rate(arm: PiIdeaArm) -> float:
    n = int((arm.stats or {}).get("n", 0))
    return (arm.alpha - 1) / n if n else 0.0


def mean_score(arm: PiIdeaArm) -> float:
    s = arm.stats or {}
    n = int(s.get("n", 0))
    return int(s.get("score_sum", 0)) / n if n else 0.0


async def canary_view(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    """Every idea still on its 10% start with how it is doing against the best live idea of its
    problem, and what the next nightly run will do with it (Part 3.4: 10% canary)."""
    testing = list(
        await session.scalars(
            select(PiIdeaArm).where(
                *solution_ideas._where_arm(scope), PiIdeaArm.status == "testing"
            )
        )
    )
    live = list(
        await session.scalars(
            select(PiIdeaArm).where(*solution_ideas._where_arm(scope), PiIdeaArm.status == "active")
        )
    )
    out = []
    for arm in sorted(testing, key=lambda a: (a.industry_key, a.problem_id, a.arm_key)):
        peers = [
            p
            for p in live
            if (p.industry_key, p.problem_id, p.language, p.kind == solution_ideas.ASK)
            == (arm.industry_key, arm.problem_id, arm.language, arm.kind == solution_ideas.ASK)
            and int((p.stats or {}).get("n", 0)) >= PEER_MIN_FEEDBACK
        ]
        best = max((success_rate(p) for p in peers), default=0.0)
        mine, score = success_rate(arm), mean_score(arm)
        if arm.uses < PROMOTE_USES:
            decision = "watching"
        elif score >= 0 and mine >= best:
            decision = "promote"
        else:
            decision = "hold"
        out.append(
            {
                "id": arm.id,
                "industry": arm.industry_key,
                "problem": arm.problem_id,
                "text": arm.text,
                "source": arm.source,
                "traffic": arm.traffic_cap,
                "uses": arm.uses,
                "feedback": int((arm.stats or {}).get("n", 0)),
                "mean_score": round(score, 2),
                "success_rate": round(mine, 2),
                "best_live_rate": round(best, 2),
                "decision": decision,
            }
        )
    return out


async def promote_ideas(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """testing to active, only for an idea that has had PROMOTE_USES uses, a non-negative score
    and a success rate at least that of the best live idea of its problem. The nightly gate must
    be passing (the caller checks `learning_gate.allows`)."""
    promoted = held = 0
    by_id = {row["id"]: row for row in await canary_view(session, scope)}
    for arm_id, row in by_id.items():
        if row["decision"] == "watching":
            continue
        arm = await session.get(PiIdeaArm, arm_id)
        if arm is None:
            continue
        if row["decision"] == "promote":
            arm.status, arm.traffic_cap = "active", 1.0
            promoted += 1
        else:
            held += 1
    await session.flush()
    return {"promoted": promoted, "held": held}


async def evaluate_versions(
    session: AsyncSession, scope: WorkspaceScope, now: datetime | None = None
) -> dict[str, Any]:
    """Automatic rollback (Part 3.4): a learned version whose new ideas have been used 50 times
    and score worse than the seed ideas of the same problems goes back, as a person's rollback
    would (rolling back is always allowed, even while the release gate fails)."""
    rolled: list[str] = []
    industries = sorted(
        set(
            await session.scalars(
                select(PiSolutionVersion.industry_key).where(
                    PiSolutionVersion.tenant_id == scope.tenant_id,
                    PiSolutionVersion.environment_id == scope.environment_id,
                    PiSolutionVersion.version != solution_versions.BASE,
                    PiSolutionVersion.status == "live",
                )
            )
        )
    )
    for industry in industries:
        arms = list(
            await session.scalars(
                select(PiIdeaArm).where(
                    *solution_ideas._where_arm(scope),
                    PiIdeaArm.industry_key == industry,
                    PiIdeaArm.kind != solution_ideas.ASK,
                )
            )
        )
        by_id = {str(a.id): a for a in arms}
        for version in await solution_versions.versions(session, scope, industry):
            if version.status != "live" or version.version == solution_versions.BASE:
                continue
            diff = version.diff or {}
            ids = [str(i) for i in diff.get("added") or []] + [
                str(i) for i in (diff.get("add_problem") or {}).get("arm_ids") or []
            ]
            mine = [by_id[i] for i in ids if i in by_id]
            if not mine or sum(a.uses for a in mine) < PROMOTE_USES:
                continue
            n = sum(int((a.stats or {}).get("n", 0)) for a in mine)
            if n == 0:
                continue
            ours = sum(int((a.stats or {}).get("score_sum", 0)) for a in mine) / n
            problems = {a.problem_id for a in mine}
            seeds = [a for a in arms if a.source == "seed" and a.problem_id in problems] or [
                a for a in arms if a.source == "seed"
            ]
            base_n = sum(int((a.stats or {}).get("n", 0)) for a in seeds)
            if base_n == 0:
                continue
            baseline = sum(int((a.stats or {}).get("score_sum", 0)) for a in seeds) / base_n
            if ours < baseline:
                await solution_versions.undo(
                    session,
                    scope,
                    industry,
                    version,
                    solution_versions.BASE,
                    kind="solution_auto_rollback",
                    why=f"solutions/{industry}@{version.version} scored {ours:.2f} against the "
                    f"seed's {baseline:.2f} after {sum(a.uses for a in mine)} uses",
                )
                rolled.append(f"{industry}@{version.version}")
    return {"rolled_back": rolled}


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


# --- weekly review items (Part 3.5) -------------------------------------------------------------

OWNERS_FOR_REVIEW = 2


async def flag_unhelpful(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """An idea that two or more different owners said did not help goes to a reviewer: is the
    idea wrong, or the fit? One open item per idea."""
    owners: dict[UUID, set[UUID]] = {}
    for arm_id, customer_id in await session.execute(
        select(PiIdeaFeedback.idea_arm_id, PiIdeaFeedback.customer_id).where(
            PiIdeaFeedback.tenant_id == scope.tenant_id,
            PiIdeaFeedback.environment_id == scope.environment_id,
            PiIdeaFeedback.signal == "idea_no_help",
        )
    ):
        owners.setdefault(arm_id, set()).add(customer_id)
    flagged = 0
    for arm_id, people in owners.items():
        if len(people) < OWNERS_FOR_REVIEW:
            continue
        arm = await session.get(PiIdeaArm, arm_id)
        if arm is not None and await solution_ideas.flag_fit(
            session,
            scope,
            arm,
            why=f"{len(people)} owners said it did not help: is the idea wrong, or the fit?",
            owners=len(people),
        ):
            flagged += 1
    return {"flagged": flagged}
