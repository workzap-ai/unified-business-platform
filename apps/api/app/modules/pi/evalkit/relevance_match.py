"""Matching helpers for the relevance scorer (FT-A3b): light inflection, amounts, constraint rules.

Deterministic, no model and no third-party package. Not a quality gate and not a learning reward;
it prints no verdict of its own, `relevance` uses these helpers. Limits, stated plainly:
  * stemming is a short suffix list for English (plural, -ing, -ed, -ly, trailing e) and, only
    when the language is `roman_ur`, for common Roman Urdu endings (-on, -ain/-ein, -iyan, the
    infinitive/habitual/perfective endings and the gender vowels). It is not a dictionary: an
    irregular form ('children'), a prefix, or a language outside these two is not matched.
  * amounts understand digits with grouping (done by `relevance`), a currency marker (Rs, PKR,
    rupees, $ ...), magnitude words (k, thousand, hazar, lakh, lac, crore, karor, million), and a
    range ('10-15k', '10 to 15 thousand', 'between 10000 and 15000'). Spelled-out numbers ('two',
    'do hazar') are not read. A bare number with no currency, magnitude or unit word is ignored.
  * a limit is read as a ceiling only when its words say so (not more than, under, up to, at
    most, max, within, a budget kind, or Roman Urdu 'se zyada nahi'); a floor ('at least') is not
    compared. An idea figure written as a benefit (save, earn, revenue ...) or equal to a figure
    the owner already stated is not counted as a cost.
  * a limit text such as 'cannot buy a new feed mill' is read as a verb group plus an object, and
    'tried a discount before and it failed' as a repeated failed attempt. Only the listed verb
    groups are known; any other verb stands for itself.
"""

import math
import re
from typing import NamedTuple

MAGNITUDES = {
    "k": 1e3, "thousand": 1e3, "thousands": 1e3, "hazar": 1e3, "hazaar": 1e3, "hazaro": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lakhon": 1e5,
    "crore": 1e7, "crores": 1e7, "karor": 1e7, "karore": 1e7,
    "million": 1e6, "millions": 1e6, "mn": 1e6, "billion": 1e9, "arab": 1e9,
}  # fmt: skip
_MAG = r"k|mn|thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|millions?|billion|arab"
_NUM = r"\d[\d,]*(?:\.\d+)?"
_CURRENCY = {"rs", "pkr", "inr", "usd", "aed", "rupee", "rupees", "rupay", "rupaye", "dollar",
             "dollars", "$", "₹"}  # fmt: skip
_BARE_MAGNITUDE = r"(?:\s?(?:k|mn)|\s+(?:thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|millions?|billion|arab))"  # noqa: E501

# ---------------------------------------------------------------- inflection

_VOWELS = "aeiou"
_RU_SUFFIXES = ("iyan", "yan", "ain", "ein", "on", "ne", "na", "ni", "ta", "te", "ti", "ya",
                "ye", "yi", "a", "e", "i")  # fmt: skip


def _has_vowel(word: str) -> bool:
    return any(ch in _VOWELS for ch in word)


def english_stem(token: str) -> str:
    """Strip plural, -ing, -ed, -ly and a trailing e; undouble a final consonant; cut to 5."""
    t = token
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith(("sses", "shes", "ches", "xes", "zes")):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        t = t[:-1]
    if len(t) > 5 and t.endswith("ing") and _has_vowel(t[:-3]):
        t = t[:-3]
    elif len(t) > 4 and t.endswith("ied"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("ed") and _has_vowel(t[:-2]):
        t = t[:-2]
    elif len(t) > 5 and t.endswith("ly"):
        t = t[:-2]
    if len(t) > 3 and t.endswith("e"):
        t = t[:-1]
    if len(t) > 3 and t[-1] == t[-2] and t[-1] not in _VOWELS + "lsz":
        t = t[:-1]
    return t[:5]


def roman_urdu_stem(token: str) -> str:
    """Strip one common Roman Urdu ending (never below three letters)."""
    for suffix in sorted(_RU_SUFFIXES, key=len, reverse=True):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def stem_ascii(token: str, language: str | None = None) -> str:
    if language == "roman_ur":
        token = roman_urdu_stem(token)
    return english_stem(token)


# ------------------------------------------------------------------- numbers


def _plain(raw: str) -> float | None:
    """One grouped or plain number as a float; None when it is not one number."""
    if "," not in raw:
        return float(raw)
    if re.fullmatch(r"\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        return float(raw.replace(",", ""))
    if re.fullmatch(r"\d+,\d{1,2}", raw):
        return float(raw.replace(",", "."))
    return None


def _digits(value: float) -> str:
    return str(int(round(value))) if abs(value - round(value)) < 1e-9 else f"{value:g}"


_RANGE_FOLD = re.compile(
    rf"(?<![\w.,])({_NUM})\s?(?:-|–|—|to)\s?({_NUM})(?:(k|mn)|\s*(thousands?|haz+aro?|lakhs?|lacs?|"
    rf"lakhon|crores?|karore?|millions?|billion|arab))\b",
    re.IGNORECASE,
)
_FOLD = re.compile(
    rf"(?<![\w.,])({_NUM})(?:(k|mn)|\s*(thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|"
    rf"millions?|billion|arab))\b",
    re.IGNORECASE,
)


def fold_magnitudes(text: str) -> str:
    """'3 lakh' -> '300000', '20k' -> '20000', '10-15k' -> '10000 15000'. Figures only; the
    magnitude word disappears, so '3 lakh' and '3,00,000' are the same token afterwards."""

    def one(raw: str, mag: str) -> str | None:
        number = _plain(raw)
        return None if number is None else _digits(number * MAGNITUDES[mag.casefold()])

    def range_sub(m: re.Match[str]) -> str:
        mag = (m.group(3) or m.group(4)).casefold()
        lo, hi = one(m.group(1), mag), one(m.group(2), mag)
        return m.group(0) if lo is None or hi is None else f"{lo} {hi}"

    def sub(m: re.Match[str]) -> str:
        done = one(m.group(1), (m.group(2) or m.group(3)).casefold())
        return m.group(0) if done is None else done

    return _FOLD.sub(sub, _RANGE_FOLD.sub(range_sub, text or ""))


class Amount(NamedTuple):
    lo: float
    hi: float
    unit: str  # "money", or the stem of the word that follows ('staff', 'guest'), or ""
    start: int
    end: int


_AMOUNT = re.compile(
    rf"(?<![\w.,])(?P<pre>(?:rs\.?|pkr|inr|usd|aed)\s?|[$₹]\s?)?(?P<n1>{_NUM})"
    rf"(?:(?P<m1>k|mn)\b|\s*(?P<w1>thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|"
    rf"millions?|billion|arab)\b)?"
    rf"(?:\s?(?:-|–|—|to)\s?(?:rs\.?\s?|pkr\s?|[$₹]\s?)?(?P<n2>{_NUM})"
    rf"(?:(?P<m2>k|mn)\b|\s*(?P<w2>thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|"
    rf"millions?|billion|arab)\b)?)?"
    rf"(?:\s+(?P<unit>[a-z$₹]+))?",
    re.IGNORECASE,
)
_UNIT_SKIP = {"to", "for", "a", "an", "the", "and", "or", "of", "on", "in", "at", "so", "per",
              "se", "ka", "ki", "ke", "ko", "tak", "only", "total", "more", "less",
              "than", "each", "every", "by", "if", "is", "are", "as", "with", "from"}  # fmt: skip


def _mult(letter: str | None, word: str | None) -> float:
    key = (letter or word or "").casefold()
    return MAGNITUDES.get(key, 1.0)


def amounts(text: str) -> list[Amount]:
    """Quantities in `text`: a number with an optional currency marker, magnitude word, unit word
    and range. A figure with no currency, magnitude or unit word is not returned."""
    folded = re.sub(
        rf"between\s+({_NUM}(?:\s?(?:k|mn|{_MAG}))?)\s+and\s+({_NUM})",
        r"\1 to \2",
        (text or "").casefold(),
    )
    out: list[Amount] = []
    for m in _AMOUNT.finditer(folded):
        n1, n2 = _plain(m.group("n1")), _plain(m.group("n2")) if m.group("n2") else None
        if n1 is None or (m.group("n2") and n2 is None):
            continue
        m1, m2 = _mult(m.group("m1"), m.group("w1")), _mult(m.group("m2"), m.group("w2"))
        has_mag = m1 != 1.0 or m2 != 1.0
        if n2 is None:
            lo = hi = n1 * m1
        else:
            first = m1 if m1 != 1.0 else (m2 if (m2 != 1.0 and n1 < n2) else 1.0)
            lo, hi = n1 * first, n2 * m2
            if lo > hi:
                lo, hi = hi, lo
        pre = (m.group("pre") or "").strip(" .")
        unit_word = (m.group("unit") or "").strip()
        end = m.end()
        if unit_word in _UNIT_SKIP or not unit_word:
            unit_word = ""
            end = m.end("n2") if m.group("n2") else m.end("n1")
            end = max(end, m.end("w2") if m.group("w2") else end, m.end("m2") or end)
        if pre or unit_word in _CURRENCY:
            unit = "money"
        elif unit_word:
            unit = english_stem(unit_word)
        elif has_mag:
            unit = "money"  # '50k' or '3 lakh' with no noun: a sum
        else:
            continue
        out.append(Amount(lo, hi, unit, m.start(), end))
    return out


_CEILING_BEFORE = re.compile(
    r"(?:(?:not|no|never|cannot|can't|can not|cant|won't|must not)\s+(?:[a-z']+\s+){0,3}?"
    r"(?:more than|above|over|beyond|exceed\w*|higher than|greater than|upto|up to)"
    r"|\b(?:under|below|less than|at most|at the most|up to|upto|max(?:imum)?(?: of)?|within"
    r"|limit(?:ed)? (?:to|of)|cap(?:ped)?(?: at)?|not exceed\w*|no more than)\s*$"
    r"|\b(?:not|no)\s+(?:above|over|beyond)\s*$)"
)
_CEILING_AFTER = re.compile(
    r"^\s*(?:rupay\w*|rupees?|rs|pkr)?\s*(?:se|say)\s+(?:zyada|ziada|zyadah|upar|oopar|barh)"
)
_FLOOR = re.compile(r"\b(?:at least|minimum|not less|no less|no fewer|not fewer|kam se kam)\b")
_STRICT = re.compile(r"\b(?:under|below|less than)\s*(?:rs\.?|pkr|[$₹])?\s*$")
_BENEFIT = {"save", "saves", "saving", "savings", "saved", "earn", "earns", "earning",
            "revenue", "profit", "sales", "worth", "lose", "lost", "loss", "losing", "bachat",
            "kamai", "munafa", "nuqsan"}  # fmt: skip


class Ceiling(NamedTuple):
    value: float
    unit: str
    strict: bool


def ceiling_of(limit_text: str, kind: str = "") -> Ceiling | None:
    """The ceiling a limit text states as a number, or None when it states none."""
    text = (limit_text or "").casefold()
    if _FLOOR.search(text):
        return None
    for found in amounts(text):
        before, after = text[: found.start], text[found.end :]
        if _CEILING_BEFORE.search(before) or _CEILING_AFTER.search(after) or kind == "budget":
            unit = found.unit
            if unit == "" and kind == "budget":
                unit = "money"
            return Ceiling(found.hi, unit, bool(_STRICT.search(before)))
    return None


def _benefit(text: str, found: Amount) -> bool:
    words = re.findall(r"[a-z]+", text[max(0, found.start - 40) : found.start].casefold())
    return any(w in _BENEFIT for w in words[-3:])


def over_ceiling(idea_text: str, ceiling: Ceiling, said: set[tuple[float, float]]) -> bool:
    """True when an idea figure of the same kind is plainly above the ceiling. A figure the owner
    already stated, a benefit, and a range that reaches down to the ceiling are not costs."""
    text = (idea_text or "").casefold()
    for found in amounts(text):
        if found.unit != ceiling.unit or (found.lo, found.hi) in said or _benefit(text, found):
            continue
        if found.lo > ceiling.value or (ceiling.strict and found.lo >= ceiling.value):
            return True
    return False


def said_amounts(texts: list[str]) -> set[tuple[float, float]]:
    return {(a.lo, a.hi) for t in texts for a in amounts(t)}


# ------------------------------------------------------- verb and tried rules

_FAMILIES = [
    {"buy", "purchase", "acquire", "procure", "order", "kharid"},
    {"hire", "recruit", "employ", "appoint"},
    {"spend", "pay", "invest"},
    {"refuse", "reject", "decline"},
    {"change", "alter", "modify", "replace", "switch", "swap", "badal"},
    {"close", "shut", "stop", "halt", "suspend", "band"},
    {"fire", "dismiss", "sack", "terminate", "lay"},
    {"raise", "increase", "hike"},
    {"cut", "reduce", "lower", "decrease"},
    {"sell", "bech"},
]
_ALTERNATIVES = {"buy": {"rent", "lease", "borrow", "share"}}
_FAMILY_STEMS = [{english_stem(w) for w in g} for g in _FAMILIES]
_ALT_STEMS = {
    english_stem(k): frozenset(english_stem(w) for w in v) for k, v in _ALTERNATIVES.items()
}
_NEG = re.compile(
    r"\b(?:cannot|can't|can not|cant|do not|don't|dont|must not|mustn't|never|won't|will not|"
    r"unable to|not able to|not allowed to|no way to|may not|should not|shouldn't)\s+"
    r"(?:(?:want|afford|be able|be allowed)\s+to\s+)?(?P<verb>[a-z']+)\s*(?P<obj>[^,;.:!?()]*)"
)
_NEG_RU = re.compile(
    r"(?P<obj>[^,;.:!?()]+?)\s+(?P<verb>[a-z]+)\s+(?:nahi|nahin)\s+(?:kar\s+)?sakt[a-z]*"
)
_NEG_RU_VERB = re.compile(
    r"(?P<obj>[^,;.:!?()]+?)\s+(?:nahi|nahin)\s+(?P<verb>badal|kharid|bech|band|hata)[a-z]*\s+sakt"
)
_CUT = re.compile(r"\b(?:because|as|so|since|but|when|while|if|taake|kyunke)\b")
_TIME = re.compile(
    r"\b(?:this|next|last|is|iss|agle) (?:year|month|week|season|quarter|saal|mahine)\b"
    r"|\b(?:right now|for now|at the moment|at all|anymore|any more|abhi)\b"
)
_FILLER = {"new", "more", "another", "second", "extra", "any", "additional", "other", "anyone",
           "anybody", "anything", "someone", "people", "ones", "naya", "naye", "nayi"}  # fmt: skip
_FAIL = re.compile(
    r"\b(?:failed|fails?|did not work|didn't work|didnt work|does not work|doesn't work|"
    r"not work(?:ed)?|no use|useless|flopped|made no difference|did nothing|no result)\b"
    r"|\b(?:kaam nahi|nakam|faida nahi|fayda nahi)\b"
)
_TRIED_LEAD = re.compile(
    r"^(?:(?:we|i|hum|humne|already|have|had|previously|once|maine)\s+)*(?:(?:tried|try|aazmaya)\s+)?"
)
_TRIED_TAIL = re.compile(
    r"(?:\s*(?:,|\band\b|\bbut\b|\blekin\b|\bpar\b|\bmagar\b|\bit\b|\bthat\b|\bthey\b|\bwhich\b|"
    r"\bbefore\b|\bearlier\b|\balready\b|\bpehle\b|\btry\b|\btried\b|\blast (?:year|month|week)\b|"
    r"\bin the past\b|\bpreviously\b|\bkiya\b|\btha\b|\baazmaya\b|\bonce\b))*\s*$"
)


class Rule(NamedTuple):
    kind: str  # "neg" (cannot VERB OBJECT) or "tried" (OBJECT failed before)
    verbs: frozenset[str]  # stems of the verb group; empty for "tried"
    alternatives: frozenset[str]  # stems of verbs that do not break the limit
    objects: frozenset[str]  # content stems of the object
    need: int  # how many object stems an idea must contain


def _need(count: int) -> int:
    return count if count <= 2 else math.ceil(2 * count / 3)


def _object_stems(text: str, language: str | None, stems_of) -> frozenset[str]:  # type: ignore[no-untyped-def]
    cut = _CUT.split(_TIME.sub(" ", text))[0]
    cut = re.sub(r"\b(?:" + "|".join(sorted(_FILLER)) + r")\b", " ", cut)
    return frozenset(stems_of(cut, language))


def parse_rules(limit_text: str, language: str | None, stems_of) -> list[Rule]:  # type: ignore[no-untyped-def]
    """Verb and tried rules read from a limit's own text. `stems_of(text, language)` is the
    scorer's stemmer, so a rule and an idea are always compared in the same stem space."""
    text = (limit_text or "").casefold()
    rules: list[Rule] = []
    seen: set[tuple[str, str]] = set()

    def add_neg(verb: str, obj: str) -> None:
        stem = english_stem(verb)
        group = next((g for g in _FAMILY_STEMS if stem in g), {stem})
        alt = frozenset().union(*(_ALT_STEMS.get(s, frozenset()) for s in group))
        objects = _object_stems(obj, language, stems_of)
        if any(any(ch.isdigit() for ch in o) for o in objects):
            return  # a figure in the limit is compared as a number, not as a word
        key = (stem, ",".join(sorted(objects)))
        if key not in seen:
            seen.add(key)
            rules.append(Rule("neg", frozenset(group), alt, objects, _need(len(objects))))

    for m in _NEG.finditer(text):
        add_neg(m.group("verb"), m.group("obj"))
    if language == "roman_ur":
        for rx in (_NEG_RU, _NEG_RU_VERB):
            for m in rx.finditer(text):
                add_neg(m.group("verb"), m.group("obj"))
    if _FAIL.search(text):
        before = _FAIL.split(text)[0]
        for marker in ("pehle", "try ", "aazma"):
            at = before.find(marker)
            if at > 0:
                before = before[:at]
        before = _TRIED_TAIL.sub("", _TRIED_LEAD.sub("", before.strip()))
        objects = _object_stems(before, language, stems_of) - {"tried", "try"}
        if objects:
            rules.append(Rule("tried", frozenset(), frozenset(), objects, _need(len(objects))))
    return rules


def rule_hit(rule: Rule, idea: set[str]) -> bool:
    """The idea does what the rule forbids: the verb group (for 'cannot') and enough of the
    object. A 'cannot VERB' with no object words is broken by the verb alone."""
    if rule.kind == "neg" and not (rule.verbs & idea):
        return False
    return len(rule.objects & idea) >= rule.need


def rule_alternative(rule: Rule, idea: set[str]) -> bool:
    """The idea uses a milder verb the limit does not cover ('rent' against 'cannot buy')."""
    return rule.kind == "neg" and bool(rule.alternatives & idea) and not (rule.verbs & idea)
