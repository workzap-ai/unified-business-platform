"""Vocabulary pi picks up from customers (pi Brain spec 8.5 job 4).

A word or short phrase customers use for a problem becomes a lesson ("people here say X when they
mean a Y problem") once at least five different businesses used it and at least 90% of the time it
ended up in one category (`learning_rules.lexicon_terms`). Only problems the classifier was unsure
about count (low confidence, or first filed as "other" and moved by a person), and the lesson is
scoped to the industry (or, when no single industry has enough businesses, to its sector). New
spellings of a known term (Roman Urdu variants) are clustered into one term. It goes through the
same lesson gate as a person's tip: low risk starts as a canary, anything touching money or the
rules waits for a person.
"""

import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.pi import learning_lessons, learning_packs, learning_rules, learning_situation
from app.modules.pi.learning_models import PiLearningLesson
from app.modules.pi.problem_models import PiProblem, PiProblemRevision
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

MAX_WORDS = 3
MAX_NEW_PER_RUN = 10
LOW_CONFIDENCE = 0.7  # only what the classifier was unsure about
OTHER = "other"
DOUBLED = re.compile(r"(.)\1+")


def phrase(text: str) -> str | None:
    """A customer's word or short phrase that is safe to learn, lower-cased, or None."""
    said = learning_packs.clean_text(text, 40)
    if said is None or not 1 <= len(said.split()) <= MAX_WORDS or len(said) < 4:
        return None
    return said.lower()


def lesson_text(term: str, category: str, variants: list[str] | None = None) -> str:
    also = f' (or "{", ".join(variants)}")' if variants else ""
    kind = category.replace("_", " ")
    return f'When someone says "{term}"{also}, they usually mean a {kind} problem.'


# Roman Urdu is spelled many ways ("nuksan", "nuqsan", "nuksaan"). Spellings that fold to the same
# skeleton are one term; the most common spelling leads.
FOLD = (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("q", "k"), ("ph", "f"))


def skeleton(term: str) -> str:
    folded = term.lower()
    for old, new in FOLD:
        folded = folded.replace(old, new)
    return DOUBLED.sub(r"\1", folded)


def cluster_variants(counts: Counter[str]) -> dict[str, tuple[str, list[str]]]:
    """term -> (leading spelling, the other spellings), for terms in Latin letters that fold to
    the same skeleton and start with the same letter."""
    groups: dict[tuple[str, str], list[str]] = {}
    for term in counts:
        if term.isascii():
            groups.setdefault((skeleton(term), term[:1]), []).append(term)
    out: dict[str, tuple[str, list[str]]] = {}
    for terms in groups.values():
        lead = max(terms, key=lambda t: (counts[t], t))
        others = sorted(t for t in terms if t != lead)
        for t in terms:
            out[t] = (lead, others)
    return out


async def qualifying(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    """Problems whose category the classifier was unsure about, with the business, industry and
    the weight of a staff correction."""
    moved_from_other: set[Any] = set()
    corrected_by_staff: set[Any] = set()
    for problem_id, diff, by in await session.execute(
        select(PiProblemRevision.problem_id, PiProblemRevision.diff, PiProblemRevision.by).where(
            PiProblemRevision.tenant_id == scope.tenant_id,
            PiProblemRevision.environment_id == scope.environment_id,
        )
    ):
        change = (diff or {}).get("category")
        if change:
            if by == "staff":  # only a staff-chosen category counts: a title typo confirms nothing
                corrected_by_staff.add(problem_id)
            if isinstance(change, list) and change and change[0] == OTHER:
                moved_from_other.add(problem_id)
    rows = await session.execute(
        select(
            PiProblem.id,
            PiProblem.customer_id,
            PiProblem.category,
            PiProblem.user_words,
            PiProblem.confidence,
            PiProblem.language,
            Customer.industry_primary,
        )
        .join(Customer, Customer.id == PiProblem.customer_id, isouter=True)
        .where(
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
        )
    )
    out: list[dict[str, Any]] = []
    for pid, customer_id, category, words, confidence, language, industry in rows:
        unsure = float(confidence or 0) < LOW_CONFIDENCE or pid in moved_from_other
        if not unsure or category == OTHER:
            continue
        out.append(
            {
                "customer": str(customer_id),
                "category": category,
                "words": words or [],
                "language": language,
                "industry": learning_situation.clean_industry(industry),
                "weight": learning_rules.STAFF_WEIGHT if pid in corrected_by_staff else 1,
            }
        )
    return out


async def learn(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """New vocabulary lessons from the problems the classifier was unsure about. Returns counts."""
    problems = await qualifying(session, scope)
    counts: Counter[str] = Counter()
    for p in problems:
        if p["language"] == "roman_ur":
            counts.update(t for w in p["words"] if (t := phrase(str(w))) is not None)
    variants = cluster_variants(counts)

    def observations(match: Callable[[dict[str, Any]], bool]) -> list[tuple[str, str, str, int]]:
        seen: list[tuple[str, str, str, int]] = []
        for p in problems:
            if not match(p):
                continue
            for word in p["words"]:
                if (term := phrase(str(word))) is not None:
                    lead = variants.get(term, (term, []))[0]
                    seen.append((lead, p["customer"], p["category"], p["weight"]))
        return seen

    industries = sorted({p["industry"] for p in problems if p["industry"]})
    passes: list[tuple[dict[str, str], dict[str, str]]] = []  # (scope, term -> category)

    def in_industry(industry: str) -> Callable[[dict[str, Any]], bool]:
        return lambda p: bool(p["industry"] == industry)

    def in_sector(sector: str) -> Callable[[dict[str, Any]], bool]:
        return lambda p: bool(
            p["industry"] and learning_situation.sector_of(p["industry"]) == sector
        )

    def unclassified(p: dict[str, Any]) -> bool:
        return not p["industry"]

    for industry in industries:
        got = learning_rules.lexicon_terms(observations(in_industry(industry)))
        passes.append(({"industry": industry}, got))
    for sector in sorted({learning_situation.sector_of(i) for i in industries} - {""}):
        got = learning_rules.lexicon_terms(observations(in_sector(sector)))
        passes.append(({"sector": sector}, got))
    passes.append(({}, learning_rules.lexicon_terms(observations(unclassified))))
    have = {
        (text, tuple(sorted((lesson_scope or {}).items())))
        for text, lesson_scope in await session.execute(
            select(PiLearningLesson.text, PiLearningLesson.scope).where(
                PiLearningLesson.tenant_id == scope.tenant_id,
                PiLearningLesson.environment_id == scope.environment_id,
            )
        )
    }
    terms_seen, added = 0, 0
    taken: set[str] = set()
    for where, got in passes:
        for term, category in sorted(got.items()):
            terms_seen += 1
            if term in taken:
                continue  # a narrower scope already has it
            text = lesson_text(term, category, variants.get(term, (term, []))[1])
            if (text, tuple(sorted(where.items()))) in have or added >= MAX_NEW_PER_RUN:
                continue
            try:
                lesson = await learning_lessons.propose(
                    session,
                    scope,
                    text,
                    {"industry": where["industry"]} if "industry" in where else {},
                    None,
                    created_by="pi",
                )
            except BusinessRuleViolation:
                continue  # rejected before, or rolled back twice: not proposed again
            if "sector" in where:
                lesson.scope = {**lesson.scope, "sector": where["sector"]}
            taken.add(term)
            added += 1
    return {"terms_seen": terms_seen, "lessons_added": added}
