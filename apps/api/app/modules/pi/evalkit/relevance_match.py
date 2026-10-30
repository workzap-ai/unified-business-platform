"""Matching helpers for the relevance scorer (FT-A3b): light inflection, amounts, constraint rules.

Deterministic, no model and no third-party package. Not a quality gate and not a learning reward;
it prints no verdict of its own, `relevance` uses these helpers. Limits, stated plainly:
  * stemming is a short suffix list for English (plural, -ing, -ed, -ly, trailing e) and, only
    when the language is `roman_ur`, for common Roman Urdu endings (-on, -ain/-ein, -iyan, the
    infinitive/habitual/perfective endings and the gender vowels). It is not a dictionary: an
    irregular form ('children'), a prefix, or a language outside these two is not matched.
  * two stem spaces. The soft space cuts a stem to five letters and feeds only the soft overlap
    that decides relevant or not; it glues unrelated words ('discount' and 'discover'). The full
    space keeps the whole stem and is the only one used to REJECT an idea (a limit's blocks, a
    'cannot VERB OBJECT' rule, a 'tried and failed' rule): 'employee' never matches 'employ'. In
    the full space Roman Urdu endings are stripped only when four letters stay ('salon' is not
    'sale', 'data' is not 'date').
  * amounts understand digits with grouping, a currency marker (Rs, PKR, rupees, $ ...),
    magnitude words (k, thousand, hazar, lakh, lac, crore, karor, million) and a range ('10-15k',
    '10 to 15 thousand', 'between 10000 and 15000'). A trailing comma or full stop is punctuation
    and a list of 3-digit numbers ('120,150,180') stays separate numbers. Spelled-out numbers
    ('two', 'do hazar') and a spaced 'k' ('5 k') are not read. A bare number with no currency,
    magnitude or unit word is ignored (except in a budget limit's own text).
  * a limit is read as a ceiling only when its words say so (not more than, under, up to, at
    most, max, within, a budget kind, or Roman Urdu 'se zyada nahi'); a floor ('at least') is not
    compared. An idea figure is not counted as a cost when it directly follows a benefit word
    (save, earn, profit, revenue, sales of, loss of) or equals, in the same unit, a figure the
    owner already stated.
  * a limit text such as 'cannot buy a new feed mill' is read as a verb group plus an object, and
    'tried a discount before and it failed' as a repeated failed attempt. Only modal prohibitions
    ('cannot', 'must not', 'unable to', 'do not want to') count; a descriptive 'never' or
    'fails to' is not a prohibition. Only the listed verb groups are known; any other verb
    stands for itself.
  * money versus counted nouns: a figure with a currency marker or magnitude word is money unless
    the next word is in a short list of counted nouns (staff, days, guests, birds ...); a bare
    figure is money only in a money context (a budget limit, or 'for', 'costs', 'pay' before it)
    and a following 'then', 'because', 'this month' is not a unit. A counted noun outside that
    list after a magnitude word ('3 lakh goats') is read as money. In an idea, a bare figure with
    no price cue before it is ignored.
  * a verb that is also a noun ('fire', 'cut', 'close', 'stop', 'use', 'order') is dropped from
    an idea's verbs when it follows a determiner or preposition ('a fire alarm', 'each stop'); a
    noun used without one ('fire drills') still looks like the verb. Roman Urdu verb roots are
    added to a verb group only in `roman_ur` cases. 'plane' is kept apart from 'plan' by an
    exception list; other long e-words and -ing nouns not in the lists can still merge.
    Rules read only the first 4000 characters of a limit text.
  * not handled, on purpose: a prohibition without a modal ('no hiring', 'never hire'), 'cannot
    VERB' with an object that is only a figure, a floor ('at least'), spelled-out numbers, and a
    figure written for a different unit than the limit's (staff against money).
"""

import math
import re
from collections.abc import Callable
from typing import NamedTuple

MAGNITUDES = {
    "k": 1e3, "thousand": 1e3, "thousands": 1e3, "hazar": 1e3, "hazaar": 1e3, "hazaro": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lakhon": 1e5,
    "crore": 1e7, "crores": 1e7, "karor": 1e7, "karore": 1e7,
    "million": 1e6, "millions": 1e6, "mn": 1e6, "billion": 1e9, "arab": 1e9,
}  # fmt: skip
_MAG = r"k|mn|thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|millions?|billion|arab"
_NUM = r"\d+(?:,\d+)*(?:\.\d+)?"  # a comma is part of a figure only when digits follow it
_CURRENCY = {"rs", "pkr", "inr", "usd", "aed", "rupee", "rupees", "rupay", "rupaye", "dollar",
             "dollars", "$", "₹"}  # fmt: skip

# ---------------------------------------------------------------- inflection

_VOWELS = "aeiou"
_RU_SUFFIXES = ("iyan", "yan", "ain", "ein", "on", "ne", "na", "ni", "ta", "te", "ti", "ya",
                "ye", "yi", "a", "e", "i")  # fmt: skip
# nouns that end in -ing without being an inflection ('evening' is not 'even')
_NOT_ING = {"evening", "morning", "ceiling", "during", "nothing", "something",
            "anything", "everything", "spring", "string", "sibling", "wedding"}  # fmt: skip


def _has_vowel(word: str) -> bool:
    return any(ch in _VOWELS for ch in word)


_DOUBLE_L = {"cancell", "travell", "labell", "modell", "fuell", "levell", "signall"}
_KEEP_E = {"plane"}


def _consonant(ch: str) -> bool:
    return ch.isalpha() and ch not in _VOWELS


def _cvc(word: str) -> bool:
    return (
        len(word) >= 3
        and _consonant(word[-3])
        and word[-2] in _VOWELS
        and _consonant(word[-1])
        and word[-1] not in "wxy"
    )


def english_plural(token: str) -> str:
    """Strip an English plural: -ies, -sses/-shes/-ches/-xes/-zes, -s (not -ss, -us, -is)."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("sses", "shes", "ches", "xes", "zes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def english_stem(token: str) -> str:
    """Strip plural, -ing, -ed, -ly and a trailing e; undouble a final consonant. The whole stem
    is returned; the soft space cuts it to five letters (`relevance`). A short stem keeps its e
    ('care', 'rate', 'cute' stay apart from 'car', 'rat', 'cut') and a short stem left by -ing or
    -ed gets it back ('hiring' and 'hire' agree)."""
    t = english_plural(token)
    stripped = False
    if len(t) > 5 and t.endswith("ing") and t not in _NOT_ING and _has_vowel(t[:-3]):
        t, stripped = t[:-3], True
    elif len(t) > 4 and t.endswith("ied"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("ed") and _has_vowel(t[:-2]):
        t, stripped = t[:-2], True
    if len(t) > 5 and t.endswith("ly"):
        t = t[:-2]
    if stripped:
        if t in _DOUBLE_L:
            t = t[:-1]
        elif len(t) > 3 and t[-1] == t[-2] and t[-1] not in _VOWELS + "lsz":
            t = t[:-1]
        elif len(t) <= 4 and _cvc(t):
            t += "e"
    elif len(t) > 4 and t[-1] == t[-2] and t[-1] not in _VOWELS + "lsz":
        t = t[:-1]
    if len(t) > 4 and t.endswith("e") and t not in _KEEP_E:
        t = t[:-1]
    return t


def roman_urdu_stem(token: str, min_left: int = 3) -> str:
    """Strip one common Roman Urdu ending, never leaving fewer than `min_left` letters ('on' needs
    one more: 'lesson' is not 'less', 'coupon' is not 'coup')."""
    for suffix in sorted(_RU_SUFFIXES, key=len, reverse=True):
        need = min_left + (1 if suffix == "on" and min_left > 3 else 0)
        if token.endswith(suffix) and len(token) - len(suffix) >= need:
            return token[: -len(suffix)]
    return token


def stem_ascii(token: str, language: str | None = None, full: bool = False) -> str:
    """The stem of an ASCII word. `full` is the strict space used to reject an idea: Roman Urdu
    endings are stripped only when four letters stay. The soft space keeps three. In Roman Urdu
    the English plural goes first, so 'buttons' and 'button' reach the same stem."""
    if language == "roman_ur":
        token = roman_urdu_stem(english_plural(token), 4 if full else 3)
    return english_stem(token)


# ------------------------------------------------------------------- numbers

_LIST = re.compile(r"(?<![\w.,])\d{3}(?:,\d{3}){2,}(?![\w,])")


def _unlist(text: str) -> str:
    """A comma list of 3-digit numbers ('120,150,180') becomes separate numbers; a grouped figure
    ('120,000,000') stays one. Same reading as `relevance.tokens`."""

    def sub(m: re.Match[str]) -> str:
        groups = m.group().split(",")
        return " ".join(groups) if groups[-1] != "000" else m.group()

    return _LIST.sub(sub, text)


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

    return _FOLD.sub(sub, _RANGE_FOLD.sub(range_sub, _unlist(text or "")))


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
              "se", "say", "ka", "ki", "ke", "ko", "tak", "only", "total", "more", "less",
              "than", "each", "every", "by", "if", "is", "are", "as", "with", "from"}  # fmt: skip


def _mult(letter: str | None, word: str | None) -> float:
    key = (letter or word or "").casefold()
    return MAGNITUDES.get(key, 1.0)


# words that follow a figure without being what is counted ('20000 this month', 'for 50000 then')
_TAIL = _UNIT_SKIP | {"then", "because", "this", "next", "last", "monthly", "weekly", "yearly",
                      "daily", "annually", "mein", "main", "per", "so", "but", "aur", "lekin", "ya",
                      "hai", "hain", "abhi", "tight", "approx", "approximately", "maximum",
                      "max", "budget", "that", "which", "when", "while", "thak"}  # fmt: skip
# what a figure with a magnitude or currency cue may count instead of money
_COUNTED = {"staff", "people", "persons", "person", "units", "unit", "days", "day", "weeks",
            "week", "months", "month", "years", "year", "hours", "hour", "minutes", "times",
            "guests", "guest", "items", "item", "workers", "worker", "employees", "members",
            "clients", "customers", "riders", "birds", "orders", "order", "seats", "rooms",
            "halls", "courts", "doctors", "patients", "trials", "users", "families", "kg",
            "litres", "liters", "pieces", "bookings", "parcels", "chairs", "tables"}  # fmt: skip
_COUNTED_STEMS = {english_stem(w) for w in _COUNTED}
_PRICE_BEFORE = re.compile(
    r"(?:\bfor|\bcosts?|\bcosting|\bprice[sd]?(?: at| of)?|\bpay(?:ing)?|"
    r"\bspend(?:ing)?|\bworth|\bbudget(?: of)?|\bkeemat)\s*$"
)


def amounts(text: str, context: bool = False) -> list[Amount]:
    """Quantities in `text`: a number with an optional currency marker, magnitude word, unit word
    and range.
      * a currency marker (Rs, PKR, rupees, $) makes it money;
      * a magnitude word (k, lakh, hazar ...) makes it money unless the next word is a counted
        noun ('3 lakh birds');
      * a bare number is money when `context` says the text is about money (a budget limit) or
        the words before it are a price cue ('for', 'costs', 'pay'), and the next word is not a
        noun that is counted; a following word such as 'then', 'because', 'this month' does not
        make it a unit; any other noun word is the unit ('5 staff', '50 chairs');
      * a bare number with none of that is not returned."""
    folded = re.sub(
        rf"between\s+({_NUM}(?:\s?(?:{_MAG}))?)\s+and\s+({_NUM})",
        r"\1 to \2",
        _unlist((text or "").casefold()),
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
        if unit_word in _TAIL or not unit_word:
            unit_word = ""
            # the figure ends where its last numeric piece ends, not after a skipped word
            end = max(m.end(g) for g in ("n1", "m1", "w1", "n2", "m2", "w2") if m.group(g))
        else:
            end = m.end()
        counted = unit_word in _COUNTED or english_stem(unit_word) in _COUNTED_STEMS
        priced = bool(_PRICE_BEFORE.search(folded[max(0, m.start() - 24) : m.start()]))
        if pre or unit_word in _CURRENCY:
            unit = "money"
        elif has_mag and not counted:
            unit = "money"  # '50k tablet', '50 hazar mein': a sum
        elif unit_word:
            unit = english_stem(unit_word)  # '5 staff', '50 chairs': what is counted
        elif context or priced:
            unit = "money"
        else:
            continue
        out.append(Amount(lo, hi, unit, m.start(), end))
    return out


_CEILING_BEFORE = re.compile(
    r"(?:\b(?:not|no|never|cannot|can't|can not|cant|won't|must not)\s+(?:[a-z']+\s+){0,3}?"
    r"(?:more than|above|over|beyond|exceed\w*|higher than|greater than|upto|up to)"
    r"|\b(?:under|below|less than|at most|at the most|up to|upto|max(?:imum)?(?: of)?|within"
    r"|limit(?:ed)? (?:to|of)|cap(?:ped)?(?: at)?|not exceed\w*|no more than"
    r"|(?:not|no)\s+(?:above|over|beyond)))\s*$"
)
_CEILING_AFTER = re.compile(
    r"^\s*(?:rupay\w*|rupees?|rs|pkr)?\s*(?:se|say)\s+(?:zyada|ziada|zyadah|upar|oopar|barh)"
)
_FLOOR = re.compile(r"\b(?:at least|minimum|not less|no less|no fewer|not fewer|kam se kam)\b")
_STRICT = re.compile(r"\b(?:under|below|less than)\s*$")
_MONEY_WORDS = re.compile(r"\b(?:spend|spent|pay|cost|costs|budget|afford|kharch|kharcha)\b")
# a benefit word directly in front of the figure: 'save 50000', 'profit of', 'sales of'
_BENEFIT_BEFORE = re.compile(
    r"\b(?:sav(?:e|es|ed|ing|ings)|earn(?:s|ed|ing)?|revenue|profit|sales|loss|lose|lost|losing"
    r"|bachat|kamai|munafa|nuqsan)(?:\s+(?:you|us|them|clients?|customers?|the business))?"
    r"(?:\s+(?:of|about|around|up to|an extra|extra|another))?\s*$"
)


class Ceiling(NamedTuple):
    value: float
    unit: str
    strict: bool


_CLAUSE_BREAK = re.compile(r"[,;.:]|\band\b|\bbut\b|\baur\b|\blekin\b")


def _floor_spans(text: str) -> list[tuple[int, int]]:
    """The clauses that state a floor ('we need at least 2 staff'); only they are left out."""
    spans = []
    for m in _FLOOR.finditer(text):
        start = max((x.end() for x in _CLAUSE_BREAK.finditer(text, 0, m.start())), default=0)
        nxt = _CLAUSE_BREAK.search(text, m.end())
        spans.append((start, nxt.start() if nxt else len(text)))
    return spans


def ceilings_of(limit_text: str, kind: str = "") -> list[Ceiling]:
    """The numeric ceilings a limit text states. Each figure the words call a ceiling is one;
    under a budget kind the first MONEY figure is one too when nothing else gave a money ceiling,
    so '2 staff, budget 20000 rupees' compares money, not staff. A clause that states a floor
    ('at least 2 staff') is skipped, the rest of the limit still counts."""
    text = (limit_text or "").casefold()[:4000]
    money_context = kind == "budget" or bool(_MONEY_WORDS.search(text))
    spans = _floor_spans(text)
    found = [
        a
        for a in amounts(text, context=money_context)
        if not any(lo <= a.start < hi for lo, hi in spans)
    ]
    out: list[Ceiling] = []
    for a in found:
        before, after = text[: a.start], text[a.end :]
        if _CEILING_BEFORE.search(before) or _CEILING_AFTER.search(after):
            out.append(Ceiling(a.hi, a.unit, bool(_STRICT.search(before))))
    if kind == "budget" and not any(c.unit == "money" for c in out):
        money = [a for a in found if a.unit == "money"]
        if money:
            out.append(Ceiling(money[0].hi, "money", False))
    return out


def _benefit(text: str, found: Amount) -> bool:
    return bool(_BENEFIT_BEFORE.search(text[max(0, found.start - 40) : found.start]))


def over_ceiling(idea_text: str, ceiling: Ceiling, said: set[tuple[float, float, str]]) -> bool:
    """True when an idea figure of the same kind is plainly above the ceiling. A figure the owner
    already stated (same unit), a benefit, and a range that reaches down to the ceiling are not
    costs."""
    text = (idea_text or "").casefold()
    for found in amounts(text):
        if found.unit != ceiling.unit or _benefit(text, found):
            continue
        if (found.lo, found.hi, found.unit) in said:
            continue
        if found.lo > ceiling.value or (ceiling.strict and found.lo >= ceiling.value):
            return True
    return False


def said_amounts(texts: list[str]) -> set[tuple[float, float, str]]:
    return {(a.lo, a.hi, a.unit) for t in texts for a in amounts(t)}


# ------------------------------------------------------- verb and tried rules

_FAMILIES = [
    {"buy", "purchase", "acquire", "procure"},
    {"hire", "recruit", "employ", "appoint"},
    {"spend", "pay", "invest"},
    {"refuse", "reject", "decline"},
    {"change", "alter", "modify", "replace", "switch", "swap"},
    {"close", "shut", "stop", "halt", "suspend"},
    {"fire", "dismiss", "sack", "terminate"},
    {"raise", "increase", "hike"},
    {"cut", "reduce", "lower", "decrease"},
    {"sell"},
    {"give", "offer", "grant"},
    {"use", "accept"},
]
# Roman Urdu verb roots, added to a group only when the case language is roman_ur
_RU_EXTRA = {"buy": {"kharid"}, "change": {"badal"}, "close": {"band"}, "sell": {"bech"}}
_ALTERNATIVES = {"buy": {"rent", "lease", "borrow", "share"}}
# verbs that are also nouns: in a noun position ('a fire alarm', 'each stop') they are not the verb
_HOMOGRAPHS = {"fire", "fires", "cut", "cuts", "raise", "raises", "close", "stop", "stops",
               "change", "changes", "switch", "switches", "lower", "swap", "swaps", "order",
               "orders", "pay", "offer", "offers", "use", "uses", "sale", "hike", "hikes",
               "decline", "halt", "reject", "grant", "grants"}  # fmt: skip
_NOUN_LEAD = {"a", "an", "the", "this", "that", "these", "those", "our", "your", "their", "my",
              "his", "her", "its", "each", "every", "any", "some", "no", "of", "in", "on", "with",
              "for", "per", "new", "live", "big", "small", "free", "one", "two", "three", "last",
              "next", "another", "same", "first", "second", "daily", "weekly"}  # fmt: skip
# verbs that the scorer's stop list drops from ordinary matching; still matchable as rule verbs
RULE_VERBS = {"give", "use", "make", "get", "put", "keep", "let"}
_FAMILY_CACHE: dict[str | None, tuple[list[set[str]], dict[str, frozenset[str]]]] = {}


def drop_noun_homographs(text: str) -> str:
    """The idea text without a verb-looking word that sits in a noun position ('a fire alarm',
    'each stop'), so a verb rule is not fired by a noun."""
    words = (text or "").split()
    keep = []
    for i, w in enumerate(words):
        bare = re.sub(r"[^a-z]", "", w.casefold())
        prev = re.sub(r"[^a-z]", "", words[i - 1].casefold()) if i else ""
        if bare in _HOMOGRAPHS and prev in _NOUN_LEAD:
            continue
        keep.append(w)
    return " ".join(keep)


def _family_stems(language: str | None) -> tuple[list[set[str]], dict[str, frozenset[str]]]:
    """Verb groups and their milder alternatives, stemmed in the same full space as an idea."""
    if language not in _FAMILY_CACHE:
        extra = _RU_EXTRA if language == "roman_ur" else {}
        groups = []
        for g in _FAMILIES:
            words = set(g)
            for key, more in extra.items():
                if key in g:
                    words |= more
            groups.append({stem_ascii(w, language, True) for w in words})
        alts = {
            stem_ascii(k, language, True): frozenset(stem_ascii(w, language, True) for w in v)
            for k, v in _ALTERNATIVES.items()
        }
        _FAMILY_CACHE[language] = (groups, alts)
    return _FAMILY_CACHE[language]


_NEG = re.compile(
    r"\b(?:cannot|can't|can not|cant|must not|mustn't|may not|unable to|not able to|"
    r"not allowed to|no way to|"
    r"(?:do not|don't|dont|will not|won't)\s+(?:want|wish|intend|plan)\s+to)\s+"
    r"(?:(?:afford|be able|be allowed)\s+to\s+)?(?P<verb>[a-z']+)\s*(?P<obj>[^,;.:!?()]*)"
)
_NEG_PASSIVE = re.compile(
    r"(?P<obj>[^,;.:!?()]+?)\s+(?:cannot|can't|can not|cant|must not|may not)\s+be\s+"
    r"(?P<verb>[a-z]+)"
)
_NEG_RU_TAIL = re.compile(r"\s(?:nahi|nahin)\s+(?:kar\s+)?sakt[a-z]*")
_NEG_RU_VERB = re.compile(r"\s(?:nahi|nahin)\s+(?P<verb>badal|kharid|bech|band|hata)[a-z]*\s+sakt")
_CUT = re.compile(r"\b(?:because|as|so|since|but|when|while|if|taake|kyunke)\b")
_TIME = re.compile(
    r"\b(?:this|next|last|is|iss|agle) (?:year|month|week|season|quarter|saal|mahine)\b"
    r"|\b(?:right now|for now|at the moment|at all|anymore|any more|abhi)\b"
)
_FILLER = {"new", "more", "another", "second", "extra", "any", "additional", "other", "anyone",
           "anybody", "anything", "someone", "people", "ones", "naya", "naye", "nayi"}  # fmt: skip
_TRIED_MARK = re.compile(r"\b(?:tried|try|aazma\w*|pehle)\b")
# 'did not work' is an outcome on its own; 'failed' and the like count only beside 'tried'
_FAIL_ALONE = re.compile(
    r"\b(?:did not work|didn't work|didnt work|does not work|doesn't work|not worked|"
    r"made no difference|did nothing)\b"
)
_FAIL_TRIED = re.compile(
    r"\b(?:failed|useless|flopped|no use|no result|kaam nahi|nakam|faida nahi|fayda nahi)\b"
)
_TRIED_LEAD = re.compile(
    r"^(?:(?:we|i|hum|humne|already|have|had|previously|once|maine)\s+)*"
    r"(?:(?:tried|try|aazmaya)\s+)?"
)
_TRIED_TAIL = re.compile(
    r"(?:\s*(?:,|\band\b|\bbut\b|\blekin\b|\bpar\b|\bmagar\b|\bit\b|\bthat\b|\bthey\b|\bwhich\b|"
    r"\bbefore\b|\bearlier\b|\balready\b|\bpehle\b|\btry\b|\btried\b|\blast (?:year|month|week)\b|"
    r"\bin the past\b|\bpreviously\b|\bkiya\b|\btha\b|\baazmaya\b|\bonce\b))*\s*$"
)
_NOT_A_VERB = {"be", "have", "do", "go", "get"}
_MAX_LIMIT = 4000  # characters of a limit text read for rules; keeps parsing linear


class Rule(NamedTuple):
    kind: str  # "neg" (cannot VERB OBJECT) or "tried" (OBJECT failed before)
    verbs: frozenset[str]  # full stems of the verb group; empty for "tried"
    alternatives: frozenset[str]  # full stems of verbs that do not break the limit
    objects: frozenset[str]  # full stems of the object's content words
    need: int  # how many object stems an idea must contain


def _need(count: int) -> int:
    return count if count <= 2 else math.ceil(2 * count / 3)


StemsOf = Callable[[str, str | None], set[str]]


def _object_stems(
    text: str, language: str | None, stems_of: StemsOf, last: bool = False
) -> frozenset[str]:
    parts = _CUT.split(_TIME.sub(" ", text))
    cut = parts[-1] if last else parts[0]
    cut = re.sub(r"\b(?:" + "|".join(sorted(_FILLER)) + r")\b", " ", cut)
    return frozenset(stems_of(cut, language))


def parse_rules(limit_text: str, language: str | None, stems_of: StemsOf) -> list[Rule]:
    """Verb and tried rules read from a limit's own text. `stems_of(text, language)` must return
    FULL stems, so a rule and an idea are always compared in the strict space.

    Read: 'cannot|must not|unable to VERB OBJECT' (also with the curly apostrophe, and 'cannot
    afford OBJECT' as buy or spend), 'OBJECT cannot be VERBed', 'we do not want to VERB OBJECT',
    Roman Urdu 'OBJECT VERB nahi kar sakte', and a tried-and-failed text. Not handled: a
    prohibition without a modal ('no hiring'), 'never VERB', and a verb whose object is a figure
    (that is compared as a number)."""
    text = (limit_text or "").casefold().replace("’", "'").replace("‘", "'")
    text = text[:_MAX_LIMIT]
    rules: list[Rule] = []
    seen: set[tuple[str, str]] = set()
    groups, alts = _family_stems(language)
    afford = stem_ascii("afford", language, True)
    money_verbs = {stem_ascii("buy", language, True), stem_ascii("spend", language, True)}

    def add_neg(verb: str, obj: str, last: bool = False) -> None:
        if verb in _NOT_A_VERB:
            return
        stem = stem_ascii(verb, language, True)
        if stem == afford:
            group = {stem}.union(*(g for g in groups if g & money_verbs))
        else:
            group = next((g for g in groups if stem in g), {stem})
        alt = frozenset().union(*(alts.get(s, frozenset()) for s in group))
        objects = _object_stems(obj, language, stems_of, last)
        if any(any(ch.isdigit() for ch in o) for o in objects):
            return  # a figure in the limit is compared as a number, not as a word
        key = (stem, ",".join(sorted(objects)))
        if key not in seen:
            seen.add(key)
            rules.append(Rule("neg", frozenset(group), alt, objects, _need(len(objects))))

    for m in _NEG.finditer(text):
        add_neg(m.group("verb"), m.group("obj"))
    for m in _NEG_PASSIVE.finditer(text):
        add_neg(m.group("verb"), m.group("obj"), last=True)
    if language == "roman_ur":
        for m in _NEG_RU_TAIL.finditer(text):
            head = re.split(r"[,;.:!?()]", text[: m.start()])[-1][-160:].split()
            if len(head) >= 2:
                add_neg(head[-1], " ".join(head[:-1]))
        for m in _NEG_RU_VERB.finditer(text):
            head = re.split(r"[,;.:!?()]", text[: m.start()])[-1][-160:]
            add_neg(m.group("verb"), head)
    fail = _FAIL_ALONE.search(text) or (_TRIED_MARK.search(text) and _FAIL_TRIED.search(text))
    if fail:
        before = text[: fail.start()]
        for marker in ("pehle", "try ", "aazma"):
            at = before.find(marker)
            if at > 0:
                before = before[:at]
        before = _TRIED_TAIL.sub("", _TRIED_LEAD.sub("", before.strip()[-240:]))
        objects = _object_stems(before, language, stems_of) - {"tried", "try"}
        if objects:
            rules.append(Rule("tried", frozenset(), frozenset(), objects, _need(len(objects))))
    return rules


def rule_hit(rule: Rule, idea: set[str], idea_verbs: set[str] | None = None) -> bool:
    """The idea does what the rule forbids: the verb group (for 'cannot') and enough of the
    object. A 'cannot VERB' with no object words is broken by the verb alone. `idea` is the idea's
    FULL stem set; `idea_verbs` is the same without nouns that look like verbs ('a fire alarm')."""
    if rule.kind == "neg" and not (rule.verbs & (idea if idea_verbs is None else idea_verbs)):
        return False
    return len(rule.objects & idea) >= rule.need


def rule_alternative(rule: Rule, idea: set[str]) -> bool:
    """The idea uses a milder verb the limit does not cover ('rent' against 'cannot buy')."""
    return rule.kind == "neg" and bool(rule.alternatives & idea) and not (rule.verbs & idea)
