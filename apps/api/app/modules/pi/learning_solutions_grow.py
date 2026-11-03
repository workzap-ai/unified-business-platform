"""Daily learning for solutions, part two (Addendum 2 to the pi Brain v3, Part 3.4).

S3 finds new ideas where a problem is down to few; S5 replaces a sample reply with a better real
one; S6 drafts a problem entry pi had no answer for, in shadow until it has proved itself; S7 turns
a failed solution chat into a lesson and a regression case. Everything a model writes goes through
`learning_solutions.add_candidate` and so through the same guard as a seed. Nothing here can raise
the number of ideas per message, change the value line or touch a build line.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    constitution,
    industry_packs,
    learning,
    learning_bank,
    learning_gate,
    learning_lessons,
    learning_rules,
    learning_seed,
    learning_situation,
    learning_solutions,
    solution_ask,
    solution_ideas,
    solution_rules,
    solution_versions,
    solutions,
)
from app.modules.pi.language import detect_language
from app.modules.pi.learning_models import PiLearningChange, PiLearningExample
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.solution_models import (
    PiBuildFit,
    PiCatalogueProposal,
    PiIdeaArm,
    PiSolutionVersion,
)
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

# (industry, problem label, language, ideas already live) -> new one-line ideas
IdeaWriter = Callable[[str, str, str, list[str]], Awaitable[list[str]]]
# A writer may also carry `draft_entry`, an EntryWriter: (industry, problem words) -> the rest of a
# problem entry ({"build_keys": [...], "ask_first": "...", "free_stops": "..."}). Every field is
# checked here; nothing it returns is used as written.
EntryWriter = Callable[[str, str], Awaitable[dict[str, Any]]]
MAX_NEW_PER_RUN = 10
MIN_LIVE_IDEAS = 3  # S3 looks for a problem with fewer than this many live ideas
SAMPLE_MIN_CANDIDATES = 3
SHADOW_DAYS = 7
MIN_UNMATCHED = 3  # the same unmatched problem this many times before S6 drafts an entry
BAD_REACTIONS = {"idea_no_help", "idea_impatient", "idea_confused", "idea_generic"}
LESSONS = {
    "idea_no_help": "When an idea was tried and did not help, say so plainly, ask what happened, "
    "and do not offer the same idea worded again.",
    "idea_impatient": "When someone is losing patience after the ideas, keep the next message "
    "short and ask only one simple question.",
    "idea_confused": "When someone is confused by the ideas, say each in one plain sentence in "
    "their own language and check which part was unclear.",
    "idea_generic": "When an idea is called generic, drop that kind of idea for this person and "
    "tie the next one to what they told us about their business.",
    "request_unanswered": "When someone asks for a fix, say yes first and give two ideas in that "
    "reply; if none fit yet, say plainly what you have noted and that Workzap can prepare a "
    "solution document, and never keep digging instead.",
    "idea_rejected_twice": "When two ideas in a row are met with already doing it or not possible, "
    "stop offering that kind: ask what they already do, and suggest measuring it instead.",
}


def _clean(text: str) -> bool:
    """Safe to keep as tenant-wide evidence: nothing personal, and no name, figure or contact the
    redactor could have missed (the bank's blunt check, at its promotion bar)."""
    return (
        not solution_rules.has_personal_data(text)
        and learning_bank.redaction_confidence(text) >= learning_rules.PROMOTE_REDACTION
    )


def _problem_label(entry: dict[str, Any]) -> str:
    return " ".join(
        str(entry.get(k) or "") for k in ("category", "subtype") if entry.get(k)
    ) or str(entry.get("id", ""))


async def find_ideas(
    session: AsyncSession, scope: WorkspaceScope, writer: IdeaWriter | None
) -> dict[str, int]:
    """Job S3: a problem with fewer than MIN_LIVE_IDEAS live ideas (one was retired) gets new
    candidates, each from the writer and each through the guard."""
    counts = {"proposed": 0, "refused": 0}
    if writer is None:
        return counts
    arms = list(await session.scalars(select(PiIdeaArm).where(*solution_ideas._where_arm(scope))))
    by_problem: dict[tuple[str, str, str], list[PiIdeaArm]] = {}
    for arm in arms:
        if arm.kind != solution_ideas.ASK:
            by_problem.setdefault((arm.industry_key, arm.problem_id, arm.language), []).append(arm)
    for (industry, problem_id, language), group in sorted(by_problem.items()):
        live = [a for a in group if a.status in solution_ideas.LIVE or a.status == "review"]
        if len(live) >= MIN_LIVE_IDEAS or not any(a.status == "retired" for a in group):
            continue
        if counts["proposed"] >= MAX_NEW_PER_RUN:
            break
        seed = solutions.load(industry) or {}
        problems = seed.get("problems", [])
        entry: dict[str, Any] = next((p for p in problems if p.get("id") == problem_id), {})
        lines = await writer(industry, _problem_label(entry), language, [a.text for a in live])
        for line in lines[: MIN_LIVE_IDEAS - len(live)]:
            fresh = await learning_solutions.add_candidate(
                session,
                scope,
                industry_key=industry,
                problem_id=problem_id,
                text=line,
                source="miner",
                evidence_ids=[str(a.id) for a in group if a.status == "retired"],
                language=language,
            )
            counts["proposed" if fresh is not None else "refused"] += 1
            if fresh is not None:
                await solution_versions.bump(
                    session,
                    scope,
                    industry,
                    {"added": [str(fresh.id)]},
                    {"source": "miner", "problem": problem_id},
                )
    return counts


HUMAN_SOURCES = ("owner", "document")
NEIGHBOUR_MIN_FEEDBACK = 20  # an idea must have this much feedback to be worth trying next door
NEIGHBOUR_MIN_SCORE = 1.0  # mean score per feedback
MAX_NEIGHBOURS_PER_RUN = 5
Generaliser = Callable[[str], Awaitable[str]]


async def add_human_idea(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    industry_key: str,
    problem_id: str,
    text: str,
    source: str,
    evidence_ids: list[str] | None = None,
    generalise: Generaliser | None = None,
) -> tuple[PiIdeaArm | None, list[str]]:
    """Job S3, the owner and document sources: an owner says what worked for them, or a reviewer
    keeps adding a do-it-yourself line to the solution documents. The text is generalised (when a
    `generalise` model step is given), redacted and then goes through `add_candidate` like every
    other idea: the guard, redaction at the promotion bar, 10% start in testing (review when it
    touches money or a regulated topic) and its evidence row. Returns (the idea, why not)."""
    if source not in HUMAN_SOURCES:
        return None, [f"source must be one of {', '.join(HUMAN_SOURCES)}"]
    if solutions.load(industry_key) is None:
        return None, ["unknown industry"]
    known = {e["id"] for e in await solution_ideas.entries(session, scope, industry_key)}
    if problem_id not in known:
        return None, ["unknown problem for this industry"]
    line = " ".join((text or "").split())
    if generalise is not None and line:
        line = " ".join((await generalise(line)).split())
    reasons = list(solution_rules.check_idea(line).reject)
    confidence = learning_bank.redaction_confidence(line)
    if confidence < learning_rules.PROMOTE_REDACTION:
        reasons.append("may hold a name, figure or contact: redact it first")
    if reasons:
        return None, reasons
    arm = await learning_solutions.add_candidate(
        session,
        scope,
        industry_key=industry_key,
        problem_id=problem_id,
        text=line,
        source=source,
        evidence_ids=evidence_ids or [],
        redaction_confidence=confidence,
    )
    if arm is None:
        return None, ["this idea is already there"]
    await solution_versions.bump(
        session,
        scope,
        industry_key,
        {"added": [str(arm.id)]},
        {"source": source, "problem": problem_id},
    )
    return arm, []


async def neighbour_ideas(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """Job S3, neighbouring industries: an idea that scores well in one industry is tried, in
    testing, for the same problem in a closely related industry of the same sector."""
    counts = {"proposed": 0}
    sector: dict[str, str] = {
        key: industry_packs.sector_key(pack) for key, pack in industry_packs.load_packs().items()
    }
    members: dict[str, list[str]] = {}
    for key, code in sector.items():
        if solutions.load(key) is not None:
            members.setdefault(code, []).append(key)
    arms = list(
        await session.scalars(
            select(PiIdeaArm).where(
                *solution_ideas._where_arm(scope),
                PiIdeaArm.status == "active",
                PiIdeaArm.kind != solution_ideas.ASK,
            )
        )
    )
    best = sorted(
        (a for a in arms if int((a.stats or {}).get("n", 0)) >= NEIGHBOUR_MIN_FEEDBACK),
        key=lambda a: -learning_solutions.mean_score(a),
    )
    for arm in best:
        if learning_solutions.mean_score(arm) < NEIGHBOUR_MIN_SCORE:
            break
        mine = next(
            (p for p in (solutions.load(arm.industry_key) or {}).get("problems", [])
             if p.get("id") == arm.problem_id),
            None,
        )  # fmt: skip
        if mine is None:
            continue
        for other in sorted(members.get(sector.get(arm.industry_key, ""), [])):
            if other == arm.industry_key or counts["proposed"] >= MAX_NEIGHBOURS_PER_RUN:
                continue
            match = solution_ideas.match_problem(
                (solutions.load(other) or {}).get("problems", []),
                str(mine.get("category") or ""),
                str(mine.get("subtype") or ""),
                str(mine.get("words") or ""),
            )
            if match is None:
                continue
            fresh = await learning_solutions.add_candidate(
                session,
                scope,
                industry_key=other,
                problem_id=match["id"],
                text=arm.text,
                source="neighbour",
                evidence_ids=[str(arm.id)],
                language=arm.language,
            )
            if fresh is None:
                continue
            counts["proposed"] += 1
            await solution_versions.bump(
                session,
                scope,
                other,
                {"added": [str(fresh.id)]},
                {"source": "neighbour", "from": arm.industry_key, "problem": match["id"]},
            )
    return counts


# --- S5: a better sample reply ------------------------------------------------------------------


def fit_for_bank(person: str, pi: str) -> tuple[bool, float]:
    """A sample reply may enter the example bank only when it passes the sample checks of the
    value line and the bank's own bar (redaction at the promotion level, nothing the linter calls
    a hard violation, no named person or competitor, no social proof, no instructions).
    `learning_seed.admit` is the listening gate and would refuse every solution reply (its lint
    context forbids solutions and documents), so the same bar is applied in a solution context, to
    the reply as the model would write it: without the offer, which the application appends."""
    if solution_rules.check_sample_reply(pi, person):
        return False, 0.0
    body = solution_versions.sample_body(pi)
    confidence = min(
        learning_bank.redaction_confidence(body), learning_bank.redaction_confidence(person)
    )
    if not body or confidence < learning_rules.PROMOTE_REDACTION:
        return False, confidence
    context = {
        "pi_mode": "brain",
        "strict_voice": True,
        "flow": {"state": "S4_SORTED_SUMMARY"},
        "history": [
            {"role": "ai", "text": "I'm pi, an AI from Workzap."},
            {"role": "customer", "text": person},
        ],
        "latest_customer_message": person,
        "solution_asked": True,
    }
    if constitution.hard(constitution.lint(body, context)):
        return False, confidence
    for text in (body, person):
        if (
            learning.PERSON_OR_COMPETITOR.search(text)
            or learning.SOCIAL_PROOF.search(text)
            or learning.INJECTION.search(text)
            or learning.VALUE_LINE_ATTEMPT.search(text)
        ):
            return False, confidence
    return True, confidence


async def feed_sample(
    session: AsyncSession,
    scope: WorkspaceScope,
    industry: str,
    person: str,
    pi: str,
    language: str,
    source: str,
) -> str:
    """Put one sample reply into the example bank as a candidate (it then earns its place through
    the bank's own canary). Returns "added", "rejected" (it does not pass) or "there"."""
    ok, confidence = fit_for_bank(person, pi)
    if not ok:
        return "rejected"
    said = solution_versions.sample_body(pi)
    have = await solution_versions.sample_examples(session, scope, industry)
    if any(r.reply_text == said for r in have):
        return "there"
    session.add(
        PiLearningExample(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            message_id=None,
            source=source,
            situation={
                "state": "S4_SORTED_SUMMARY",
                "language": language,
                "turn_kind": "statement",
                **learning_situation.extras(industry, "", None),
            },
            language=language,
            person_text=person[:500],
            reply_text=said,
            reward=0,
            status="candidate",
            source_contacts=[f"solutions:{industry}"],
            redaction_confidence=Decimal(str(confidence)),
        )
    )
    await session.flush()
    return "added"


async def seed_samples(
    session: AsyncSession, scope: WorkspaceScope, industries: set[str] | None = None
) -> dict[str, int]:
    """Part 2.3: every industry's sample reply seeds the example bank, through the same gate as
    any example. By default the industries this workspace has customers in. Idempotent."""
    wanted = (
        industries
        if industries is not None
        else await learning_seed.customer_industries(session, scope)
    )
    counts = {"added": 0, "rejected": 0, "there": 0}
    for key in sorted(wanted):
        sample = (solutions.load(key) or {}).get("sample_reply")
        if not sample:
            continue
        person, pi = str(sample["person"]), str(sample["pi"])
        outcome = await feed_sample(
            session, scope, key, person, pi, detect_language(person) or "en", "solution_sample"
        )
        counts[outcome] += 1
    return counts


async def replace_samples(
    session: AsyncSession, scope: WorkspaceScope, now: datetime
) -> dict[str, int]:
    """Job S5. Real replies that earned "it worked" or "I will try" become the industry's sample
    reply when there are enough of them; the best one wins. The person's line is redacted and the
    reply passes the same checks as a sample (two ideas at most, no how-to, no claims)."""
    found: dict[str, list[tuple[int, str, str, str]]] = {}
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.last_message_at >= now - timedelta(days=30),
        )
    )
    for conversation in rows:
        for stamp in (conversation.service_brief or {}).get("learning_used") or []:
            if stamp.get("reaction") not in ("idea_worked", "idea_will_try"):
                continue
            industry = stamp.get("industry")
            reply, asked = await learning_solutions._reply_of(session, stamp)
            if not industry or reply is None or asked is None:
                continue
            body, person = reply.body or "", asked.body or ""
            if not fit_for_bank(person, body)[0] or not (_clean(person) and _clean(body)):
                continue
            if not body.rstrip().endswith("?") or len(person.split()) > 40:
                continue
            score = 2 if stamp["reaction"] == "idea_worked" else 1
            found.setdefault(industry, []).append(
                (score, person, body, str(stamp.get("language") or "en"))
            )
    replaced = 0
    for industry, picks in found.items():
        if len(picks) < SAMPLE_MIN_CANDIDATES:
            continue
        _, person, body, language = max(picks, key=lambda p: (p[0], len(p[2])))
        current = await solution_versions.current_sample(session, scope, industry) or {}
        if current.get("pi") == body:
            continue
        await solution_versions.bump(
            session,
            scope,
            industry,
            {
                "sample_reply": {
                    "from": current,
                    "to": {"person": person, "pi": body, "language": language},
                }
            },
            {"candidates": len(picks)},
        )
        # the better reply also leaves the old sample's place in the bank (S5: "replaces it in
        # the example bank"); the bank's own canary then decides whether it is used
        for old in await solution_versions.sample_examples(session, scope, industry):
            if old.status != "retired":
                old.status = "retired"
        await feed_sample(session, scope, industry, person, body, language, "solution_learned")
        replaced += 1
    return {"replaced": replaced}


# --- S6: a problem pi had no answer for ---------------------------------------------------------


async def grow_problems(
    session: AsyncSession, scope: WorkspaceScope, writer: IdeaWriter | None, now: datetime
) -> dict[str, int]:
    """Job S6. The same unmatched problem (the stamps keep its words, never the person's name)
    three times draws a new entry with two ideas from the writer. It starts in shadow: it is not
    used in chat until SHADOW_DAYS later, and a person can reject it first."""
    counts = {"drafted": 0, "promoted": 0}
    unmatched: dict[tuple[str, str], set[str]] = {}
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.last_message_at >= now - timedelta(days=30),
        )
    )
    for conversation in rows:
        for stamp in (conversation.service_brief or {}).get("learning_used") or []:
            if stamp.get("unmatched") and stamp.get("industry"):
                key = (stamp["industry"], str(stamp["unmatched"])[:60])
                unmatched.setdefault(key, set()).add(str(stamp.get("customer") or conversation.id))
    for (industry, words), people in sorted(unmatched.items()):
        n = len(people)  # distinct businesses: one owner repeating themselves is not a pattern
        if n < MIN_UNMATCHED or writer is None or counts["drafted"] >= 3:
            continue
        known = await solution_ideas.learned_problems(session, scope, industry)
        if any(k.get("words") == words for k in known):
            continue
        lines = await writer(industry, words, "en", [])
        every = [
            v
            for v in await solution_versions.versions(session, scope, industry)
            if (v.diff or {}).get("add_problem")
        ]  # rolled-back ones too: an id and its arm keys are never reused
        problem_id = f"L{len(every) + 1}"
        arm_ids: list[str] = []
        for i, line in enumerate(lines[:2]):
            verdict = solution_rules.check_idea(line)
            if not verdict.ok:
                continue
            arm = PiIdeaArm(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                arm_key=f"{industry}:{problem_id}:q{i + 1}",
                industry_key=industry,
                problem_id=problem_id,
                language="en",
                text=" ".join(line.split())[:500],
                kind=solution_rules.idea_kind(line),
                status="review" if verdict.needs_review else "shadow",
                traffic_cap=0.10,
                source="miner",
            )
            session.add(arm)
            await session.flush()
            arm_ids.append(str(arm.id))
        if len(arm_ids) == 2:
            entry = await draft_entry_fields(writer, industry, words)
            if entry.get("invalid"):
                counts["incomplete"] = counts.get("incomplete", 0) + 1
                for arm_id in arm_ids:  # the whole entry or nothing: no half-drafted problem
                    drafted = await session.get(PiIdeaArm, UUID(arm_id))
                    if drafted is not None:
                        drafted.status, drafted.retired_reason = "retired", "entry fields refused"
                continue
            if entry.get("ask_first"):
                ask = PiIdeaArm(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    arm_key=f"{industry}:{problem_id}:ask1",
                    industry_key=industry,
                    problem_id=problem_id,
                    language="en",
                    text=str(entry["ask_first"])[:500],
                    kind=solution_ideas.ASK,
                    status="shadow",
                    traffic_cap=0.10,
                    source="miner",
                )
                session.add(ask)
                await session.flush()
                arm_ids.append(str(ask.id))
            await solution_versions.bump(
                session,
                scope,
                industry,
                {
                    "add_problem": {
                        "id": problem_id,
                        "words": words,
                        "arm_ids": arm_ids,
                        **{k: v for k, v in entry.items() if k != "invalid"},
                    }
                },
                {"seen": n},
                status="shadow",
            )
            counts["drafted"] += 1
    counts["promoted"] = await promote_shadows(session, scope, now)
    return counts


async def draft_entry_fields(
    writer: IdeaWriter | None, industry: str, words: str
) -> dict[str, Any]:
    """The other fields of a drafted problem entry (Part 2.2): the Workzap build (catalogue keys
    only, said in the phrase bank's own words), the one question to ask first and where the free
    part stops. Empty when the writer does not draft them (the entry then has no build line and pi
    gives its two ideas and the document offer); {"invalid": True} when it drafted them badly."""
    drafter: EntryWriter | None = getattr(writer, "draft_entry", None)
    if drafter is None:
        return {}
    try:
        raw = await drafter(industry, words)
    except Exception:  # noqa: BLE001 - drafting is an extra, never a reason to fail a run
        logger.warning("pi_solution_entry_draft_failed", exc_info=True)
        return {"invalid": True}
    keys = [str(k) for k in (raw.get("build_keys") or [])][:2]
    ask = " ".join(str(raw.get("ask_first") or "").split())
    stops = " ".join(str(raw.get("free_stops") or "").split())
    if not keys or solution_rules.check_build_line(solutions.build_phrase(keys[0]), keys):
        return {"invalid": True}  # not in the catalogue, or too many builds (R-BUILD-05)
    if (
        not ask.endswith("?")
        or ask.count("?") != 1
        or len(ask.split()) > 30
        or solutions.banned_tool_words(ask)
        or solution_rules.has_personal_data(ask)
        or not _clean(ask)
    ):
        return {"invalid": True}
    if (
        not stops
        or len(stops.split()) > 40
        or solution_rules.HOWTO.search(stops)
        or solutions.banned_tool_words(stops)
        or not _clean(stops)
    ):
        return {"invalid": True}
    return {
        "workzap_build": {"keys": keys, "text": solutions.build_phrase(keys[0])},
        "ask_first": ask,
        "free_stops": stops,
    }


async def promote_shadows(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> int:
    """A shadow problem entry goes live after SHADOW_DAYS, unless one of its ideas still waits for
    a reviewer."""
    promoted = 0
    rows = await session.scalars(
        select(PiSolutionVersion).where(
            PiSolutionVersion.tenant_id == scope.tenant_id,
            PiSolutionVersion.environment_id == scope.environment_id,
            PiSolutionVersion.status == "shadow",
        )
    )
    for version in rows:
        ids = ((version.diff or {}).get("add_problem") or {}).get("arm_ids") or []
        if now - version.created_at < timedelta(days=SHADOW_DAYS):
            continue
        arms = [await session.get(PiIdeaArm, UUID(i)) for i in ids]
        live = [a for a in arms if a is not None and a.status in ("shadow", "testing")]
        if len(live) != len(ids) or not ids:
            continue
        for arm in live:
            arm.status = "testing"
        version.status = "live"
        # Live at the canary's 10%, on probation: `learning_solutions.evaluate_versions` takes the
        # entry back after 50 uses if its ideas score worse than the seed's (Job S6: "goes live
        # when it scores at least as well as the generic fallback")
        version.evidence = {
            **(version.evidence or {}),
            "live_at": now.isoformat(),
            "judged_against": "seed ideas, after 50 uses",
        }
        promoted += 1
    await session.flush()
    return promoted


# --- S7: failed solution chats ------------------------------------------------------------------


async def audit_failed(
    session: AsyncSession, scope: WorkspaceScope, since: datetime
) -> dict[str, int]:
    """Job S7. A reply the person met with "did not help", impatience, confusion or "too generic"
    becomes (1) a lesson, once, for a reviewer, and (2) a regression case kept in the change log
    with the person's words redacted, so the same failure is replayed against every later
    change. Nothing about the person is stored."""
    counts = {"lessons": 0, "cases": 0}
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.last_message_at >= since,
        )
    )
    for conversation in rows:
        stamps = list((conversation.service_brief or {}).get("learning_used") or [])
        for stamp in stamps:
            signal = stamp.get("reaction")
            if signal not in BAD_REACTIONS or stamp.get("audited"):
                continue
            reply, asked = await learning_solutions._reply_of(session, stamp)
            if reply is None or asked is None:
                continue
            try:
                await learning_lessons.propose(
                    session, scope, LESSONS[signal], {"signal": signal}, None, created_by="pi"
                )
                counts["lessons"] += 1
            except BusinessRuleViolation:
                pass  # the same lesson is already there or the size check refused it
            session.add(
                PiLearningChange(
                    tenant_id=scope.tenant_id,
                    environment_id=scope.environment_id,
                    kind="solution_regression",
                    risk="low",
                    before={
                        "person": solution_rules.redacted(asked.body or "")[:300]
                        if _clean(asked.body or "")
                        else "",
                        "pi": solution_rules.redacted(reply.body or "")[:600]
                        if _clean(reply.body or "")
                        else "",
                    },
                    after={"signal": signal, "industry": stamp.get("industry")},
                    status="live",
                    reason=f"failed solution chat: {signal}",
                )
            )
            counts["cases"] += 1
            stamp["audited"] = True
        brief = {**(conversation.service_brief or {}), "learning_used": stamps}
        # two more ways a solution chat fails (Part 3.4, Job S7): a request for a fix that got no
        # idea, and ideas rejected twice ("already doing that", "not possible for us")
        rejected = [s for s in stamps if s.get("reaction") in REJECTIONS]
        triggers: list[tuple[str, dict[str, Any] | None, str | None]] = []
        if brief.get("solution_unanswered") and not brief.get("unanswered_audited"):
            triggers.append(("request_unanswered", None, "unanswered_audited"))
        if len(rejected) >= 2 and not brief.get("rejected_twice_audited"):
            triggers.append(("idea_rejected_twice", rejected[-1], "rejected_twice_audited"))
        for signal, stamp_for, flag in triggers:
            pair = await _failed_pair(session, conversation, stamp_for)
            if pair is None:
                continue
            await _record_failure(
                session,
                scope,
                signal,
                pair[0],
                pair[1],
                (stamp_for or {}).get("industry") or _last_industry(brief),
            )
            counts["lessons"] += 1
            counts["cases"] += 1
            if flag:
                brief[flag] = True
        conversation.service_brief = brief
    await session.flush()
    return counts


REJECTIONS = frozenset({"idea_already_doing", "idea_not_possible"})


def _last_industry(brief: dict[str, Any]) -> str | None:
    log = brief.get("solution_unanswered") or []
    return str(log[-1].get("industry") or "") or None if log else None


async def _failed_pair(
    session: AsyncSession, conversation: PiConversation, stamp: dict[str, Any] | None
) -> tuple[PiMessage, PiMessage] | None:
    """(what the person said, pi's reply to it) for a failure that has no scored stamp of its own:
    the latest request for a fix that no idea answered, or the reply a second rejection met."""
    if stamp is not None:
        reply, asked = await learning_solutions._reply_of(session, stamp)
        return (asked, reply) if reply is not None and asked is not None else None
    inbound = list(
        await session.scalars(
            select(PiMessage)
            .where(PiMessage.conversation_id == conversation.id, PiMessage.direction == "inbound")
            .order_by(PiMessage.created_at.desc())
            .limit(30)
        )
    )
    for message in inbound:
        if not solution_ask.asked_for_ideas(message.body or ""):
            continue
        after = await session.scalar(
            select(PiMessage)
            .where(
                PiMessage.conversation_id == conversation.id,
                PiMessage.direction == "outbound",
                PiMessage.created_at > message.created_at,
            )
            .order_by(PiMessage.created_at)
            .limit(1)
        )
        if after is not None:
            return message, after
    return None


async def _record_failure(
    session: AsyncSession,
    scope: WorkspaceScope,
    signal: str,
    asked: PiMessage,
    reply: PiMessage,
    industry: str | None,
) -> None:
    """One lesson for a reviewer (once) and one regression case with the words redacted."""
    try:
        await learning_lessons.propose(
            session, scope, LESSONS[signal], {"signal": signal}, None, created_by="pi"
        )
    except BusinessRuleViolation:
        pass  # the same lesson is already there or the size check refused it
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="solution_regression",
            risk="low",
            before={
                "person": solution_rules.redacted(asked.body or "")[:300]
                if _clean(asked.body or "")
                else "",
                "pi": solution_rules.redacted(reply.body or "")[:600]
                if _clean(reply.body or "")
                else "",
            },
            after={"signal": signal, "industry": industry},
            status="live",
            reason=f"failed solution chat: {signal}",
        )
    )


# --- weekly review: catalogue gaps and which build fits (Parts 3.5 and 3.6) ----------------------

CATALOGUE_BUSINESSES = 3  # distinct businesses with the same unmet need, across industries
BUILD_OUTCOMES = {
    "document_approved": "doc_approved",
    "quote_accepted": "accepted",
    "project_delivered": "delivered",
}


async def propose_catalogue(
    session: AsyncSession, scope: WorkspaceScope, now: datetime
) -> dict[str, int]:
    """When the same unmatched need (its words, never a name) comes from three distinct
    businesses, in one industry or several, pi proposes a catalogue entry to a person: how often
    and in which industries. Only a person can add it (Part 3.5)."""
    seen: dict[str, dict[str, set[str]]] = {}
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
            PiConversation.last_message_at >= now - timedelta(days=30),
        )
    )
    for conversation in rows:
        for stamp in (conversation.service_brief or {}).get("learning_used") or []:
            if stamp.get("unmatched") and stamp.get("industry"):
                group = seen.setdefault(
                    str(stamp["unmatched"])[:60], {"who": set(), "in": set(), "ev": set()}
                )
                group["who"].add(str(stamp.get("customer") or conversation.id))
                group["in"].add(str(stamp["industry"]))
                group["ev"].add(str(conversation.id))
    counts = {"proposed": 0, "updated": 0}
    for words, group in sorted(seen.items()):
        if len(group["who"]) < CATALOGUE_BUSINESSES:
            continue
        have = await session.scalar(
            select(PiCatalogueProposal).where(
                PiCatalogueProposal.tenant_id == scope.tenant_id,
                PiCatalogueProposal.environment_id == scope.environment_id,
                PiCatalogueProposal.need_text == words,
            )
        )
        if have is not None:
            if have.status == "open" and len(group["who"]) > have.count:
                have.count = len(group["who"])
                have.industries = sorted(group["in"])
                counts["updated"] += 1
            continue
        session.add(
            PiCatalogueProposal(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                need_text=words,
                industries=sorted(group["in"]),
                count=len(group["who"]),
                evidence_ids=sorted(group["ev"])[:20],
            )
        )
        counts["proposed"] += 1
    await session.flush()
    return counts


async def record_build_fit(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    event: str,
    project_id: UUID | None = None,
) -> PiBuildFit | None:
    """Part 3.6: when a solution document is approved, a quote accepted or a project delivered
    (`event` is one of BUILD_OUTCOMES), record problem to build for that customer's industry. The
    build is the one pi named for the problem. A reviewer confirms it (`confirm_build_fit`). It
    never enters the chat score: nothing here is read by the idea scoring, and `solution_score`
    ignores these events whatever a caller passes. None when pi gave this business no idea."""
    from app.modules.customers.models import Customer

    outcome = BUILD_OUTCOMES.get(event)
    customer = await session.get(Customer, customer_id)
    if outcome is None or customer is None or not customer.industry_primary:
        return None
    memory = await solution_ideas.remembered(session, scope, customer_id)
    if not memory:
        return None
    latest = max(memory, key=lambda m: m.given_at)
    keys = list(latest.builds_mentioned or [])
    if not keys:
        entry = {
            e["id"]: e for e in await solution_ideas.entries(session, scope, latest.industry_key)
        }.get(latest.problem_id)
        keys = list(((entry or {}).get("workzap_build") or {}).get("keys") or [])[:1]
    if not keys:
        return None
    existing = await session.scalar(
        select(PiBuildFit).where(
            PiBuildFit.tenant_id == scope.tenant_id,
            PiBuildFit.environment_id == scope.environment_id,
            PiBuildFit.industry_key == latest.industry_key,
            PiBuildFit.problem_key == latest.problem_id,
            PiBuildFit.catalogue_key == str(keys[0]),
            PiBuildFit.project_id.is_(None)
            if project_id is None
            else PiBuildFit.project_id == project_id,
        )
    )
    if existing is not None:
        if existing.confirmed_by is None and existing.outcome != outcome:
            existing.outcome = outcome  # the same fit, further along
        return existing
    row = PiBuildFit(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        industry_key=latest.industry_key,
        problem_key=latest.problem_id,
        catalogue_key=str(keys[0]),
        project_id=project_id,
        outcome=outcome,
    )
    session.add(row)
    await session.flush()
    return row


async def confirm_build_fit(
    session: AsyncSession, row: PiBuildFit, reviewer: UUID | None, approve: bool
) -> PiBuildFit:
    """A reviewer's decision on one recorded fit. A rejected one stays as a record, outcome
    "rejected", and never counts as a fit."""
    if approve:
        row.confirmed_by = reviewer
    else:
        row.outcome = "rejected"
    await session.flush()
    return row


# --- the model that writes candidate ideas ------------------------------------------------------


class Ideas(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ideas: list[str] = Field(default_factory=list, max_length=4)


SYSTEM = """You write free one-line ideas for pi, Workzap's WhatsApp AI, to give a small business
owner about one problem. You get the industry, the problem, a language and the ideas already in use.
Write 2 new ones in that language: each is ONE short sentence, what to do plus why, in everyday
words, a different kind of idea from the ones in use. No steps, no settings, no numbers, no amounts,
no promises, no app or tool names, no mention of Workzap, nothing that needs a system. Roman Urdu
stays Roman Urdu. Return only the structured result."""


def make_writer(settings: Any, http: Any, scope: WorkspaceScope) -> IdeaWriter | None:
    if http is None:
        return None

    async def write(industry: str, problem: str, language: str, current: list[str]) -> list[str]:
        from app.ai.manager import LLMManager
        from app.ai.types import Message
        from app.ai.usage import NullUsageStore

        try:
            manager = LLMManager(settings, http, usage=NullUsageStore())
            result = await manager.complete_structured(
                scope,
                Ideas,
                alias="fast",
                purpose="pi_solution_miner",
                messages=[
                    Message.system(SYSTEM),
                    Message.user(
                        json.dumps(
                            {
                                "industry": industry,
                                "problem": problem,
                                "language": language,
                                "in_use": current,
                            },
                            ensure_ascii=False,
                        )
                    ),
                ],
                temperature=0.7,
                max_tokens=400,
            )
        except Exception:  # noqa: BLE001 - mining is an extra, never a reason to fail a run
            logger.warning("pi_solution_miner_failed", exc_info=True)
            return []
        value = result.value
        return list(value.ideas) if isinstance(value, Ideas) else []

    async def draft(industry: str, words: str) -> dict[str, Any]:
        from app.ai.manager import LLMManager
        from app.ai.types import Message
        from app.ai.usage import NullUsageStore

        try:
            manager = LLMManager(settings, http, usage=NullUsageStore())
            result = await manager.complete_structured(
                scope,
                EntryDraft,
                alias="fast",
                purpose="pi_solution_entry",
                messages=[
                    Message.system(
                        ENTRY_SYSTEM.replace("KEYS", ", ".join(sorted(solutions.CATALOGUE)))
                    ),
                    Message.user(
                        json.dumps({"industry": industry, "problem": words}, ensure_ascii=False)
                    ),
                ],
                temperature=0.4,
                max_tokens=300,
            )
        except Exception:  # noqa: BLE001 - drafting is an extra, never a reason to fail a run
            logger.warning("pi_solution_entry_failed", exc_info=True)
            return {}
        value = result.value
        return value.model_dump() if isinstance(value, EntryDraft) else {}

    setattr(write, "draft_entry", draft)  # noqa: B010 - an optional second step of the writer
    return write


class EntryDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    build_keys: list[str] = Field(default_factory=list, max_length=2)
    ask_first: str = ""
    free_stops: str = ""


ENTRY_SYSTEM = """You complete a new problem entry for pi, Workzap's WhatsApp AI. You get an
industry and the owners' words for a problem. Return: build_keys, one or two keys from this list
only: KEYS;
ask_first, ONE short plain question (one sentence, no numbers) to ask first when the facts are thin;
free_stops, ONE short sentence naming two or three things the solution document settles that pi
does not give for free (the how, never steps). No tool words (dashboard, system, software,
platform, app), no amounts, no promises. Return only the structured result."""


async def run_all(
    session: AsyncSession,
    scope: WorkspaceScope,
    since: datetime,
    now: datetime,
    writer: IdeaWriter | None,
) -> dict[str, Any]:
    """S1 to S8 in order, plus the weekly review items. The nightly gate calls this only when
    learning is not frozen. When the release gate (`learning_gate`) last failed, nothing is
    promoted, nothing goes from shadow to live and no version is bumped; scoring, the
    leaderboards, retiring a bad idea, an automatic rollback and the audit still run, because
    they only make pi safer."""
    held = {"held": "the release gate is failing"}
    allowed = await learning_gate.allows(session, scope)
    digest: dict[str, Any] = {"scored": await learning_solutions.score_replies(session, scope, now)}
    digest["gate"] = "open" if allowed else "held"
    digest["leaderboard"] = await learning_solutions.update_leaderboards(session, scope)
    digest["canary"] = await learning_solutions.promote_ideas(session, scope) if allowed else held
    digest["auto_rollback"] = await learning_solutions.evaluate_versions(session, scope, now)
    digest["retired"] = await learning_solutions.retire_ideas(session, scope)
    digest["ask_first"] = await learning_solutions.learn_ask_first(session, scope)
    if allowed:
        digest["found"] = await find_ideas(session, scope, writer)
        digest["neighbours"] = await neighbour_ideas(session, scope)
        digest["sample_seeds"] = await seed_samples(session, scope)
        digest["samples"] = await replace_samples(session, scope, now)
        digest["grown"] = await grow_problems(session, scope, writer, now)
    else:
        digest["found"] = digest["neighbours"] = digest["samples"] = digest["grown"] = held
    digest["audit"] = await audit_failed(session, scope, since)
    digest["review"] = {
        **await learning_solutions.flag_unhelpful(session, scope),
        **{"catalogue_" + k: v for k, v in (await propose_catalogue(session, scope, now)).items()},
    }
    return digest


async def note_build_fit(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    event: str,
    project_id: UUID | None = None,
) -> None:
    """`record_build_fit` for the places where the event happens (document approved, quote
    accepted): it can never fail the turn or the approval, and a workspace whose solution tables
    are not migrated yet is simply skipped."""
    try:
        async with session.begin_nested():
            await record_build_fit(
                session, scope, customer_id=customer_id, event=event, project_id=project_id
            )
    except Exception:  # noqa: BLE001 - learning is an extra, never a reason to fail the event
        logger.warning("pi_build_fit_skipped", exc_info=True)
