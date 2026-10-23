"""What the solution ideas add to one turn's context (Addendum 2 to the pi Brain v3, Parts 2 and 3).

Only when the workspace set `response_rules.brain.solution_mode` to true. Then, once the problems
are sorted (S4 or S5, never while pi is still listening), pi may be handed at most two ideas for
the problem the person cares about, chosen by `solution_ideas.choose`: none they have had, none of
a kind they rejected, the better ones more often. A returning customer is greeted with their last
ideas instead (the follow-up is the one question of that message). The counts of the value line
are enforced here: a conversation never gets more than IDEAS_BEFORE_OFFER ideas. Which ideas were
handed over is stamped on the conversation, so the nightly run can score them by what the person
says next.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    flow,
    learning_bank,
    learning_rules,
    solution_ideas,
    solutions,
    value_line,
)
from app.modules.pi.language import detect_language
from app.modules.pi.models import PiConversation
from app.shared.scope import WorkspaceScope

GIVING = {flow.State.S4_SORTED_SUMMARY.value, flow.State.S5_READINESS.value}


def switched_on(response_rules: dict[str, Any] | None) -> bool:
    rules = response_rules or {}
    return (
        rules.get("pi_mode") == "brain" and (rules.get("brain") or {}).get("solution_mode") is True
    )


def given_so_far(conversation: PiConversation) -> int:
    """Ideas handed over in this chat. Kept in the brief, apart from the stamps, which are
    trimmed to the last few: a long chat must never reset the count (R-VAL-02)."""
    return int((conversation.service_brief or {}).get("ideas_given") or 0)


async def build(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    noted: list[dict[str, Any]],
    used: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Context keys `solution_ideas`, `solution_followup`, `solution_exhausted` (each may be
    missing); fills `used` with the stamp for the nightly scoring. Never raises: before migration
    0043 is applied the tables are missing and pi simply gives no ideas."""
    try:
        async with session.begin_nested():
            return await _build(session, scope, conversation, said, noted, used, now)
    except ProgrammingError:
        return {}


async def _build(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    said: str,
    noted: list[dict[str, Any]],
    used: dict[str, Any],
    now: datetime | None,
) -> dict[str, Any]:
    from app.modules.customers.models import Customer

    if conversation.customer_id is None:
        return {}
    customer = await session.get(Customer, conversation.customer_id)
    industry = customer.industry_primary if customer is not None else None
    if not industry or solutions.load(industry) is None:
        return {}
    language = detect_language(said) or conversation.language or "en"
    language = language if language in ("en", "roman_ur", "ar") else "en"
    await solution_ideas.ensure_arms(session, scope, industry)
    used["industry"] = industry
    used["language"] = language
    brief = conversation.service_brief or {}
    if not brief.get("solution_followup_done"):
        back = await solution_ideas.continuity(
            session, scope, customer_id=conversation.customer_id, now=now or datetime.now(UTC)
        )
        if back is not None:
            conversation.service_brief = {**brief, "solution_followup_done": True}
            return {"solution_followup": back}
    if (conversation.flow_state or "") not in GIVING or not noted:
        return {}
    if given_so_far(conversation) >= value_line.IDEAS_BEFORE_OFFER:
        return {}
    latest = noted[-1]
    problem = solution_ideas.match_problem(
        await solution_ideas.entries(session, scope, industry),
        str(latest.get("group") or ""),
        "",
        str(latest.get("title") or ""),
    )
    if problem is None:
        words = " ".join(str(latest.get("title") or "").lower().split()[:8])
        if words and learning_bank.redaction_confidence(words) >= learning_rules.PROMOTE_REDACTION:
            used["unmatched"] = words  # only words with no name, figure or contact in them
            used["customer"] = str(conversation.customer_id)
        return {}
    left = value_line.IDEAS_BEFORE_OFFER - given_so_far(conversation)
    choice = await solution_ideas.choose(
        session,
        scope,
        industry_key=industry,
        problem_id=problem["id"],
        language=language,
        customer_id=conversation.customer_id,
        count=min(value_line.IDEAS_PER_MESSAGE, left),
    )
    if not choice.arms:
        return {"solution_exhausted": True} if choice.exhausted else {}
    used["ideas"] = [str(a.id) for a in choice.arms]
    used["problem_id"] = problem["id"]
    used["state"] = conversation.flow_state
    # Remember at once what is handed over, so the same idea is never offered twice in one chat
    # (the nightly scoring only adds what the person said about it).
    await solution_ideas.record_given(
        session,
        scope,
        customer_id=conversation.customer_id,
        conversation_id=conversation.id,
        arms=choice.arms,
        now=now or datetime.now(UTC),
    )
    used["recorded"] = True
    conversation.service_brief = {
        **(conversation.service_brief or {}),
        "ideas_given": given_so_far(conversation) + len(choice.arms),
    }
    return {"solution_ideas": [a.text for a in choice.arms]}
