"""Lessons: short situational guidance in plain words (pi Brain spec 8.2, 8.7, 8.10 "Teach pi").

A person (or the nightly run) proposes a lesson such as "when someone describes a late delivery,
ask which route first". `learning.risk` sorts it: LOW (phrasing, order, vocabulary) goes live at
once; HIGH (anything touching money, privacy, the offer, follow-ups, approval or advice, or anything
the never-learn list refuses) waits for a second person, never its own author. A live lesson is
shown to pi as reference material below the rules for a matching situation. It can be retired in
one click. Nothing a lesson says can change a rule: the reply linter still judges every reply.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning
from app.modules.pi.learning_models import PiLearningChange, PiLearningLesson
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

MAX_LESSONS_SHOWN = 3
MIN_LENGTH = 12
MAX_LENGTH = 300
SCOPE_KEYS = ("state", "language", "category")
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
        status="live" if lesson.status == "live" else lesson.status,
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
    lesson = PiLearningLesson(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        text=said,
        scope={
            **{k: v for k, v in (situation or {}).items() if k in SCOPE_KEYS and v},
            **({"kind": kind} if kind else {}),
        },
        risk=risk,
        status="live" if risk == "LOW" else "review",
        created_by=created_by,
        author_id=author_id,
    )
    session.add(lesson)
    await session.flush()
    why = "low risk: live at once" if risk == "LOW" else "high risk: waits for a second person"
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


def _fits(lesson: PiLearningLesson, state: str, language: str) -> bool:
    wanted: dict[str, Any] = lesson.scope or {}
    return bool(
        wanted.get("state", state) == state and wanted.get("language", language) == language
    )


async def relevant(
    session: AsyncSession, scope: WorkspaceScope, state: str, language: str
) -> list[PiLearningLesson]:
    """Live lessons for this situation, most specific first, at most three. Anything that no longer
    passes the never-learn list is left out."""
    rows = list(
        await session.scalars(
            select(PiLearningLesson)
            .where(*_where(scope), PiLearningLesson.status == "live")
            .order_by(PiLearningLesson.created_at)
        )
    )
    fitting = [
        r
        for r in rows
        if not (r.scope or {}).get("kind")  # only plain lessons: any kind is for something else
        and _fits(r, state, language)
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
