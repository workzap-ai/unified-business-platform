"""Drift monitor (pi Brain spec 8.9, eval L13).

Once a week, pi's recent replies are compared with a reference window from the weeks before, and
with a frozen reference that never moves, so slow creep (a little longer every week) is caught as
well as a sudden jump. The frozen reference is stored once: the golden conversations' replies set
the baseline for questions, emoji and language, and the first full week of real replies sets the
baseline for length. If the style drifted (longer messages, more questions, more emoji,
more English where the person writes Urdu) learning is frozen, a change is logged and staff are
told. The freeze stops every automatic change; pi keeps working on the last good versions.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import constitution, learning, learning_seed, spec_handbook
from app.modules.pi.language import detect_language
from app.modules.pi.learning_models import PiLearningChange
from app.modules.pi.models import PiConversation, PiMessage, PiSettings
from app.shared.scope import WorkspaceScope

CURRENT_DAYS = 7
REFERENCE_FROM_DAYS = 36
CHECK_EVERY = timedelta(days=7)
MIN_REPLIES = 30  # each window needs this many replies before anything can be said
LENGTH_LIMIT = 0.30  # replies 30% longer than the reference
QUESTION_RISE = 0.10  # more replies with two questions or more, absolute share
EMOJI_RISE = 0.10
ENGLISH_RISE = 0.15  # replies in English to people who write Roman Urdu


@dataclass(frozen=True)
class Stats:
    replies: int
    words: float
    many_questions: float
    emoji: float
    english_to_urdu: float


def stats(rows: Sequence[tuple[str, str]]) -> Stats:
    """(reply text, the language of the chat) pairs -> the style numbers."""
    n = len(rows)
    if not n:
        return Stats(0, 0.0, 0.0, 0.0, 0.0)
    words = sum(len(text.split()) for text, _ in rows) / n
    many = sum(1 for text, _ in rows if text.count("?") + text.count("؟") > 1) / n
    emoji = sum(1 for text, _ in rows if constitution.EMOJI.search(text)) / n
    urdu = [text for text, language in rows if language == "roman_ur"]
    english = sum(1 for text in urdu if detect_language(text) == "en") / len(urdu) if urdu else 0.0
    return Stats(n, words, many, emoji, english)


def drift(reference: Stats, current: Stats) -> list[str]:
    """What drifted, by name. Empty when either window is too small to judge."""
    if reference.replies < MIN_REPLIES or current.replies < MIN_REPLIES:
        return []
    found: list[str] = []
    if learning.drifted([round(current.words)], [round(reference.words)], LENGTH_LIMIT):
        found.append("longer replies")
    if current.many_questions - reference.many_questions > QUESTION_RISE:
        found.append("more replies with several questions")
    if current.emoji - reference.emoji > EMOJI_RISE:
        found.append("more emoji")
    if current.english_to_urdu - reference.english_to_urdu > ENGLISH_RISE:
        found.append("more English for people who write Roman Urdu")
    return found


REFERENCE_KIND = "drift_reference"
MIN_GOLDEN = 5


def golden_stats() -> Stats:
    """The style numbers of pi's replies in the golden conversations (spec 10.1)."""
    rows: list[tuple[str, str]] = []
    for gid, item in spec_handbook.sections().items():
        if not (gid.startswith("G") and gid[1:].isdigit()):
            continue
        for person, reply in learning_seed.pairs(learning_seed.split_turns(item.get("text", ""))):
            rows.append((reply, detect_language(person) or "en"))
    return stats(rows)


def drift_from_frozen(golden: Stats, first_window: Stats | None, current: Stats) -> list[str]:
    """What drifted from the frozen reference: more questions, emoji or English for Roman Urdu
    people than the golden replies show, or replies longer than the first real week."""
    found: list[str] = []
    if current.replies < MIN_REPLIES:
        return found
    if golden.replies >= MIN_GOLDEN:
        if current.many_questions - golden.many_questions > QUESTION_RISE:
            found.append("more replies with several questions than the frozen reference")
        if current.emoji - golden.emoji > EMOJI_RISE:
            found.append("more emoji than the frozen reference")
        if current.english_to_urdu - golden.english_to_urdu > ENGLISH_RISE:
            found.append("more English for Roman Urdu people than the frozen reference")
    if (
        first_window is not None
        and first_window.replies >= MIN_REPLIES
        and learning.drifted([round(current.words)], [round(first_window.words)], LENGTH_LIMIT)
    ):
        found.append("replies longer than the frozen reference")
    return found


async def _frozen_reference(
    session: AsyncSession, scope: WorkspaceScope, current: Stats
) -> tuple[Stats, Stats | None]:
    """The stored frozen reference (made once). The first week with enough replies is added to it
    once, and never changed after."""
    row = await session.scalar(
        select(PiLearningChange)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.kind == REFERENCE_KIND,
        )
        .limit(1)
    )
    if row is None:
        golden = golden_stats()
        row = PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind=REFERENCE_KIND,
            risk="low",
            before={},
            after={},
            evidence={"golden": golden.__dict__, "first_window": None},
            status="live",
            reason="frozen drift reference stored once",
        )
        session.add(row)
    evidence = dict(row.evidence or {})
    if evidence.get("first_window") is None and current.replies >= MIN_REPLIES:
        evidence["first_window"] = current.__dict__
        row.evidence = evidence
    first = evidence.get("first_window")
    return Stats(**evidence["golden"]), Stats(**first) if first else None


async def _window(
    session: AsyncSession, scope: WorkspaceScope, start: datetime, end: datetime
) -> Stats:
    rows = await session.execute(
        select(PiMessage.body, PiConversation.language)
        .join(PiConversation, PiConversation.id == PiMessage.conversation_id)
        .where(
            PiMessage.tenant_id == scope.tenant_id,
            PiMessage.environment_id == scope.environment_id,
            PiMessage.direction == "outbound",
            PiMessage.sender_type == "ai",
            PiMessage.created_at >= start,
            PiMessage.created_at < end,
        )
    )
    pairs = [
        (re.sub(r"\s+", " ", body or "").strip(), language or "en")
        for body, language in rows
        if (body or "").strip()
    ]
    return stats(pairs)


async def check(
    session: AsyncSession,
    scope: WorkspaceScope,
    settings: PiSettings,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The weekly check. Freezes learning (and says why) when pi's style drifted."""
    now = now or datetime.now(UTC)
    last = await session.scalar(
        select(PiLearningChange.created_at)
        .where(
            PiLearningChange.tenant_id == scope.tenant_id,
            PiLearningChange.environment_id == scope.environment_id,
            PiLearningChange.kind == "drift_check",
        )
        .order_by(PiLearningChange.created_at.desc())
        .limit(1)
    )
    if last is not None and now - last < CHECK_EVERY:
        return {"checked": False}
    current = await _window(session, scope, now - timedelta(days=CURRENT_DAYS), now)
    reference = await _window(
        session,
        scope,
        now - timedelta(days=REFERENCE_FROM_DAYS),
        now - timedelta(days=CURRENT_DAYS),
    )
    found = drift(reference, current)
    golden, first_window = await _frozen_reference(session, scope, current)
    found += [d for d in drift_from_frozen(golden, first_window, current) if d not in found]
    session.add(
        PiLearningChange(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            kind="drift_check",
            risk="low",
            before={},
            after={"drifted": found},
            evidence={
                "reference": reference.__dict__,
                "current": current.__dict__,
            },
            status="live" if not found else "review",
            reason=", ".join(found) or "no drift",
        )
    )
    if found:
        rules = dict(settings.response_rules or {})
        brain = dict(rules.get("brain") or {})
        brain["learning_frozen"] = True
        rules["brain"] = brain
        settings.response_rules = rules
        session.add(
            PiLearningChange(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                kind="drift_freeze",
                risk="high",
                before={"learning_frozen": False},
                after={"learning_frozen": True},
                status="review",
                reason="pi's style drifted: " + ", ".join(found),
            )
        )
        from app.modules.notifications.service import notify

        await notify(
            session,
            scope,
            "pi.learning_frozen",
            "pi's learning was frozen: its style drifted",
            "Compared with the weeks before: " + ", ".join(found) + ". Look at the Brain screen.",
            link="/pi/brain",
            permission="pi.settings.manage",
            dedupe_key=f"pi-drift:{scope.tenant_id}:{now.date().isoformat()}",
        )
    await session.flush()
    return {"checked": True, "drifted": found}
