"""Vocabulary pi picks up from customers (pi Brain spec 8.5 job 4).

A word or short phrase customers use for a problem becomes a lesson ("people here say X when they
mean a Y problem") once at least five different businesses used it and at least 90% of the time it
ended up in one category (`learning_rules.lexicon_terms`). It goes through the same lesson gate as
a person's tip: low risk goes live, anything touching money or the rules waits for a person.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import learning_lessons, learning_packs, learning_rules
from app.modules.pi.learning_models import PiLearningLesson
from app.modules.pi.problem_models import PiProblem
from app.shared.scope import WorkspaceScope

MAX_WORDS = 3
MAX_NEW_PER_RUN = 10


def phrase(text: str) -> str | None:
    """A customer's word or short phrase that is safe to learn, lower-cased, or None."""
    said = learning_packs.clean_text(text, 40)
    if said is None or not 1 <= len(said.split()) <= MAX_WORDS or len(said) < 4:
        return None
    return said.lower()


def lesson_text(term: str, category: str) -> str:
    return f'When someone says "{term}", they usually mean a {category.replace("_", " ")} problem.'


async def learn(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """New vocabulary lessons from the problems noted so far. Returns counts."""
    rows = await session.execute(
        select(PiProblem.customer_id, PiProblem.category, PiProblem.user_words).where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
        )
    )
    seen: list[tuple[str, str, str]] = []
    for customer_id, category, words in rows:
        for word in words or []:
            if (term := phrase(str(word))) is not None:
                seen.append((term, str(customer_id), category))
    found = learning_rules.lexicon_terms(seen)
    have = set(
        await session.scalars(
            select(PiLearningLesson.text).where(
                PiLearningLesson.tenant_id == scope.tenant_id,
                PiLearningLesson.environment_id == scope.environment_id,
            )
        )
    )
    added = 0
    for term, category in sorted(found.items()):
        text = lesson_text(term, category)
        if text in have or added >= MAX_NEW_PER_RUN:
            continue
        await learning_lessons.propose(session, scope, text, {}, None, created_by="pi")
        added += 1
    return {"terms_seen": len(found), "lessons_added": added}
