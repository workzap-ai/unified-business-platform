"""Which two ideas pi gives, and what it remembers it gave (Addendum 2, Parts 2.1 and 3.3).

The idea bandit chooses WHICH two ideas, never how many: the count is fixed by the value line. For
one business pi never repeats an idea already given, tried or rejected, and when an owner says
"already doing that" it swaps to a different kind of idea at once. When the customer comes back
pi opens with what it suggested last time and asks if anything started: that is its one question.
Nothing here runs unless the workspace has learning on and `brain.solution_mode` set.
"""

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning,
    solution_lint,
    solution_rules,
    solution_score,
    solution_versions,
    solutions,
    value_line,
)
from app.modules.pi.language import detect_language
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.solution_models import PiIdeaArm, PiIdeaFeedback, PiIdeaSource, PiSolutionMemory
from app.shared.scope import WorkspaceScope

ASK = "ask_first"  # the kind of an arm that is a question, not an idea
NO_FEEDBACK = frozenset({"idea_not_tried"})  # a cue for pi, not a score for the idea
FIT_REVIEW = "idea_fit_review"  # the change-log kind of a weekly review item for an idea's fit
LIVE = ("active", "testing")
MATCH_AT = 3.0
STOP = frozenset(
    "the and for with that this have has are was were our their they them from your you but not "
    "all out can get got any more some what when where which who how too very much many one "
    "two just also than then into over only own same such will would about after again been "
    "before being both each few "
    "kam hai hain nahi aur ka ki ke mein se ko par ye wo bhi koi kuch".split()
)


def _stem(word: str) -> str:
    """A crude stem so "booking", "bookings" and "booked" meet ("double-book" shares "book")."""
    for tail in ("ings", "ing", "ed", "es", "s"):
        if word.endswith(tail) and len(word) - len(tail) >= 4:
            return word[: -len(tail)]
    return word


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in STOP} - {
        ""
    }


RELEVANT_AT = (
    3  # content words of theirs, from which a match must share at least one with its entry
)


def relevant(entry: dict[str, Any], words: str) -> bool:
    """An entry is served only when it shares a real content word with what the person said (a
    category or a sub-type alone gave a fashion shop with a price problem the exchange ideas, live
    test 3). A short phrase, which has too few words to judge by, is not held to this."""
    said = _words(words)
    if len(said) < RELEVANT_AT:
        return True
    theirs = _words(entry.get("words", "")) | _words(" ".join(entry.get("quick_ideas") or []))
    return bool(said & theirs)


def match_problem(
    problems: list[dict[str, Any]], category: str, subtype: str, words: str = ""
) -> dict[str, Any] | None:
    """The closest entry, if it is also relevant to what they said (see ``relevant``)."""
    found = _closest(problems, category, subtype, words)
    return found if found is not None and relevant(found, words) else None


def _closest(
    problems: list[dict[str, Any]], category: str, subtype: str, words: str = ""
) -> dict[str, Any] | None:
    """The numbered problem of an industry closest to a noted problem, by category, sub-type and
    wording (Part 2.1). None when nothing is close enough: pi then falls back and gives no idea."""
    said = _words(words)
    # A word of theirs that only ONE entry of this industry uses ("udhaar" in a kiryana shop) says
    # which problem they mean, and outweighs a sub-type the model guessed wrong ("cash_mismatch").
    own: dict[int, int] = {}
    for word in (w for w in said if len(w) >= 5):
        owners = [i for i, e in enumerate(problems) if word in _words(e.get("words", ""))]
        if len(owners) == 1:
            own[owners[0]] = own.get(owners[0], 0) + 1
    # Only when the model's sub-type points at a real entry of this industry that shares none of
    # their words: a sub-type this industry has no entry for says nothing about a wrong guess.
    if own and not any(
        subtype and e.get("subtype") == subtype and not said & _words(e.get("words", ""))
        for e in problems
    ):
        own = {}
    best: tuple[float, dict[str, Any]] | None = None
    for index, entry in enumerate(problems):
        score = 4.0 if subtype and entry.get("subtype") == subtype else 0.0
        score += 2.0 if category and entry.get("category") == category else 0.0
        score += 4.0 * min(own.get(index, 0), 2)
        theirs = _words(entry.get("words", ""))
        if said and theirs:
            # Their phrase is short and the entry's long: a shared share of the SHORTER one (the
            # overlap coefficient), not of the union, which no short phrase could ever reach.
            score += 3.0 * len(said & theirs) / min(len(said), len(theirs))
        if best is None or score > best[0]:
            best = (score, entry)
    if best is not None and best[0] >= MATCH_AT:
        return best[1]
    # Same category and at least one word in common with a numbered problem: close enough to
    # give its free ideas (a person's "udhaar" is the pack's "credit customers" problem).
    if category and said:
        near = [
            (len(said & _words(e.get("words", ""))), e)
            for e in problems
            if e.get("category") == category and said & _words(e.get("words", ""))
        ]
        if near:
            return max(near, key=lambda pair: pair[0])[1]
    # No shared words and no sub-type: when the industry has exactly one entry in the problem's
    # category, that is the match (a wrong idea is worse than none, so never with two or more).
    same = [e for e in problems if category and e.get("category") == category]
    if len(same) == 1:
        return same[0]
    # Whatever category the model chose: a word that only ONE numbered problem of this industry
    # uses ("udhaar" in a kiryana shop) says which problem the person means.
    votes: dict[int, int] = {}
    for word in (w for w in said if len(w) >= 5):
        owners = [i for i, e in enumerate(problems) if word in _words(e.get("words", ""))]
        if len(owners) == 1:
            votes[owners[0]] = votes.get(owners[0], 0) + 1
    if votes:
        best_vote = max(votes.values())
        winners = [i for i, n in votes.items() if n == best_vote]
        if len(winners) == 1:
            return problems[winners[0]]
    return None


def is_strong_match(entry: dict[str, Any], category: str, subtype: str, words: str = "") -> bool:
    """Whether this entry matches the noted problem by the main rule (sub-type, category and the
    owner's own wording reach MATCH_AT). The fallbacks above give ideas for a near problem, but the
    build line of a near problem would read as an irrelevant template."""
    said = _words(words)
    score = 4.0 if subtype and entry.get("subtype") == subtype else 0.0
    score += 2.0 if category and entry.get("category") == category else 0.0
    theirs = _words(entry.get("words", ""))
    if said and theirs:
        score += 3.0 * len(said & theirs) / min(len(said), len(theirs))
    return score >= MATCH_AT


def _where_arm(scope: WorkspaceScope) -> tuple[Any, ...]:
    return (
        PiIdeaArm.tenant_id == scope.tenant_id,
        PiIdeaArm.environment_id == scope.environment_id,
    )


async def learned_problems(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> list[dict[str, Any]]:
    """Problem entries pi drafted itself (Job S6) that are live or still in shadow."""
    found = []
    for version in await solution_versions.versions(session, scope, industry_key):
        entry = (version.diff or {}).get("add_problem")
        if entry and version.status in ("live", "shadow"):
            found.append(
                {**entry, "learned": True, "version": version.version, "state": version.status}
            )
    return found


async def entries(
    session: AsyncSession, scope: WorkspaceScope, industry_key: str
) -> list[dict[str, Any]]:
    """Every problem entry in force for an industry: the seed's, then the learned ones."""
    seed = solutions.load(industry_key)
    if seed is None:
        return []
    live = [e for e in await learned_problems(session, scope, industry_key) if e["state"] == "live"]
    return [*seed["problems"], *live]


def _arm_status(key: str, text: str, kind: str, extras: dict[str, Any]) -> str:
    """A seed idea is live when the idea guard passes it; an added one is "testing" (a tenth of the
    chats), or waits for a person when the guard flags it or its entry marked it for review."""
    if key in extras:
        verdict = solution_rules.check_idea(text)
        return (
            "testing" if verdict.ok and not verdict.review and not extras[key].review else "review"
        )
    return "active" if kind == ASK or solution_rules.check_idea(text).ok else "review"


async def ensure_arms(session: AsyncSession, scope: WorkspaceScope, industry_key: str) -> int:
    """Seed one industry's idea arms from Part 4 (once). Returns how many were added."""
    seed = solutions.load(industry_key)
    if seed is None:
        return 0
    await solution_versions.ensure_base(session, scope, industry_key)
    have = {
        row.arm_key: row
        for row in await session.scalars(
            select(PiIdeaArm).where(*_where_arm(scope), PiIdeaArm.industry_key == industry_key)
        )
    }
    added = 0
    for problem in seed["problems"]:
        extras = {i.arm_id: i for i in solutions.ideas(industry_key, problem) if i.extra}
        wanted = [
            (i.arm_id, i.text, solution_rules.idea_kind(i.text))
            for i in solutions.ideas(industry_key, problem)
        ]
        if problem.get("ask_first"):
            wanted.append((f"{industry_key}:{problem['id']}:ask1", problem["ask_first"], ASK))
        for key, text, kind in wanted:
            if key in have:
                # a seed idea the owner rewrote since it was stored keeps its record, with new words
                current = have[key]
                if current.source in ("seed", "seed_extra") and current.text != text[:500]:
                    current.text = text[:500]
                    current.language = detect_language(text) or "en"
                    current.kind = kind
                continue
            arm = PiIdeaArm(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                arm_key=key,
                industry_key=industry_key,
                problem_id=problem["id"],
                language=detect_language(text) or "en",
                text=text[:500],
                kind=kind,
                # a seed idea the guard would refuse today waits for a person (R-VAL, R-BUILD)
                status=_arm_status(key, text, kind, extras),
                source="seed_extra" if key in extras else "seed",
                version=solution_versions.BASE,
                # an added idea is tested on a tenth of the chats until it has been used enough
                traffic_cap=0.1 if key in extras else 1.0,
            )
            session.add(arm)
            await session.flush()
            session.add(
                PiIdeaSource(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    idea_arm_id=arm.id,
                    source="seed",
                    evidence_ids=[],
                )
            )
            added += 1
    await session.flush()
    return added


def _as_arm(row: PiIdeaArm) -> learning.Arm:
    return learning.Arm(
        row.text, row.alpha, row.beta, row.uses, row.traffic_cap if row.status == "testing" else 1.0
    )


@dataclass
class Choice:
    arms: list[PiIdeaArm] = field(default_factory=list)
    exhausted: bool = False  # nothing new is left for this business: pi points to the document
    swapped: bool = False  # the kind was changed because they rejected one


async def remembered(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, problem_id: str | None = None
) -> list[PiSolutionMemory]:
    query = select(PiSolutionMemory).where(
        PiSolutionMemory.tenant_id == scope.tenant_id,
        PiSolutionMemory.environment_id == scope.environment_id,
        PiSolutionMemory.customer_id == customer_id,
    )
    if problem_id is not None:
        query = query.where(PiSolutionMemory.problem_id == problem_id)
    return list(await session.scalars(query.order_by(PiSolutionMemory.given_at)))


async def choose(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    industry_key: str,
    problem_id: str,
    language: str,
    customer_id: UUID,
    count: int = 2,
    rng: random.Random | None = None,
    conversation_id: UUID | None = None,
) -> Choice:
    """The ideas to give this business for this problem: never one it has been given, tried or
    rejected; of a different kind from any it rejected; best-scoring more often, new ones tried
    some of the time. `count` is two (the value line); a caller cannot raise it. With a
    `conversation_id` the ideas already handed over in that chat for this problem count against
    IDEAS_PER_PROBLEM (R-VAL-01: two per problem, never a third)."""
    count = min(count, value_line.IDEAS_PER_MESSAGE)
    if conversation_id is not None:
        given_here = len(
            [
                m
                for m in await remembered(session, scope, customer_id, problem_id)
                if m.conversation_id == conversation_id
            ]
        )
        count = min(count, value_line.IDEAS_PER_PROBLEM - given_here)
        if count <= 0:
            return Choice([], exhausted=True)
    rows = list(
        await session.scalars(
            select(PiIdeaArm).where(
                *_where_arm(scope),
                PiIdeaArm.industry_key == industry_key,
                PiIdeaArm.problem_id == problem_id,
                PiIdeaArm.kind != ASK,
                PiIdeaArm.status.in_(LIVE),
            )
        )
    )
    memory = await remembered(session, scope, customer_id, problem_id)
    seen = {m.idea_arm_id for m in memory}
    by_id = {r.id: r for r in rows}
    rejected_kinds = {
        by_id[m.idea_arm_id].kind
        for m in memory
        if m.reaction in ("rejected", "generic") and m.idea_arm_id in by_id
    }
    pool = [r for r in rows if r.id not in seen and solution_lint.passes(r.text)]
    # the owner's own language first; the other language only when it is all that is left
    same = [r for r in pool if r.language == language]
    pool = same if len(same) >= 1 else pool
    different = [r for r in pool if r.kind not in rejected_kinds]
    swapped = bool(rejected_kinds) and bool(different)
    pool = different or pool
    chosen: list[PiIdeaArm] = []
    rng = rng or random.Random()
    while pool and len(chosen) < count:
        pick = learning.choose_arm([_as_arm(r) for r in pool], rng)
        row = next(r for r in pool if r.text == pick.text)
        chosen.append(row)
        # the second idea should be a different kind from the first when there is a choice
        others = [r for r in pool if r is not row]
        pool = [r for r in others if r.kind != row.kind] or others
    return Choice(chosen, exhausted=len(chosen) < count, swapped=swapped)


async def ask_first(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    industry_key: str,
    problem_id: str,
    rng: random.Random | None = None,
) -> PiIdeaArm | None:
    """The one question to ask when the facts are too thin to choose ideas (Job S8 learns it)."""
    rows = list(
        await session.scalars(
            select(PiIdeaArm).where(
                *_where_arm(scope),
                PiIdeaArm.industry_key == industry_key,
                PiIdeaArm.problem_id == problem_id,
                PiIdeaArm.kind == ASK,
                PiIdeaArm.status.in_(LIVE),
            )
        )
    )
    if not rows:
        return None
    pick = learning.choose_arm([_as_arm(r) for r in rows], rng or random.Random())
    return next(r for r in rows if r.text == pick.text)


async def record_given(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    conversation_id: UUID | None,
    arms: list[PiIdeaArm],
    now: datetime,
) -> int:
    """Remember what was given. One row per business and idea: it is never given twice."""
    have = {m.idea_arm_id for m in await remembered(session, scope, customer_id)}
    added = 0
    for arm in arms:
        arm.uses += 1
        if arm.id in have:
            continue
        session.add(
            PiSolutionMemory(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                customer_id=customer_id,
                conversation_id=conversation_id,
                industry_key=arm.industry_key,
                problem_id=arm.problem_id,
                idea_arm_id=arm.id,
                given_at=now,
            )
        )
        added += 1
    await session.flush()
    return added


async def react(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    arms: list[PiIdeaArm],
    reaction: solution_score.Reaction,
    message_id: UUID | None,
) -> int:
    """Apply what the person did next to the ideas they were given: feedback rows for the
    leaderboard (Job S2 counts them), solution memory for this business, and the generic flag."""
    memory = {m.idea_arm_id: m for m in await remembered(session, scope, customer_id)}
    done = 0
    for arm in arms:
        if reaction.signal in NO_FEEDBACK:
            continue
        session.add(
            PiIdeaFeedback(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                idea_arm_id=arm.id,
                customer_id=customer_id,
                industry_key=arm.industry_key,
                language=arm.language,
                signal=reaction.signal,
                score=reaction.score,
                message_id=message_id,
            )
        )
        row = memory.get(arm.id)
        if row is not None:
            value = solution_score.reaction_of_memory(reaction.signal)
            if value != "none":
                row.reaction = value
            row.said_will_try = row.said_will_try or reaction.signal == "idea_will_try"
            if reaction.signal == "idea_worked":
                row.reported_result = "worked"
            elif reaction.signal == "idea_no_help":
                row.reported_result = "no_change"
        if reaction.flag == "generic":
            arm.generic = True
        done += 1
    await session.flush()
    return done


async def note_offer(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    status: str,
    document_id: UUID | None = None,
) -> int:
    """Keep what happened to the offer next to the ideas (memory only: it never scores them)."""
    rows = await remembered(session, scope, customer_id)
    for row in rows:
        row.offer_status = status
        if document_id is not None:
            row.document_id = document_id
    await session.flush()
    return len(rows)


async def continuity(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    now: datetime,
    gap: timedelta = timedelta(hours=18),
    window: timedelta = timedelta(days=90),
) -> dict[str, Any] | None:
    """What to open with when the customer comes back (Part 3.3): the ideas of their latest visit
    and whether they have said anything about them. None when there is nothing to follow up."""
    rows = [
        m
        for m in await remembered(session, scope, customer_id)
        if now - window <= m.given_at <= now - gap
    ]
    if not rows:
        return None
    last = max(m.given_at for m in rows)
    latest = [m for m in rows if abs((last - m.given_at).total_seconds()) <= 3600]
    arms = [await session.get(PiIdeaArm, m.idea_arm_id) for m in latest]
    texts = [a.text for a in arms if a is not None]
    if not texts:
        return None
    worked = any(m.reported_result == "worked" for m in latest)
    tried = any(m.said_will_try or m.reaction == "tried" for m in latest)
    return {
        "tried": tried,
        "no_help": any(m.reported_result == "no_change" for m in latest),
        "ideas": texts,
        "arm_ids": [str(m.idea_arm_id) for m in latest],
        "problem_id": latest[0].problem_id,
        "industry_key": latest[0].industry_key,
        "worked": worked,
        "unanswered": all(m.reaction == "none" for m in latest),
    }


async def note_builds(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    problem_id: str,
    keys: list[str],
) -> int:
    """Remember which catalogue builds pi named for this problem (`builds_mentioned`). Memory only:
    it never reaches a score (Part 3.6)."""
    rows = await remembered(session, scope, customer_id, problem_id)
    for row in rows:
        row.builds_mentioned = sorted({*(row.builds_mentioned or []), *keys})
    await session.flush()
    return len(rows)


async def flag_fit(
    session: AsyncSession,
    scope: WorkspaceScope,
    arm: PiIdeaArm,
    *,
    why: str,
    owners: int = 1,
) -> bool:
    """A review item: is this idea wrong for the problem, or is the fit wrong (Part 3.2 and 3.5)?
    One open item per idea. False when one is already waiting."""
    waiting = await session.scalar(
        select(PiLearningChange.id).where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.kind == FIT_REVIEW,
            PiLearningChange.target_id == arm.id,
            PiLearningChange.status == "review",
        )
    )
    if waiting is not None:
        return False
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=FIT_REVIEW,
            speed="weekly",
            risk="low",
            target_id=arm.id,
            before={"industry": arm.industry_key, "problem": arm.problem_id},
            after={"owners": owners},
            status="review",
            reason=why[:300],
        )
    )
    await session.flush()
    return True
