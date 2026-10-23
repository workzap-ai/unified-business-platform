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
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning_bank,
    learning_lessons,
    learning_rules,
    learning_solutions,
    solution_ideas,
    solution_rules,
    solution_versions,
    solutions,
)
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiConversation
from app.modules.pi.solution_models import PiIdeaArm
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

# (industry, problem label, language, ideas already live) -> new one-line ideas
IdeaWriter = Callable[[str, str, str, list[str]], Awaitable[list[str]]]
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


# --- S5: a better sample reply ------------------------------------------------------------------


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
            bad_reply = solution_rules.check_sample_reply(body, person)
            if bad_reply or not (_clean(person) and _clean(body)):
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
            await solution_versions.bump(
                session,
                scope,
                industry,
                {"add_problem": {"id": problem_id, "words": words, "arm_ids": arm_ids}},
                {"seen": n},
                status="shadow",
            )
            counts["drafted"] += 1
    counts["promoted"] = await promote_shadows(session, scope, now)
    return counts


async def promote_shadows(session: AsyncSession, scope: WorkspaceScope, now: datetime) -> int:
    """A shadow problem entry goes live after SHADOW_DAYS, unless one of its ideas still waits for
    a reviewer."""
    from app.modules.pi.solution_models import PiSolutionVersion

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
        conversation.service_brief = {**(conversation.service_brief or {}), "learning_used": stamps}
    await session.flush()
    return counts


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

    return write


async def run_all(
    session: AsyncSession,
    scope: WorkspaceScope,
    since: datetime,
    now: datetime,
    writer: IdeaWriter | None,
) -> dict[str, Any]:
    """S1 to S8 in order. The nightly gate calls this only when learning is not frozen."""
    digest: dict[str, Any] = {"scored": await learning_solutions.score_replies(session, scope, now)}
    digest["leaderboard"] = await learning_solutions.update_leaderboards(session, scope)
    digest["retired"] = await learning_solutions.retire_ideas(session, scope)
    digest["ask_first"] = await learning_solutions.learn_ask_first(session, scope)
    digest["found"] = await find_ideas(session, scope, writer)
    digest["samples"] = await replace_samples(session, scope, now)
    digest["grown"] = await grow_problems(session, scope, writer, now)
    digest["audit"] = await audit_failed(session, scope, since)
    return digest
