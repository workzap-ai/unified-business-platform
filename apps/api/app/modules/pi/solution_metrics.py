"""The learning metrics of the Solutions panel (Addendum 2 to the pi Brain v3, Part 3.10).

Read only. Rates are shares of the feedback rows (one row per reaction to an idea); the others
count rows of the idea, memory and chat stores. Offer acceptance is deliberately absent: it is
reported elsewhere and never optimised (Part 3.2 and 3.6). Nothing here writes, and nothing here
feeds a score.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import solution_ideas, solution_versions
from app.modules.pi.models import PiConversation
from app.modules.pi.solution_models import PiIdeaArm, PiIdeaFeedback, PiSolutionMemory
from app.shared.scope import WorkspaceScope

ENGAGED = ("idea_will_try", "idea_followup", "idea_more", "idea_worked")
RATES = {
    "generic_rate": ("idea_generic",),
    "already_tried_rate": ("idea_already_doing",),
    "no_help_rate": ("idea_no_help",),
    "impatience_rate": ("idea_impatient",),
}


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def _block() -> dict[str, Any]:
    return {
        "feedback": 0,
        "engagement_rate": 0.0,
        "generic_rate": 0.0,
        "already_tried_rate": 0.0,
        "no_help_rate": 0.0,
        "impatience_rate": 0.0,
        "worked_reports": 0,
        "requests_unanswered": 0,
        "ideas_per_conversation": 0.0,
        "ideas_added": 0,
        "ideas_retired": 0,
        "sample_replies_learned": 0,
    }


async def compute(
    session: AsyncSession, scope: WorkspaceScope, industry: str | None = None
) -> dict[str, Any]:
    """The metrics overall and per industry (one industry only when `industry` is given)."""
    blocks: dict[str, dict[str, Any]] = defaultdict(_block)
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    feedback = select(PiIdeaFeedback.industry_key, PiIdeaFeedback.signal, func.count()).where(
        PiIdeaFeedback.tenant_id == scope.tenant_id,
        PiIdeaFeedback.environment_id == scope.environment_id,
    )
    if industry:
        feedback = feedback.where(PiIdeaFeedback.industry_key == industry)
    for key, signal, n in await session.execute(
        feedback.group_by(PiIdeaFeedback.industry_key, PiIdeaFeedback.signal)
    ):
        counts[key]["_all"] += n
        counts[key][signal] += n

    memory = select(
        PiSolutionMemory.industry_key,
        PiSolutionMemory.conversation_id,
        func.count(),
    ).where(
        PiSolutionMemory.tenant_id == scope.tenant_id,
        PiSolutionMemory.environment_id == scope.environment_id,
    )
    if industry:
        memory = memory.where(PiSolutionMemory.industry_key == industry)
    chats: dict[str, list[int]] = defaultdict(list)
    for key, _conversation, n in await session.execute(
        memory.group_by(PiSolutionMemory.industry_key, PiSolutionMemory.conversation_id)
    ):
        chats[key].append(n)

    arms = select(PiIdeaArm.industry_key, PiIdeaArm.status, PiIdeaArm.source, func.count()).where(
        *solution_ideas._where_arm(scope), PiIdeaArm.kind != solution_ideas.ASK
    )
    if industry:
        arms = arms.where(PiIdeaArm.industry_key == industry)
    for key, status, source, n in await session.execute(
        arms.group_by(PiIdeaArm.industry_key, PiIdeaArm.status, PiIdeaArm.source)
    ):
        if source != "seed":
            counts[key]["_added"] += n
        if status == "retired":
            counts[key]["_retired"] += n

    unanswered: dict[str, int] = defaultdict(int)
    rows = await session.scalars(
        select(PiConversation).where(
            PiConversation.tenant_id == scope.tenant_id,
            PiConversation.environment_id == scope.environment_id,
        )
    )
    for conversation in rows:
        for miss in (conversation.service_brief or {}).get("solution_unanswered") or []:
            key = str(miss.get("industry") or "")
            if not industry or key == industry:
                unanswered[key] += 1

    learned_samples: dict[str, int] = defaultdict(int)
    if industry:
        found = [industry]
    else:
        found = sorted({*counts, *chats, *unanswered} - {""})
    for key in found:
        if any(
            v.status == "live" and (v.diff or {}).get("sample_reply")
            for v in await solution_versions.versions(session, scope, key)
        ):
            learned_samples[key] = 1

    for key in sorted({*counts, *chats, *unanswered, *learned_samples}):
        c, block = counts[key], blocks[key]
        total = c["_all"]
        block["feedback"] = total
        block["engagement_rate"] = _rate(sum(c[s] for s in ENGAGED), total)
        for name, signals in RATES.items():
            block[name] = _rate(sum(c[s] for s in signals), total)
        block["worked_reports"] = c["idea_worked"]
        block["requests_unanswered"] = unanswered.get(key, 0)
        block["ideas_per_conversation"] = (
            round(sum(chats[key]) / len(chats[key]), 2) if chats[key] else 0.0
        )
        block["ideas_added"] = c["_added"]
        block["ideas_retired"] = c["_retired"]
        block["sample_replies_learned"] = learned_samples.get(key, 0)

    overall = _block()
    grand: dict[str, int] = defaultdict(int)
    for per in counts.values():
        for name, n in per.items():
            grand[name] += n
    overall["feedback"] = grand["_all"]
    overall["engagement_rate"] = _rate(sum(grand[s] for s in ENGAGED), grand["_all"])
    for name, signals in RATES.items():
        overall[name] = _rate(sum(grand[s] for s in signals), grand["_all"])
    overall["worked_reports"] = grand["idea_worked"]
    overall["ideas_added"] = grand["_added"]
    overall["ideas_retired"] = grand["_retired"]
    overall["sample_replies_learned"] = sum(learned_samples.values())
    sizes = [n for sizes in chats.values() for n in sizes]
    overall["ideas_per_conversation"] = round(sum(sizes) / len(sizes), 2) if sizes else 0.0
    # misses with no known industry still count overall
    overall["requests_unanswered"] = sum(unanswered.values())
    return {"overall": overall, "industries": dict(sorted(blocks.items()))}
