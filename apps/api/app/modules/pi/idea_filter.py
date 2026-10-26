"""The goal and grounding checks of the idea filter (platform spec Book 5, 7.1: G1 and G2).

`solution_rules.check_idea` already covers honesty (G6), no how-to (G5) and owner action; the free
idea vetting covers "uses something the person said". These two add what the second live chat
showed: a "keep a buffer back" idea for someone who wants to clear stock (G1), and "online
launches" or "a website shop" for a business that never mentioned either (G2).

Pure functions. An idea that fails is dropped; if every idea fails pi asks for one more fact."""

import re

from app.modules.pi import taxonomy

# A goal verb and the ideas that work against it.
_AGAINST_CLEARING = re.compile(
    r"\b(?:buffer|safety stock|stock up|order more|re-?order|keep (?:a )?(?:little|some|extra) "
    r"(?:stock )?(?:back|in reserve)|hold back|keep stock back)\b",
    re.IGNORECASE,
)
_AGAINST_KNOWING = re.compile(
    r"\b(?:discount|clearance|sale|mark(?:ing)? down|cut (?:the )?price)\b", re.IGNORECASE
)
_AGAINST_COLLECTING = re.compile(
    r"\b(?:give (?:more )?credit|extend (?:the )?credit|longer terms|offer (?:a )?discount for "
    r"(?:new|more) (?:orders|sales))\b",
    re.IGNORECASE,
)
_AGAINST = {
    "sell_clear": _AGAINST_CLEARING,
    "know_track": _AGAINST_KNOWING,
    "collect_cash": _AGAINST_COLLECTING,
}

# Context an idea must not bring in unless the owner said it (G2).
_INVENTED_CONTEXT = re.compile(
    r"\b(?:web ?site|online (?:store|shop|launch(?:es)?|sales?)|e-?commerce|webshop|web shop|"
    r"social media (?:ads?|campaign)|influencers?|franchis(?:e|es|ing)|export(?:s|ing)?)\b",
    re.IGNORECASE,
)


def goal_conflict(idea: str, owner_words: str) -> str | None:
    """G1: the rule id when the idea works against what the owner wants, else None."""
    sort = taxonomy.goal_sort(owner_words)
    if sort is None:
        return None
    pattern = _AGAINST.get(sort.goal_verb)
    if pattern is not None and pattern.search(idea):
        return "G1"
    return None


def invented_context(idea: str, owner_words: str) -> str | None:
    """G2: the rule id when the idea brings in a channel or business model the owner never named."""
    for match in _INVENTED_CONTEXT.finditer(idea):
        word = match.group(0).lower()
        if word.split()[0] not in owner_words.lower():
            return "G2"
    return None


def failures(idea: str, owner_words: str) -> list[str]:
    """Rule ids of G1 and G2 that the idea breaks (empty when it passes)."""
    found = [goal_conflict(idea, owner_words), invented_context(idea, owner_words)]
    return [rule for rule in found if rule]
