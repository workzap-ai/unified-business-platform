"""Lessons: short situational guidance in plain words (pi Brain spec 8.2, 8.7, 8.10 "Teach pi").

A person (or the nightly run) proposes a lesson such as "when someone describes a late delivery,
ask which route first". `learning.risk` sorts it: LOW (phrasing, order, vocabulary) goes live at
once; HIGH (anything touching money, privacy, the offer, follow-ups, approval or advice, or anything
the never-learn list refuses) waits for a second person, never its own author. A live lesson is
shown to pi as reference material below the rules for a matching situation. It can be retired in
one click. Nothing a lesson says can change a rule: the reply linter still judges every reply.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import (
    learning,
    learning_canary,
    learning_gate,
    learning_review,
    learning_situation,
)
from app.modules.pi.learning_models import PiLearningChange, PiLearningLesson
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

MAX_LESSONS_SHOWN = 3
MIN_LENGTH = 12
MAX_LENGTH = 300
SCOPE_KEYS = ("state", "language", "category", "industry", "person_type")
DOCUMENT_KIND = "document_drafter"  # lessons for the document drafter, never shown in the chat
NEVER_SAY = "never_say"  # a lesson that only forbids a phrase (spec 8.10, "Never say this")
MAX_NEVER_SAY = 40


def _where(scope: WorkspaceScope) -> tuple[Any, ...]:
    return (
        PiLearningLesson.tenant_id == scope.tenant_id,
        PiLearningLesson.environment_id == scope.environment_id,
    )


def _log(
    scope: WorkspaceScope,
    lesson: PiLearningLesson,
    kind: str,
    before: str,
    reason: str,
    by: UUID | None,
) -> PiLearningChange:
    return PiLearningChange(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        kind=kind,
        risk=lesson.risk.lower(),
        target_id=lesson.id,
        before={"status": before},
        after={"status": lesson.status, "text": lesson.text},
        reason=reason[:300],
        status="live" if lesson.status in ("live", "canary") else lesson.status,
        decided_by=by,
    )


async def propose(
    session: AsyncSession,
    scope: WorkspaceScope,
    text: str,
    situation: dict[str, str] | None,
    author_id: UUID | None,
    created_by: str = "staff",
    kind: str | None = None,
) -> PiLearningLesson:
    """Add a lesson. Refused when it is the wrong size or breaks the never-learn list for a reason
    no reviewer could fix (personal data, instructions aimed at pi's rules). A `kind` marks a
    lesson that is not for the chat (document wording): it is always HIGH and always waits for a
    second person, and the change log says so."""
    said = " ".join((text or "").split())
    if not MIN_LENGTH <= len(said) <= MAX_LENGTH:
        raise BusinessRuleViolation(
            "LESSON_SIZE", f"A lesson is {MIN_LENGTH} to {MAX_LENGTH} characters", 422
        )
    refused = [w for w in learning.never_learn(said) if "personal data" in w or "instructions" in w]
    if refused:
        raise BusinessRuleViolation("LESSON_REFUSED", "; ".join(refused), 422)
    risk = "HIGH" if kind else learning.risk(said)
    held = ""
    if (
        risk == "LOW"
        and created_by != "staff"
        and (
            await _was_rejected(session, scope, said)
            or await learning_review.blocked(
                session, scope, "lesson", learning_canary.signature(said)
            )
        )
    ):
        raise BusinessRuleViolation(
            "LESSON_REJECTED_BEFORE",
            "A reviewer rejected this lesson, or it was rolled back twice (8.6)",
            422,
        )
    if risk == "LOW" and not await learning_gate.allows(session, scope):
        held = "the release gate is failing: waits for a person"
    status = "review" if risk != "LOW" or held else "canary"
    lesson = PiLearningLesson(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        text=said,
        scope={
            **{k: v for k, v in (situation or {}).items() if k in SCOPE_KEYS and v},
            **({"kind": kind} if kind else {}),
        },
        risk=risk,
        status=status,
        created_by=created_by,
        author_id=author_id,
        canary_since=datetime.now(UTC) if status == "canary" else None,
    )
    session.add(lesson)
    await session.flush()
    why = held or (
        "low risk: starts as a canary (a small share of chats), live when it holds up"
        if risk == "LOW"
        else "high risk: waits for a second person"
    )
    session.add(_log(scope, lesson, "lesson_proposed", "", why, author_id))
    await session.flush()
    return lesson


async def decide(
    session: AsyncSession,
    scope: WorkspaceScope,
    lesson: PiLearningLesson,
    approve: bool,
    by: UUID | None,
    reason: str = "",
) -> PiLearningLesson:
    """A second person approves or rejects a lesson waiting for review."""
    if lesson.status != "review":
        raise BusinessRuleViolation(
            "LESSON_NOT_WAITING", "This lesson is not waiting for review", 409
        )
    if approve and by is not None and by == lesson.author_id:
        raise BusinessRuleViolation(
            "SECOND_PERSON_REQUIRED",
            "A high-risk lesson needs a different person to approve it",
            403,
        )
    lesson.status = "live" if approve else "rejected"
    lesson.decided_by = by
    lesson.reason = reason[:300]
    kind = "lesson_approved" if approve else "lesson_rejected"
    session.add(_log(scope, lesson, kind, "review", reason or kind, by))
    await session.flush()
    return lesson


async def retire(
    session: AsyncSession,
    scope: WorkspaceScope,
    lesson: PiLearningLesson,
    by: UUID | None,
    reason: str = "retired by staff",
) -> PiLearningLesson:
    before = lesson.status
    lesson.status = "retired"
    lesson.decided_by = by
    lesson.reason = reason[:300]
    session.add(_log(scope, lesson, "lesson_retired", before, reason, by))
    await session.flush()
    return lesson


def _fits(
    lesson: PiLearningLesson,
    state: str,
    language: str,
    industry: str = "",
    category: str = "",
    person_type: str = "",
) -> bool:
    """A lesson scoped to a part of the situation key (spec 8.2) fits only when that part is the
    same; a part it does not name is "any"."""
    wanted: dict[str, Any] = lesson.scope or {}
    return bool(
        wanted.get("state", state) == state
        and wanted.get("language", language) == language
        and wanted.get("industry", industry) == industry
        and wanted.get("sector", learning_situation.sector_of(industry))
        == learning_situation.sector_of(industry)
        and wanted.get("category", category) == category
        and wanted.get("person_type", person_type) == person_type
    )


def _norm(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


async def _was_rejected(session: AsyncSession, scope: WorkspaceScope, text: str) -> bool:
    """A reviewer rejected (or retired) this same lesson before: the miner must stop proposing it
    (spec 8.6, "reject with reason, fed back so the miner stops proposing it")."""
    gone = await session.scalars(
        select(PiLearningLesson.text).where(
            *_where(scope), PiLearningLesson.status.in_(("rejected", "retired"))
        )
    )
    return _norm(text) in {_norm(t) for t in gone}


async def rejected_reasons(
    session: AsyncSession, scope: WorkspaceScope, limit: int = 20
) -> list[str]:
    """Why reviewers rejected lessons, newest first, for the miner's prompt."""
    rows = await session.scalars(
        select(PiLearningLesson.reason)
        .where(*_where(scope), PiLearningLesson.status == "rejected", PiLearningLesson.reason != "")
        .order_by(PiLearningLesson.updated_at.desc())
        .limit(limit)
    )
    return [r for r in rows]


async def relevant(
    session: AsyncSession,
    scope: WorkspaceScope,
    state: str,
    language: str,
    *,
    industry: str = "",
    category: str = "",
    person_type: str = "",
    conversation_id: UUID | str | None = None,
    canary_percent: int = 0,
) -> list[PiLearningLesson]:
    """Live lessons for this situation, most specific first, at most three (plus canary lessons,
    for the canary share of conversations). Anything that no longer passes the never-learn list is
    left out."""
    in_share = conversation_id is not None and learning_canary.in_canary(
        conversation_id, canary_percent
    )
    rows = list(
        await session.scalars(
            select(PiLearningLesson)
            .where(
                *_where(scope),
                PiLearningLesson.status.in_(("live", "canary") if in_share else ("live",)),
            )
            .order_by(PiLearningLesson.created_at)
        )
    )
    fitting = [
        r
        for r in rows
        if not (r.scope or {}).get("kind")  # only plain lessons: any kind is for something else
        and _fits(r, state, language, industry, category, person_type)
        and not learning.never_learn(r.text)
    ]
    fitting.sort(key=lambda r: -len(r.scope or {}))
    chosen = fitting[:MAX_LESSONS_SHOWN]
    for lesson in chosen:
        await session.execute(
            update(PiLearningLesson)
            .where(PiLearningLesson.id == lesson.id)
            .values(uses=PiLearningLesson.uses + 1)
        )
    return chosen


async def add_never_say(
    session: AsyncSession,
    scope: WorkspaceScope,
    phrase: str,
    situation: dict[str, str] | None,
    author_id: UUID | None,
) -> PiLearningLesson:
    """ "Never say this": a phrase pi's replies must not contain in this situation. It only
    restricts, so it is live at once; it can never relax a rule."""
    said = " ".join((phrase or "").split())
    if not 3 <= len(said) <= 120:
        raise BusinessRuleViolation("PHRASE_SIZE", "A phrase is 3 to 120 characters", 422)
    lesson = PiLearningLesson(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        text=said,
        scope={
            "kind": NEVER_SAY,
            **{k: v for k, v in (situation or {}).items() if k in SCOPE_KEYS and v},
        },
        risk="LOW",
        status="live",
        created_by="staff",
        author_id=author_id,
    )
    session.add(lesson)
    await session.flush()
    session.add(_log(scope, lesson, "never_say_added", "", "staff: never say this", author_id))
    await session.flush()
    return lesson


async def never_say(
    session: AsyncSession, scope: WorkspaceScope, state: str, language: str
) -> list[str]:
    """The phrases pi must not use in this situation (staff lists, newest last)."""
    rows = await session.scalars(
        select(PiLearningLesson)
        .where(*_where(scope), PiLearningLesson.status == "live")
        .order_by(PiLearningLesson.created_at)
    )
    return [
        r.text
        for r in rows
        if (r.scope or {}).get("kind") == NEVER_SAY and _fits(r, state, language)
    ][-MAX_NEVER_SAY:]
