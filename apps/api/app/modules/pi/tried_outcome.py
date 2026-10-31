"""How an earlier attempt went, read from the owner's own words (L1 follow-up, live path).

Pure functions. `failed_attempt` finds a failed attempt in a text: a failure cue (negation + effect,
benefit or work word, in English, Roman Urdu, Urdu, Arabic and Hindi), or a weaker cue ("got mixed
up", "came out wrong", "was useless") that counts only beside an attempt word. It returns what was
tried, in the owner's own wording, so the stored `tried` entry can be matched against a new idea
(PS-3 `idea_relevance` reads `tried[].what`). `outcome_of` says "failed", "worked" or "unclear".

Only the owner's text is ever read here; a model's wording proves nothing (the caller passes the
owner's messages). Best effort: object words in Urdu, Arabic and Hindi are cut at the cue and at
attempt words, nothing more.
"""

import re
from typing import NamedTuple

# An attempt word: tried / before / experiment, in the five languages
ATTEMPT = re.compile(
    r"\b(?:tried|try|trying|aazma\w*|pehle|kiya tha|rakha tha|kiye|kiya|used|started)\b"
    r"|آزما|کوشش|پہلے|جرب|حاول|سابق|आज़मा|आजमा|कोशिश|पहले"
)

# Strong: a failed outcome on its own, like "did not work".
FAIL_STRONG = re.compile(
    r"\b(?:did not work|didn't work|didnt work|does not work|doesn't work|not worked|"
    r"made no difference|did nothing)\b"
    r"|\b(?:kaam|faida|fayda|faeda|asar|nateeja|natija)\s+(?:nahi|nahin|nhi)"
    r"(?:\s+(?:aaya|aya|hua|kiya|diya|kia|raha))?\b"
    r"|\bnakam\b|\bbe-?asar\b"
    r"|ناکام|(?:فائدہ|فایدہ|اثر|نتیجہ)\s+(?:نہیں|نھیں)|کام\s+نہیں\s+(?:آیا|کیا)"
    r"|لم\s+[يت](?:نجح|فد|نفع)|ما\s+(?:نفع|نجح|أفاد|افاد)|\bفشل|دون\s+جدوى|بدون\s+فائدة"
    r"|काम\s+नहीं\s+आया|(?:फायदा|फ़ायदा|असर|नतीजा)\s+नहीं|असफल|नाकाम"
)
# 'failed', 'useless' and the like count only beside an attempt word
FAIL_BESIDE_ATTEMPT = re.compile(
    r"\b(?:failed|useless|flopped|no use|no result|kaam nahi)\b"
    r"|\bmix\s+ho\s+gay[ei]\b|\bghalat\s+nikl(?:a|i|e)\b"
    r"|\bbekaar\s+(?:raha|rahi|nikla|nikli|gaya)\b"
    r"|بیکار\s+(?:رہا|رہی|نکلا|نکلی)|غلط\s+نکل|گڈ\s+مڈ\s+ہو|اختلط"
    r"|बेकार\s+(?:रहा|निकला)|गलत\s+निकला|मिक्स\s+हो\s+गए"
)
WORKED = re.compile(
    r"\b(?:it worked|worked well|that worked|helped|kaam aaya|faida hua|fayda hua|asar hua)\b"
    r"|فائدہ\s+ہوا|بہت\s+فائدہ|نفع|نجح|काम\s+आया|फायदा\s+हुआ"
)

_LEAD = re.compile(
    r"^(?:(?:we|i|hum|humne|already|have|had|previously|once|maine|so|and|but|lekin|phir)\s+)*"
    r"(?:(?:tried|try|aazmaya|used)\s+)?"
)
_TAIL = re.compile(
    r"(?:\s*(?:,|\band\b|\bbut\b|\blekin\b|\bpar\b|\bmagar\b|\bit\b|\bthat\b|\bthey\b|\bwhich\b|"
    r"\bbefore\b|\bearlier\b|\balready\b|\bpehle\b|\btry\b|\btried\b|\bkiye\b|\bkiya\b|\btha\b|"
    r"\bthe\b|\baazmaya\b|\bistemal\b|\bistamal\b|\buse\b|\bused\b|\bonce\b|"
    r"\blast (?:year|month|week)\b|\bin the past\b|\bpreviously\b))*\s*$"
)
_CLAUSE = re.compile(r"[.!?;\n]+|،|؛")
MAX_TEXT = 4000
MAX_WHAT = 160


class FailedAttempt(NamedTuple):
    what: str  # what was tried, in the owner's own wording ("rang wale folder")
    cue: str  # the failure words found


def _squash(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("’", "'").split())[:MAX_TEXT]


def _failure(text: str) -> re.Match[str] | None:
    strong = FAIL_STRONG.search(text)
    if strong:
        return strong
    if ATTEMPT.search(text):
        return FAIL_BESIDE_ATTEMPT.search(text)
    return None


def _what_before(text: str, at: int) -> str:
    before = text[:at]
    for marker in ("pehle", "try ", "aazma", "kiya tha", "rakha tha"):
        spot = before.find(marker)
        if spot > 0:
            before = before[:spot]
    before = _TAIL.sub("", _LEAD.sub("", before.strip()[-240:]))
    return before.strip(" ,:-")[:MAX_WHAT].strip()


def failed_attempt(text: str | None, language: str | None = None) -> FailedAttempt | None:
    """The first failed attempt the text says, or None. `language` is accepted for callers that
    know it; the cues are read for every language at once (a mixed message is common)."""
    for clause in _CLAUSE.split(str(text or "")):
        said = _squash(clause)
        found = _failure(said)
        if found is None:
            continue
        what = _what_before(said, found.start())
        return FailedAttempt(what, found.group(0))
    return None


def outcome_of(text: str | None) -> str:
    """ "failed" when the text says the attempt did not help, "worked" when it says it did (and not
    the opposite), else "unclear"."""
    said = _squash(str(text or ""))
    if not said:
        return "unclear"
    if _failure(said) is not None:
        return "failed"
    if WORKED.search(said):
        return "worked"
    return "unclear"


def not_worked(tried: object) -> list[object]:
    """The stored `tried` entries an idea may be checked against as a repeat: those the owner said
    failed, and those with no outcome said; never one the owner said worked (a repeat of a
    successful attempt is not a failed repeat). Plain strings and unknown shapes pass through."""
    if not isinstance(tried, list | tuple):
        return []
    return [
        t
        for t in tried
        if not (isinstance(t, dict) and str(t.get("outcome") or "").casefold() == "worked")
    ]
