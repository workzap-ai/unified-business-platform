"""Learning from the team's own work on documents (pi Brain spec 8.10).

Editing a drafted solution document teaches the drafter through phrase-level differences; a
win/loss note on a quote improves documents and quotes. Both become lessons that are HIGH risk by
rule (document and quote templates always wait for a second person, spec 8.7), are kept for the
document drafter only, and never reach the chat: a quote outcome must not become pressure in a
conversation. Nothing here runs while learning is frozen.
"""

import difflib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning, learning_lessons, safety
from app.modules.pi.brain_docs_models import PiBrainDocument
from app.modules.pi.learning_models import PiLearningLesson
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

DOCUMENT = learning_lessons.DOCUMENT_KIND  # the lesson scope that keeps a lesson out of the chat
MAX_PAIRS = 5
MAX_PHRASE_WORDS = 10
MIN_SIMILARITY = 0.5  # an edited item must still look like the one it came from
DIGIT_RUN = re.compile(r"\d[\d\s\-+()]{4,}\d")  # a phone, account or ID number
OUTCOMES = ("won", "lost", "stalled")
SHOWN = 5


def items(content: dict[str, Any]) -> list[str]:
    """The sentences of a solution document a reviewer can edit."""
    out = [str(c.get("text", "")) for c in content.get("components") or []]
    out += [str(x) for x in content.get("covers") or []]
    out += [str(x) for x in content.get("needs") or []]
    out += [str(w.get("text", "")) for w in content.get("wont_do") or []]
    return [i for i in out if i.strip()]


def phrase_pairs(before: list[str], after: list[str]) -> list[tuple[str, str]]:
    """(old phrase, new phrase) where a reviewer replaced words inside a sentence. Numbers and
    money are left out (prices never become habits), and so are pure additions and deletions."""
    pairs: list[tuple[str, str]] = []
    for new in after:
        if new in before:
            continue
        best = max(before, key=lambda b: difflib.SequenceMatcher(None, b, new).ratio(), default="")
        if not best or difflib.SequenceMatcher(None, best, new).ratio() < MIN_SIMILARITY:
            continue
        old_words, new_words = best.split(), new.split()
        matcher = difflib.SequenceMatcher(None, old_words, new_words)
        for tag, a0, a1, b0, b1 in matcher.get_opcodes():
            if tag != "replace":
                continue
            old, said = " ".join(old_words[a0:a1]), " ".join(new_words[b0:b1])
            small = 0 < a1 - a0 <= MAX_PHRASE_WORDS and 0 < b1 - b0 <= MAX_PHRASE_WORDS
            if small and not any(c.isdigit() for c in old + said) and (old, said) not in pairs:
                pairs.append((old, said))
    return pairs[:MAX_PAIRS]


def _unsafe(text: str) -> bool:
    """Personal data or an instruction aimed at pi's rules. The chat-only rules (no solution talk
    while listening) do not apply to wording for a document."""
    named = learning.PERSON_OR_COMPETITOR.search(text) is not None  # roles, never names
    return named or any(
        "personal data" in w or "instructions" in w for w in learning.never_learn(text)
    )


async def _known(session: AsyncSession, scope: WorkspaceScope) -> set[str]:
    return set(
        await session.scalars(
            select(PiLearningLesson.text).where(
                PiLearningLesson.tenant_id == scope.tenant_id,
                PiLearningLesson.environment_id == scope.environment_id,
            )
        )
    )


async def _propose(
    session: AsyncSession, scope: WorkspaceScope, text: str, author_id: UUID | None
) -> bool:
    """A document lesson: always HIGH, always waiting for a second person, drafter only."""
    if _unsafe(text) or text in await _known(session, scope):
        return False  # a name, personal data or an instruction aimed at the rules: not learnable
    try:
        await learning_lessons.propose(session, scope, text, {}, author_id, "staff", DOCUMENT)
    except BusinessRuleViolation:
        return False
    return True


async def learn_from_edit(
    session: AsyncSession,
    scope: WorkspaceScope,
    doc: PiBrainDocument,
    before: dict[str, Any],
    drafted_by_before: str,
    rules: dict[str, Any] | None,
    author_id: UUID | None,
) -> int:
    """Lessons from what the reviewer changed in a pi-drafted solution document. `drafted_by_before`
    is who wrote it before this edit: an edit marks the document as the team's own."""
    if doc.kind != "solution" or drafted_by_before != "pi" or learning.frozen(rules):
        return 0
    added = 0
    for old, new in phrase_pairs(items(before), items(doc.content)):
        text = f"When writing a solution document, say “{new}” rather than “{old}”."
        added += await _propose(session, scope, text, author_id)
    return added


async def record_outcome(
    session: AsyncSession,
    scope: WorkspaceScope,
    quote: PiBrainDocument,
    result: str,
    note: str,
    rules: dict[str, Any] | None,
    author_id: UUID | None,
) -> bool:
    """Keep the team's win/loss note on a quote and, when it says something, offer it as a lesson
    for the next document. Returns whether a lesson was offered."""
    if quote.kind != "quote":
        raise BusinessRuleViolation("NOT_A_QUOTE", "Win and loss notes belong to quotes", 422)
    if result not in OUTCOMES:
        raise BusinessRuleViolation("BAD_OUTCOME", "Use won, lost or stalled", 422)
    said = " ".join(safety.redact_pii(note or "").text.split())[:240]
    said = DIGIT_RUN.sub("[number]", said)
    content = dict(quote.content)
    content["outcome"] = {
        "result": result,
        "note": said,
        "at": datetime.now(UTC).isoformat(),
        "by": str(author_id) if author_id else None,
    }
    quote.content = content
    if not said or learning.frozen(rules):
        return False
    return await _propose(session, scope, f"On a quote that was {result}: {said}", author_id)


async def for_documents(session: AsyncSession, scope: WorkspaceScope) -> list[str]:
    """Approved wording tips for the drafter, newest first."""
    rows = await session.scalars(
        select(PiLearningLesson)
        .where(
            PiLearningLesson.tenant_id == scope.tenant_id,
            PiLearningLesson.environment_id == scope.environment_id,
            PiLearningLesson.status == "live",
        )
        .order_by(PiLearningLesson.created_at.desc())
    )
    return [
        r.text for r in rows if (r.scope or {}).get("kind") == DOCUMENT and not _unsafe(r.text)
    ][:SHOWN]
