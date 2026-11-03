"""Candidate lessons from what owners say about the ideas pi gave in real chats (A2 Part 3, 8.2).

The idea leaderboards (`learning_solutions`) only learn from ideas that came out of the idea-arm
library, so an idea the model wrote itself, or one from a pack, was never scored. This job looks at
every reply that gave ideas (bulleted, numbered or told in order), reads what the person said next
with the same classifier (`solution_score.classify`) and turns a clear reaction into a *candidate*
lesson: "an owner said this idea was already being done: <the idea>. Offer another angle."

A candidate is never live and never a canary. It waits in the Teach pi list for a person to approve
or reject it (`learning_lessons.propose(hold=...)`). Nothing is written to the chat before that, so
the reply linter and the never-learn list are the only gates a candidate needs to pass first: the
idea text must carry no personal data (redaction bar 0.98) and nothing the never-learn list refuses.
Runs inside the nightly gate and stops while learning is frozen.
"""

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning,
    learning_bank,
    learning_lessons,
    solution_rules,
    solution_score,
)
from app.modules.pi.language import detect_language
from app.modules.pi.learning_models import PiLearningLesson
from app.modules.pi.models import PiMessage
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

LOOKBACK = timedelta(days=3)  # a reaction can come a day or two after the ideas
NEXT_MESSAGES = 3
MAX_NEW_PER_RUN = 5
REDACTION_BAR = 0.98
BULLETS = ("•", "- ", "* ")
# what the person said -> how the candidate lesson says it
SAYS = {
    "idea_no_help": "did not help when an owner tried it",
    "idea_already_doing": "is something the owner was already doing",
    "idea_generic": "felt too generic to an owner",
    "idea_not_possible": "is not possible for the owner's business",
    "idea_worked": "worked for an owner",
}
ADVICE = {
    "idea_worked": "It is a good one to offer first.",
}
DEFAULT_ADVICE = "Offer a different angle next time."
HOLD = "from a real chat: waits for a person in Teach pi"


def ideas_of(reply: str) -> list[str]:
    """The idea sentences of a reply, one per bullet or numbered line."""
    out: list[str] = []
    for line in (reply or "").splitlines():
        text = line.strip()
        if text.startswith(BULLETS):
            text = text.lstrip("•-* ").strip()
        elif text[:2].rstrip(".)").isdigit() and text[1:3].strip().startswith((".", ")")):
            text = text[2:].lstrip(". )").strip()
        else:
            continue
        if text:
            out.append(text)
    return out


def lesson_text(signal: str, ideas: list[str]) -> str:
    """The candidate lesson in plain words, within the lesson size."""
    advice = ADVICE.get(signal, DEFAULT_ADVICE)
    head = f"An idea like this {SAYS[signal]}: "
    room = learning_lessons.MAX_LENGTH - len(head) - len(advice) - 4
    # A capital in the middle of a sentence looks like a name to the redaction check: an idea's own
    # first capital is dropped, the rest stays as pi wrote it.
    quoted = " / ".join(i[:1].lower() + i[1:] if i[1:2].islower() else i for i in ideas).rstrip(".")
    if len(quoted) > room:
        quoted = quoted[: max(room - 1, 0)].rstrip() + "…"
    return f"{head}“{quoted}”. {advice}"


async def _nexts(session: AsyncSession, reply: PiMessage) -> list[str]:
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
    return [m.body or "" for m in rows if (m.body or "").strip()]


async def mine(
    session: AsyncSession, scope: WorkspaceScope, since: datetime, now: datetime
) -> dict[str, int]:
    """New candidate lessons from the replies that gave ideas since the last run. Counts."""
    counts: Counter[str] = Counter()
    replies = list(
        await session.scalars(
            select(PiMessage)
            .where(
                PiMessage.tenant_id == scope.tenant_id,
                PiMessage.environment_id == scope.environment_id,
                PiMessage.direction == "outbound",
                PiMessage.sender_type == "ai",
                PiMessage.created_at >= since - LOOKBACK,
                PiMessage.created_at <= now,
            )
            .order_by(PiMessage.created_at)
        )
    )
    have = {
        text
        for (text,) in await session.execute(
            select(PiLearningLesson.text).where(
                PiLearningLesson.tenant_id == scope.tenant_id,
                PiLearningLesson.environment_id == scope.environment_id,
            )
        )
    }
    added = 0
    for reply in replies:
        body = reply.body or ""
        if solution_rules.count_ideas(body) == 0:
            continue
        counts["gave_ideas"] += 1
        ideas = ideas_of(body)
        if not ideas:
            counts["no_idea_lines"] += 1
            continue
        reaction = next(
            (
                r
                for text in await _nexts(session, reply)
                if (r := solution_score.classify(text)) is not None and r.signal in SAYS
            ),
            None,
        )
        if reaction is None:
            continue
        counts["reacted"] += 1
        text = lesson_text(reaction.signal, ideas)
        if text in have:
            counts["already_have"] += 1
            continue
        if learning.never_learn(text) or learning_bank.redaction_confidence(text) < REDACTION_BAR:
            counts["refused"] += 1  # personal data or something pi may never learn
            continue
        if added >= MAX_NEW_PER_RUN:
            counts["over_cap"] += 1
            continue
        situation: dict[str, str] = {"language": detect_language(" ".join(ideas)) or "en"}
        try:
            await learning_lessons.propose(
                session, scope, text, situation, None, "nightly", hold=HOLD
            )
        except BusinessRuleViolation:
            counts["refused"] += 1
            continue
        have.add(text)
        added += 1
        counts["proposed"] += 1
    return dict(counts)
