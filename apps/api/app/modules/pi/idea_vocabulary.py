"""G9 of the platform spec v1.4 (Book 5, 17.4): an idea uses the owner's trade's own words.

Live chat B: a locksmith was given an idea about a "breakdown call", a word from the generator and
lift trades. Every industry pack lists its trade's own words (`vocabulary`). A term that belongs to
only one or two packs is distinctive of those trades; when an idea brings in such a term and it is
not in the owner's own words nor in the vocabulary of the trade pi is talking about, the idea fails
G9. Pure functions; the index is built once from the packs.
"""

import json
import re
from collections.abc import Sequence
from functools import lru_cache

from app.modules.pi import industry_packs

MAX_PACKS = 2  # a term in more packs than this is ordinary business language, not a trade's own
MAX_TEXT_PACKS = 3  # and one that runs through the text of many packs ("tracker") is ordinary too
MIN_LENGTH = 6


def _terms(vocabulary: object) -> set[str]:
    out: set[str] = set()
    if not isinstance(vocabulary, dict):
        return out
    for key in vocabulary:
        for part in str(key).split("/"):
            term = re.sub(r"\s+", " ", part.strip().lower())
            if len(term) >= MIN_LENGTH:
                out.add(term)
    return out


@lru_cache(maxsize=1)
def _pack_terms() -> dict[str, frozenset[str]]:
    return {
        key: frozenset(_terms(pack.get("vocabulary")))
        for key, pack in industry_packs.load_packs().items()
    }


@lru_cache(maxsize=1)
def _distinctive() -> dict[str, frozenset[str]]:
    """term -> the packs that own it, for terms owned by at most MAX_PACKS packs."""
    owners: dict[str, set[str]] = {}
    for key, terms in _pack_terms().items():
        for term in terms:
            owners.setdefault(term, set()).add(key)
    packs = industry_packs.load_packs().values()
    texts = [json.dumps(pack, ensure_ascii=False).lower() for pack in packs]
    out: dict[str, frozenset[str]] = {}
    for term, keys in owners.items():
        if len(keys) > MAX_PACKS:
            continue
        pattern = re.compile(r"\b" + re.escape(term) + r"\b")
        holders = sum(1 for text in texts if term in text and pattern.search(text))
        if holders <= MAX_TEXT_PACKS:
            out[term] = frozenset(keys)
    return out


@lru_cache(maxsize=1)
def _pattern() -> re.Pattern[str] | None:
    terms = sorted(_distinctive(), key=len, reverse=True)
    if not terms:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE)


@lru_cache(maxsize=512)
def _own_text(key: str) -> str:
    pack = industry_packs.get_pack(key)
    return json.dumps(pack, ensure_ascii=False).lower() if pack else ""


def foreign_terms(idea: str, owner_words: str, industries: Sequence[str]) -> list[str]:
    """Trade words in the idea that belong to other trades only, and that the owner did not use.
    Empty when pi does not know the trade (nothing to compare against)."""
    if not industries:
        return []
    pattern = _pattern()
    if pattern is None:
        return []
    own = {t for key in industries for t in _pack_terms().get(key, ())}
    said = owner_words.lower()
    found: list[str] = []
    for match in pattern.finditer(idea):
        term = match.group(0).lower()
        owners = _distinctive().get(term, frozenset())
        if term in own or term in said or set(industries) & owners:
            continue
        if any(term in _own_text(key) for key in industries):
            continue  # the trade's own pack uses the word somewhere: it is that trade's too
        found.append(term)
    return found


def foreign_vocabulary(idea: str, owner_words: str, industries: Sequence[str]) -> str | None:
    """The rule id (G9) when the idea speaks another trade's language, else None."""
    return "G9" if foreign_terms(idea, owner_words, industries) else None
