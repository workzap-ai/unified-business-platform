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
  * a limit text such as 'cannot buy a new oven' is read as a verb group plus an object, and
    'tried a discount before and it failed' as a repeated failed attempt. Only modal prohibitions
    ('cannot', 'must not', 'unable to', 'do not want to') count; a descriptive 'never' or
    'fails to' is not a prohibition. Only the listed verb groups are known; any other verb
    stands for itself.
  * money versus counted nouns: a figure with a currency marker (or 'worth') is money. A figure
    with a magnitude word is money, except that a plural noun right after it ('50k eggs', 'your
    50k followers') is a count unless a price word (for, costs, pay, spend, worth, budget) comes
    before it; a singular noun ('a 50k tablet') stays money by decision, and a counted noun from
    a short list (staff, days, guests, birds ...) is always a count. A bare figure is money in a
    money context (a limit that talks about spending, or a budget kind), after a price word or a
    buying verb ('buy a 50000 tablet', 'invest 50000', 'get a system at 50000'; a noun after it
    needs 1000 or more to be read as a product), and a following 'then', 'because', 'this month'
    is not a unit. An idea's bare figure with none of that is ignored. '2.5m', '1m' and '5 k'
    are read.
  * not costs: an idea figure written as income or a saving (sell, charge, earn, collect, raise,
    receive, make, save, profit ...) and a figure the owner stated, with the same value and unit,
    that the idea only restates; the same figure written as something bought or paid ('buy new
    software for Rs 50000') is a new cost.
  * a stated goal is not a prohibition: 'cannot afford downtime', 'cannot lose customers' and
    'cannot risk X' make no rule; 'cannot afford X' blocks buying, spending or hiring only when X
    is something a business buys (equipment, software, staff, money ...).
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
from functools import lru_cache
from typing import NamedTuple

MAGNITUDES = {
    "k": 1e3, "thousand": 1e3, "thousands": 1e3, "hazar": 1e3, "hazaar": 1e3, "hazaro": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "lakhon": 1e5,
    "crore": 1e7, "crores": 1e7, "karor": 1e7, "karore": 1e7,
    "million": 1e6, "millions": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9, "arab": 1e9,
}  # fmt: skip
_MAG = r"k|mn|m|thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|millions?|billion|arab"
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
    return any(ch in _VOWELS + "y" for ch in word)


_IRREGULAR = {"using": "use", "used": "use", "dying": "die", "lying": "lie", "tying": "tie"}
_DOUBLE_L = {"cancell", "travell", "labell", "modell", "fuell", "levell", "signall"}
_KEEP_E = {"plane"}


def _consonant(ch: str) -> bool:
    return ch.isalpha() and ch not in _VOWELS


def _cvc(word: str) -> bool:
    return (
        len(word) >= 3
        and _consonant(word[-3])
        and word[-2] in _VOWELS + "y"
        and _consonant(word[-1])
        and word[-1] not in "wxy"
    )


def english_plural(token: str) -> str:
    """Strip an English plural: -ies, -sses/-shes/-ches/-xes/-zes, -s (not -ss, -us, -is)."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("sses", "shes", "ches", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def english_stem(token: str) -> str:
    """Strip plural, -ing, -ed, -ly and a trailing e; undouble a final consonant. The whole stem
    is returned; the soft space cuts it to five letters (`relevance`). A short stem keeps its e
    ('care', 'rate', 'cute' stay apart from 'car', 'rat', 'cut') and a short stem left by -ing or
    -ed gets it back ('hiring' and 'hire' agree)."""
    if token in _IRREGULAR:
        return _IRREGULAR[token]
    t = english_plural(token)
    stripped = False
    if len(t) > 5 and t.endswith("ing") and t not in _NOT_ING and _has_vowel(t[:-3]):
        t, stripped = t[:-3], True
    elif len(t) > 4 and t.endswith("ied"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("eed"):
        t = t[:-1]  # 'freed' and 'agreed' end in a word that already ends in e
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


_WORDS = r"thousands?|haz+aro?|lakhs?|lacs?|lakhon|crores?|karore?|millions?|billion|arab"
_RANGE_FOLD = re.compile(
    rf"(?<![\w.,])({_NUM})\s?(?:-|–|—|to)\s?({_NUM})(?:(mn|m)\b|\s?(k)\b|\s*({_WORDS})\b)",
    re.IGNORECASE,
)
_FOLD = re.compile(
    rf"(?<![\w.,])({_NUM})(?:(mn|m)\b|\s?(k)\b|\s*({_WORDS})\b)",
    re.IGNORECASE,
)


def fold_magnitudes(text: str) -> str:
    """'3 lakh' -> '300000', '20k' -> '20000', '10-15k' -> '10000 15000'. Figures only; the
    magnitude word disappears, so '3 lakh' and '3,00,000' are the same token afterwards."""

    def one(raw: str, mag: str) -> str | None:
        number = _plain(raw)
        return None if number is None else _digits(number * MAGNITUDES[mag.casefold()])

    def range_sub(m: re.Match[str]) -> str:
        mag = (m.group(3) or m.group(4) or m.group(5)).casefold()
        lo, hi = one(m.group(1), mag), one(m.group(2), mag)
        return m.group(0) if lo is None or hi is None else f"{lo} {hi}"

    def sub(m: re.Match[str]) -> str:
        done = one(m.group(1), (m.group(2) or m.group(3) or m.group(4)).casefold())
        return m.group(0) if done is None else done

    return _FOLD.sub(sub, _RANGE_FOLD.sub(range_sub, _unlist(text or "")))


class Amount(NamedTuple):
    lo: float
    hi: float
    unit: str  # "money", or the stem of the word that follows ('staff', 'guest'), or ""
    start: int
    end: int
    unclear: bool = False  # '10000 each' with no quantity before it


_AMOUNT = re.compile(
    rf"(?<![\w.,])(?P<pre>(?:rs\.?|pkr|inr|usd|aed)\s?|[$₹]\s?)?(?P<n1>{_NUM})"
    rf"(?:(?P<m1>mn|m)\b|\s?(?P<k1>k)\b|\s*(?P<w1>{_WORDS})\b)?"
    rf"(?:\s?(?:-|–|—|to)\s?(?:rs\.?\s?|pkr\s?|[$₹]\s?)?(?P<n2>{_NUM})"
    rf"(?:(?P<m2>mn|m)\b|\s?(?P<k2>k)\b|\s*(?P<w2>{_WORDS})\b)?)?"
    rf"(?:[\s-]+(?P<unit>[a-z$₹]+))?",
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
# a price word right before a figure: the figure is what something costs
_PRICE_BEFORE = re.compile(
    r"(?:\bfor|\bcosts?|\bcosting|\bprice[sd]?(?: at| of)?|\bpay(?:ing)?|"
    r"\bspend(?:ing)?|\bworth|\bbudget(?: of)?|\bkeemat)\s*$"
)
# a buying verb before a figure, at most a determiner or adjective between ('buy a 50000 tablet')
_BUY_BEFORE = re.compile(
    r"\b(?:buy|buys|buying|purchase|purchasing|get|gets|getting|invest|investing|order|install|"
    r"rent|lease|acquire)\b(?:\s+(?:a|an|the|one|new|another|our|your))*\s*$"
)
_AT_BEFORE = re.compile(r"\bat\s*(?:rs\.?\s*)?$")
_EACH = re.compile(r"^\s*(?:each|apiece|per (?:piece|unit|item))\b")
_X_BEFORE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*$")
_QTY_BEFORE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:x\s*)?(?:[a-z-]+\s+){0,2}(?:at|for|@)\s*(?:rs\.?\s*)?$|(\d+)\s*x\s*$"
)


def _is_plural_noun(word: str) -> bool:
    return len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is"))


def _amounts(text: str, context: bool) -> tuple[Amount, ...]:
    """Quantities in `text`: a number with an optional currency marker, magnitude word, unit word
    and range.
      * a currency marker (Rs, PKR, rupees, $) or 'worth' after it makes it money;
      * a magnitude word (k, m, lakh, hazar ...) makes it money, except that a plural noun right
        after it ('50k eggs', 'your 50k followers') is a COUNT unless a price word (for, costs,
        pay, spend, worth, budget) comes before it; a counted noun from the list is always a
        count; '50k tablet' (singular) stays money;
      * a bare number is money when `context` says the text is about money (a limit that talks
        about spending or a budget kind), or a price word or a buying verb ('buy a', 'invest',
        'get a ... at') comes before it, and it has no counted noun after it; a noun after a bare
        figure under such a cue is a product ('a 50000 tablet') only from 1000 up; 'then',
        'because', 'this month' after a figure are not a unit; any other noun word is the unit
        ('5 staff', '50 chairs');
      * a bare number with none of that is not returned."""
    folded = re.sub(
        rf"between\s+({_NUM}(?:\s?(?:{_MAG}))?)\s+and\s+({_NUM})",
        r"\1 to \2",
        _unlist(collapse(text).casefold()[:_MAX_AMOUNT_TEXT]),
    )
    out: list[Amount] = []
    for m in _AMOUNT.finditer(folded):
        n1, n2 = _plain(m.group("n1")), _plain(m.group("n2")) if m.group("n2") else None
        if n1 is None or (m.group("n2") and n2 is None):
            continue
        m1 = _mult(m.group("m1") or m.group("k1"), m.group("w1"))
        m2 = _mult(m.group("m2") or m.group("k2"), m.group("w2"))
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
            end = max(
                m.end(g) for g in ("n1", "m1", "k1", "w1", "n2", "m2", "k2", "w2") if m.group(g)
            )
        else:
            end = m.end()
        counted = unit_word in _COUNTED or english_stem(unit_word) in _COUNTED_STEMS
        cut = folded[max(0, m.start() - 40) : m.start()]
        strict = bool(_PRICE_BEFORE.search(cut))
        buying = bool(_BUY_BEFORE.search(cut))
        weak = bool(_AT_BEFORE.search(cut))
        big = hi >= 1000
        if pre or unit_word in _CURRENCY or unit_word == "worth":
            unit = "money"
        elif has_mag and not counted:
            plural = _is_plural_noun(unit_word)
            unit = english_stem(unit_word) if plural and not strict else "money"
        elif unit_word and counted:
            unit = english_stem(unit_word)  # '5 staff', '50 chairs': what is counted
        elif unit_word:
            product = (context or strict or buying) and big
            unit = "money" if product else english_stem(unit_word)
        elif context or strict or buying or (weak and big):
            unit = "money"
        else:
            continue
        unclear = False
        times = (
            _X_BEFORE.search(folded[max(0, m.start() - 24) : m.start()])
            if unit == "money"
            else None
        )
        if times:
            lo, hi = lo * float(times.group(1)), hi * float(times.group(1))
        elif unit == "money" and _EACH.search(folded[end : end + 24]):
            found_qty = _QTY_BEFORE.search(folded[max(0, m.start() - 40) : m.start()])
            qty = found_qty and (found_qty.group(1) or found_qty.group(2))
            if qty:
                lo, hi = lo * float(qty), hi * float(qty)
            else:
                unclear = True
        out.append(Amount(lo, hi, unit, m.start(), end, unclear))
    return tuple(out)


_SPELLED = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|"
    r"seventy|eighty|ninety|hundred|do|teen|char|paanch|das|bees|pachas)\s+"
    r"(?:hundred|thousand|lakh|lac|crore|million|hazar|hazaar)\b",
    re.IGNORECASE,
)


def spelled_number(text: str) -> bool:
    """The text writes an amount in words ('five thousand'); such a figure is not read."""
    return bool(_SPELLED.search(collapse(text)[:MAX_IDEA_TEXT]))


def unclear_quantity(text: str) -> bool:
    """A price per piece ('10000 each') with no quantity before it."""
    return any(a.unclear for a in amounts(text))


def non_latin(text: str) -> bool:
    """The text has letters in Arabic/Urdu or Devanagari script, which the scorer does not read."""
    return any(
        "\u0600" <= ch <= "\u06ff"
        or "\u0750" <= ch <= "\u077f"
        or "\u0900" <= ch <= "\u097f"
        or "\ufb50" <= ch <= "\ufdff"
        or "\ufe70" <= ch <= "\ufeff"
        for ch in text or ""
    )


_CEILING_BEFORE = re.compile(
    r"(?:\b(?:not|no|never|cannot|can't|can not|cant|won't|must not)\s+(?:[a-z']+\s+){0,3}?"
    r"(?:more than|above|over|beyond|exceed\w*|higher than|greater than|upto|up to|cross|"
    r"surpass|go over)"
    r"|\b(?:under|below|less than|at most|at the most|up to|upto|max(?:imum)?(?: of)?|within"
    r"|limit(?:ed)? (?:to|of)|cap(?:ped)?(?: at)?|not exceed\w*|no more than"
    r"|budget(?: of| is| limit(?: of| is)?)?|spending limit(?: of| is)?"
    r"|(?:not|no)\s+(?:above|over|beyond)))\s*$"
)
_CEILING_AFTER = re.compile(
    r"^\s*(?:rupay\w*|rupees?|rs|pkr)?\s*"
    r"(?:(?:se|say)\s+(?:zyada|ziada|zyadah|upar|oopar|barh)|at most|or less|or under|or below"
    r"|and below|maximum|max|tops)\b"
)
_FLOOR = re.compile(r"\b(?:at least|minimum|not less|no less|no fewer|not fewer|kam se kam)\b")
_STRICT = re.compile(r"\b(?:under|below|less than)\s*$")
_MONEY_WORDS = re.compile(r"\b(?:spend|spent|pay|cost|costs|budget|afford|kharch|kharcha)\b")
# a benefit or income word directly in front of the figure: 'save 50000', 'profit of', 'earn',
# 'get Rs 50000', 'collect', 'raise'
_BENEFIT_BEFORE = re.compile(
    r"\b(?:sav(?:e|es|ed|ing|ings)|earn(?:s|ed|ing)?|revenue|profit|sales|loss|lose|lost|losing"
    r"|income|turnover|make|makes|made|get|gets|collect(?:s|ed|ing)?|receiv(?:e|es|ed|ing)"
    r"|rais(?:e|es|ed|ing)|bachat|kamai|munafa|nuqsan)"
    r"(?:\s+(?:you|us|them|clients?|customers?|the business))?"
    r"(?:\s+(?:of|about|around|up to|an extra|extra|another|over))?\s*$"
)
# selling or charging anywhere earlier in the clause makes the figure income, unless it also buys
_INCOME_CLAUSE = re.compile(r"\b(?:sell|sells|sold|selling|resell|charge|charges|charging)\b")
# 'rent out the hall' is letting, not renting: income, never a purchase
_PHRASAL_OUT = re.compile(r"\b(?:rent|lease|hire|let)s?(?:ed|ing)?\s+out\b")
_BUY_VERBS = re.compile(
    r"\b(?:buy|buys|buying|purchase|purchasing|invest|investing|order|install|rent|lease|hire|"
    r"pay|paying|spend|spending)\b"
)
_INCOME_ANY = re.compile(
    r"\b(?:earn|earns|earned|earning|income|revenue|profit|sales|turnover|make|makes|salary|"
    r"collect|collects|receive|receives|sell|sells|sold|kamai|munafa)\b"
)
_SPEND_ROLE = re.compile(
    r"\b(?:buy|buys|buying|purchase|purchasing|get|gets|invest|investing|order|install|rent|lease|"
    r"hire|pay|paying|spend|spending|cost|costs|costing|price|priced|at|for)\b"
)


def _clause_before(text: str, pos: int) -> str:
    return _IDEA_BREAK.split(text[:pos])[-1][-120:]


class Ceiling(NamedTuple):
    value: float
    unit: str
    strict: bool


_CLAUSE_BREAK = re.compile(
    r"[,;.:]|\b(?:since|because|while|as|so|with|but|and|aur|lekin|taake|kyunke)\b"
)
_IDEA_BREAK = re.compile(r"[,;.:]|\b(?:and|but|so|because|while|then)\b")


def _floor_spans(text: str) -> list[tuple[int, int]]:
    """The clauses that state a floor ('we need at least 2 staff'); only they are left out."""
    spans = []
    for m in _FLOOR.finditer(text):
        start = max((x.end() for x in _CLAUSE_BREAK.finditer(text, 0, m.start())), default=0)
        nxt = _CLAUSE_BREAK.search(text, m.end())
        spans.append((start, nxt.start() if nxt else len(text)))
    return spans


def _ceilings_of(limit_text: str, kind: str) -> tuple[Ceiling, ...]:
    """The numeric ceilings a limit text states. Each figure the words call a ceiling is one;
    under a budget kind the first MONEY figure is one too when nothing else gave a money ceiling,
    so '2 staff, budget 20000 rupees' compares money, not staff. A clause that states a floor
    ('at least 2 staff') is skipped, the rest of the limit still counts."""
    text = collapse(limit_text).casefold()[:MAX_LIMIT_TEXT]
    money_context = kind == "budget" or bool(_MONEY_WORDS.search(text))
    spans = _floor_spans(text)
    found = [
        a
        for a in amounts(text, context=money_context)
        if not any(lo <= a.start < hi for lo, hi in spans)
    ]
    # a bare figure of 1000 or more beside an explicit ceiling cue ('20000 at most') is a sum
    seen = {a.start for a in found}
    found += [
        a
        for a in amounts(text, context=True)
        if a.start not in seen
        and a.unit == "money"
        and a.hi >= 1000
        and not any(lo <= a.start < hi for lo, hi in spans)
    ]
    out: list[Ceiling] = []
    for a in found:
        before, after = text[: a.start], text[a.end :]
        if _CEILING_BEFORE.search(before) or _CEILING_AFTER.search(after):
            out.append(Ceiling(a.hi, a.unit, bool(_STRICT.search(before))))
    if kind == "budget" and not any(c.unit == "money" for c in out):
        money = [a for a in found if a.unit == "money" and not _income_role(text, a)]
        if money:
            out.append(Ceiling(money[0].hi, "money", False))
    return tuple(out)


def _benefit(text: str, found: Amount) -> bool:
    """The figure is income or a saving, not a cost: a benefit word right before it, or selling or
    charging earlier in its clause with no buying verb there."""
    if _BENEFIT_BEFORE.search(text[max(0, found.start - 40) : found.start]):
        return True
    clause = _clause_before(text, found.start)
    plain = _PHRASAL_OUT.sub(" ", clause)
    income = _INCOME_CLAUSE.search(clause) or _PHRASAL_OUT.search(clause)
    return bool(income and not _BUY_VERBS.search(plain))


def _income_role(text: str, found: Amount) -> bool:
    return _benefit(text, found) or bool(_INCOME_ANY.search(_clause_before(text, found.start)))


def _spend_role(text: str, found: Amount) -> bool:
    """The figure is written as something bought or paid ('buy ... for', 'costs', 'at')."""
    return bool(_SPEND_ROLE.search(_clause_before(text, found.start)))


def over_ceiling(idea_text: str, ceiling: Ceiling, said: set[tuple[float, float, str]]) -> bool:
    """True when an idea figure of the same kind is plainly above the ceiling. Not costs: a
    benefit or income figure; a figure the owner already stated (same value and unit) when the
    idea only restates it and does not buy or pay it ('your 50000 diary software' is restated,
    'buy new software for Rs 50000' is a new cost); a range that reaches down to the ceiling."""
    text = (idea_text or "").casefold()
    for found in amounts(text):
        if found.unit != ceiling.unit or _benefit(text, found):
            continue
        if (found.lo, found.hi, found.unit) in said and not _spend_role(text, found):
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
_RU_EXTRA = {
    "buy": {"kharid", "kharido", "kharidna", "kharidne", "kharidein", "kharidiye", "kharidlo",
            "khareed", "khareedna", "khareedein", "khareedo"},
    "change": {"badal", "badalna", "badlein", "badlo"},
    "close": {"band"},
    "sell": {"bech", "bechna", "bechein", "becho", "bechiye"},
    "hire": {"rakh", "rakhna", "rakhne", "rakhein", "rakho", "rakhiye", "rakhen"},
    "use": {"le", "lena", "lein", "lo", "lijiye", "leta", "lete", "liya", "len"},
    "give": {"de", "dena", "dein", "do", "dijiye", "dete", "diya", "den"},
}  # fmt: skip
# Roman Urdu verbs the scorer knows; a limit with any other verb is 'unknown', never scored
RU_RULE_VERBS = {"le", "lo", "de", "do", "len", "den"}
_RU_INSTALL = {"install", "lagana", "lagao", "lagayein", "lagaye", "lagaiye", "lagane", "lagayen"}
# 'run a discount week' is offering one; only a rule whose own verb is give/offer/grant adds these
_OFFER_ALSO = {"run", "start", "launch", "host", "promote", "announce"}
# 'cannot afford equipment' covers the things that are equipment
_HYPERNYMS = {
    "equipment": {"oven", "fridge", "freezer", "machine", "mixer", "grinder", "printer", "scanner",
                  "generator", "tractor", "scale", "camera", "tool", "tablet", "computer", "laptop",
                  "mill", "van", "truck", "vehicle", "pos"},
    "software": {"app", "system", "platform", "tool", "program", "crm", "website"},
    "staff": {"employee", "worker", "helper", "clerk", "cleaner", "cook", "driver", "assistant",
              "cashier", "receptionist", "manager", "rider", "guard", "accountant", "waiter",
              "supervisor", "technician", "electrician", "plumber", "nurse", "teacher"},
    "machinery": {"machine", "mill", "tractor", "mixer", "grinder", "oven"},
}  # fmt: skip
# an idea that does one of these to the goal's subject breaks 'cannot afford X' / 'cannot lose X'
_GOAL_ACTIONS = {"cause", "create", "increase", "allow", "accept", "risk", "invite", "lose",
                 "miss", "waste", "delay", "harm", "trigger"}  # fmt: skip
_NEGATORS = {"not", "dont", "never", "avoid", "avoiding", "without", "cannot", "wont"}
_ALTERNATIVES = {"buy": {"rent", "lease", "borrow", "share"}}
# verbs that are also nouns: in a noun position ('a fire alarm', 'each stop') they are not the verb
_HOMOGRAPHS = {"hire", "hires", "band", "bands", "fire", "fires", "cut", "cuts", "raise", "raises",
               "close", "stop", "stops",
               "change", "changes", "switch", "switches", "lower", "swap", "swaps", "order",
               "orders", "pay", "offer", "offers", "use", "uses", "sale", "hike", "hikes",
               "decline", "halt", "reject", "grant", "grants"}  # fmt: skip
_NOUN_LEAD = {"a", "an", "the", "this", "that", "these", "those", "our", "your", "their", "my",
              "his", "her", "its", "each", "every", "any", "some", "no", "of", "in", "on", "with",
              "for", "per", "new", "live", "big", "small", "free", "one", "two", "three", "last",
              "next", "another", "same", "first", "second", "daily", "weekly", "monthly", "yearly",
              "annual", "safety", "extra"}  # fmt: skip
# a noun that follows a verb-looking word: 'fire extinguisher', 'fire safety'
_NOUN_FOLLOW = {"alarm", "alarms", "drill", "drills", "extinguisher", "extinguishers", "exit",
                "exits", "safety", "truck", "trucks", "department", "hazard", "hazards", "door",
                "doors", "fighter", "fighters", "code", "insurance", "marshal", "escape",
                "station", "stations", "sale", "sales"}  # fmt: skip
_NOT_VERB_NEXT = {"to", "by", "enough", "together"}
# verbs that the scorer's stop list drops from ordinary matching; still matchable as rule verbs
RULE_VERBS = {"give", "use", "make", "get", "put", "keep", "let"}
_FAMILY_CACHE: dict[str | None, tuple[list[set[str]], dict[str, frozenset[str]]]] = {}


def drop_noun_homographs(text: str) -> str:
    """The idea text without a verb that is negated ('do not buy', 'avoid losing'), without
    'hire out' and its kind, and without a verb-looking word that sits in a noun position: after a
    determiner
    or a preposition ('a fire alarm', 'each stop', 'a new hire'), before a noun it modifies
    ('fire extinguishers', 'fire safety'), or in 'close to'. A verb rule is then not fired by it."""
    words = [w for w in re.split(r"[\s-]+", collapse(text)[:MAX_IDEA_TEXT]) if w]
    bare = [re.sub(r"[^a-z]", "", w.casefold()) for w in words]
    keep = []
    for i, w in enumerate(words):
        prev1 = bare[i - 1] if i else ""
        prev2 = bare[i - 2] if i > 1 else ""
        if prev1 in _NEGATORS or (prev1 == "of" and prev2 == "instead"):
            continue  # 'do not buy', 'avoid losing', 'never causes': the verb is negated
        if (
            bare[i] in {"hire", "rent", "lease", "let"}
            and i + 1 < len(words)
            and bare[i + 1] == "out"
        ):
            continue  # 'hire out the room' is letting, not hiring
        if bare[i] in _HOMOGRAPHS:
            prev = bare[i - 1] if i else ""
            nxt = bare[i + 1] if i + 1 < len(words) else ""
            if (
                prev in _NOUN_LEAD
                or nxt in _NOUN_FOLLOW
                or (bare[i] == "close" and nxt in _NOT_VERB_NEXT)
            ):
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
        if language == "roman_ur":
            groups.append({stem_ascii(w, language, True) for w in _RU_INSTALL})
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
_PASSIVE_MARKERS = (" cannot be ", " can't be ", " can not be ", " must not be ", " may not be ")
_NEG_RU_SPLIT = re.compile(r" (?:nahi|nahin) ")
_RU_SAKT = re.compile(r"^(?P<mid>(?:[a-z]+ ){0,2})sakt[a-z]*")
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
_TRIED_TAIL_WORDS = {",", "and", "but", "lekin", "par", "magar", "it", "that", "they", "which",
                     "before", "earlier", "already", "pehle", "try", "tried", "previously", "kiya",
                     "tha", "aazmaya", "once"}  # fmt: skip


def _strip_tried_tail(text: str) -> str:
    """Drop the words that close a 'tried X before and it failed' text, one from the end at a
    time (linear, unlike a repeated regex group)."""
    words = text.replace(",", " , ").split()
    while words:
        last = words[-1]
        if last in _TRIED_TAIL_WORDS:
            words.pop()
        elif len(words) >= 2 and words[-2] == "last" and last in {"year", "month", "week"}:
            del words[-2:]
        elif words[-3:] == ["in", "the", "past"]:
            del words[-3:]
        else:
            break
    return " ".join(words)


# a verb's particle: 'hire out' and 'hire on' are not 'hire'; a limit that names one is broken
# by the same verb and particle, and by nothing else
# ('on' and 'down' are left out: 'close on Sundays' is a preposition, 'hire on' stays 'hire')
_PARTICLES = {"out", "up", "off", "away"}
# a limit object made only of these says nothing ('cannot afford much'); no rule is made from it
_VAGUE = {
    "much", "lot", "lots", "alot", "more", "many", "any", "anything", "something", "stuff",
    "things", "thing", "extra", "extras", "enough", "little", "less", "anymore",
    "zyada", "ziada", "bohat", "bahut", "bohot", "kuch", "sab", "har", "cheez", "cheezein",
    "\u0628\u06c1\u062a", "\u0632\u06cc\u0627\u062f\u06c1", "\u06a9\u0686\u06be",
    "\u0633\u0628", "\u092c\u0939\u0941\u0924", "\u091c\u093c\u094d\u092f\u093e\u0926\u093e",
    "\u091c\u094d\u092f\u093e\u0926\u093e", "\u0915\u0941\u091b", "\u0938\u092c",
    "\u0643\u062b\u064a\u0631", "\u0627\u0644\u0643\u062b\u064a\u0631",
    "\u0643\u062b\u064a\u0631\u0627", "\u0627\u0644\u0645\u0632\u064a\u062f",
    "\u0634\u064a\u0621", "\u0634\u064a\u0626\u0627", "\u0643\u0644",
}  # fmt: skip
_OBJECT_SMALL = {"a", "an", "the", "of", "to", "for", "it", "this", "that", "so", "very", "too",
                 "our", "my", "we", "at", "all", "hum", "ko", "on", "in", "with", "by", "from",
                 "than", "and", "or", "is", "are", "be"}  # fmt: skip
# 'anything', 'anyone': a universal object. 'cannot hire anyone' forbids the verb, so it stays a
# rule; with an adjective or a generic noun after it ('anything expensive') it says nothing.
_UNIVERSAL = {"anything", "anyone", "anybody", "everything", "everyone", "everybody", "any",
              "someone", "something", "somebody"}  # fmt: skip
# adjectives and determiners: they describe a thing but name none
_ADJECTIVES = {
    "ornate", "opulent", "glossy", "swanky", "snazzy", "elegant", "stylish", "futuristic",
    "innovative", "bespoke", "robust", "scalable", "versatile", "flexible", "powerful",
    "intelligent", "smart", "seamless", "comprehensive", "ambitious", "aggressive", "radical",
    "drastic", "dramatic", "substantial", "considerable", "significant", "hefty", "massive",
    "enormous", "colossal", "immense", "bulky", "sophisticated", "gigantic", "deluxe", "trendy",
    "flashy", "elaborate", "shiny", "lavish", "fashionable", "wonderful", "heavy",
    "expensive", "costly", "cheap", "pricey", "big", "small", "large", "huge", "tiny", "fancy",
    "premium", "luxurious", "new", "old", "complex", "complicated", "simple", "modern",
    "advanced", "good", "better", "best", "bad", "poor", "high", "low", "light",
    "extra", "additional", "other", "another", "same", "different", "special", "major", "minor",
    "various", "certain", "whole", "entire", "such", "own", "free", "full", "real", "fresh",
    "mehnga", "mehngi", "mehnge", "sasta", "sasti", "saste", "bara", "bari", "bare", "chota",
    "chhota", "choti", "chhoti", "naya", "nayi", "naye", "purana", "purani", "purane",
    "mushkil", "khaas", "alag",
    "\u0645\u06c1\u0646\u06af\u0627", "\u0633\u062a\u0627", "\u0628\u0691\u0627",
    "\u0686\u06be\u0648\u0679\u0627", "\u0646\u06cc\u0627", "\u067e\u0631\u0627\u0646\u0627",
    "\u092e\u0939\u0902\u0917\u093e", "\u0938\u0938\u094d\u0924\u093e", "\u092c\u095c\u093e",
    "\u091b\u094b\u091f\u093e", "\u0928\u092f\u093e", "\u092a\u0941\u0930\u093e\u0928\u093e",
    "\u063a\u0627\u0644\u064a", "\u0643\u0628\u064a\u0631", "\u0635\u063a\u064a\u0631",
    "\u062c\u062f\u064a\u062f", "\u0642\u062f\u064a\u0645", "\u0631\u062e\u064a\u0635",
}  # fmt: skip
# nouns that name no particular thing: what a limit about them can say is not matchable
_GENERIC_NOUNS = {
    "enhancements", "adjustments", "modifications", "transformations", "overhauls", "strategies",
    "approaches", "methods", "techniques", "plans", "schemes", "ventures", "endeavours",
    "undertakings", "arrangements", "mechanisms", "frameworks", "capabilities",
    "functionalities", "innovations", "developments", "expansions", "reforms", "tweaks",
    "fixes", "remedies", "commitments", "obligations", "expenditures", "outlays",
    "extravagances", "improvements", "upgrades", "solutions", "experiments", "projects", "ideas",
    "services", "measures", "programs", "initiatives", "features", "enhancement", "upgrade",
    "improvement", "solution", "experiment", "project", "idea", "service", "measure", "program",
    "initiative", "feature",
    "work", "works", "job", "jobs", "money", "funds", "fund", "cost", "costs", "expense",
    "expenses", "spending", "change", "changes", "tool", "tools", "thing", "things", "item",
    "items", "resource", "resources", "time", "effort", "efforts", "way", "ways", "option",
    "options", "luxury", "luxuries", "amount", "amounts", "investment", "investments",
    "purchase", "purchases", "activity", "activities", "task", "tasks", "process", "processes",
    "stuff", "lot", "lots", "alot", "much", "more", "many", "less", "little", "enough",
    "anymore", "extras", "problem", "problems", "issue", "issues", "situation", "matter",
    "kaam", "paisa", "paise", "paisay", "tabdeeli", "kharcha", "kharch", "mushkilat",
    "\u06a9\u0627\u0645", "\u067e\u06cc\u0633\u06d2", "\u0686\u06cc\u0632",
    "\u0686\u06cc\u0632\u06cc\u06ba", "\u062a\u0628\u062f\u06cc\u0644\u06cc",
    "\u0915\u093e\u092e", "\u092a\u0948\u0938\u093e", "\u092a\u0948\u0938\u0947",
    "\u091a\u0940\u091c\u093c", "\u091a\u0940\u091c\u0947\u0902", "\u092c\u0926\u0932\u093e\u0935",
    "\u0639\u0645\u0644", "\u0645\u0627\u0644", "\u0623\u0634\u064a\u0627\u0621",
    "\u062a\u063a\u064a\u064a\u0631",
}  # fmt: skip

# --- The concrete-noun lexicon. A 'cannot ...' object makes a rule only when it holds a word the
# scorer positively knows as a thing an idea can name (or a word from the case's own blocks and
# stated facts). Everything else leaves the limit unreadable. Singular forms; plurals are matched.
_CONCRETE_GROUPS = {
    "people": """staff employee worker helper clerk assistant manager supervisor director executive
        representative agent driver rider cook chef cleaner cashier receptionist accountant guard
        waiter nurse doctor teacher technician electrician plumber carpenter mechanic consultant
        contractor freelancer intern trainee apprentice salesperson salesman tailor painter
        labourer laborer porter courier secretary engineer developer designer programmer
        architect lawyer pharmacist barber farmer vet coach trainer instructor tutor person
        people team crew customer client patient guest tenant student member visitor family
        supplier vendor partner owner landlord neighbour neighbor boss foreman
        hire""",
    "equipment": """equipment machine machinery generator oven fridge freezer mixer grinder printer
        scanner camera tablet computer laptop phone mobile router server screen monitor projector
        scale till terminal pos kiosk mill tractor pump motor engine boiler heater fan cooler
        lamp battery solar panel ladder drill saw hammer shelf shelves rack counter desk chair
        table bed furniture cabinet locker crate bin box bag bottle jar container tank truck van
        car bus bike motorcycle scooter vehicle convertible trolley cart forklift boat trailer
        rickshaw gaari gari gaddi""",
    "premises": """shop store hall room office warehouse hub kitchen factory plant farm field land
        building premises branch outlet stall court pitch ground turf garage yard site space floor
        roof gate parking studio clinic pharmacy restaurant cafe hotel school marquee tent dukan
        kamra""",
    "materials": """paint varnish adhesive glue polish cement brick steel wood timber fabric cloth
        paper plastic glass fuel petrol diesel gas oil grease feed fodder seed fertiliser
        fertilizer pesticide medicine drug vaccine food meal vegetable fruit radish rice flour
        sugar salt milk egg meat chicken fish bread tea coffee water ice flower soap detergent
        explosive chemical stock inventory goods product parcel package packaging uniform clothes
        shoe toy jewellery
        bird cattle ghee tel chai doodh cheeni namak gandum chawal gosht khana""",
    "digital": """software app application website system crm database spreadsheet portal
        dashboard chatbot email sms whatsapp facebook instagram tiktok youtube google ad advert
        advertising flyer poster banner signboard sign brochure catalogue newsletter""",
    "money": """cash card cheque wallet jazzcash easypaisa bank loan credit debt insurance licence
        license permit subscription contract lease rent salary wage bonus fee price discount
        coupon voucher refund deposit advance invoice receipt bill tax""",
    "operations": """menu route schedule shift rota timetable booking reservation appointment order
        delivery queue token ticket diary calendar sheet form checklist list record report policy
        rule name logo brand""",
    "time": """monday tuesday wednesday thursday friday saturday sunday weekend weekday morning
        evening night holiday season summer winter ramadan eid""",
    "outcomes": """downtime mistake error delay waste deadline complaint shortage theft damage
        accident injury fraud breakage sale profit income loss""",
}
_CONCRETE = frozenset(w for group in _CONCRETE_GROUPS.values() for w in group.split())
# things nobody buys: an outcome ('downtime'), a piece of operations ('menu', 'shift') or a time
_OUTCOME_WORDS = frozenset(_CONCRETE_GROUPS["outcomes"].split())
_NONTHING = _OUTCOME_WORDS | frozenset(
    w for g in ("operations", "time") for w in _CONCRETE_GROUPS[g].split()
)
# verbs 'cannot afford X' forbids when X is a thing: every way of getting it
_AFFORD_VERBS = (
    "buy", "purchase", "acquire", "procure", "order", "hire", "recruit", "employ", "appoint",
    "spend", "pay", "invest", "take", "borrow", "lease", "rent", "subscribe", "licence", "license",
    "install", "get",
)  # fmt: skip


def _denied(word: str) -> bool:
    return (
        word in _VAGUE
        or word in _UNIVERSAL
        or word in _ADJECTIVES
        or word in _GENERIC_NOUNS
        or english_plural(word) in _ADJECTIVES
        or english_plural(word) in _GENERIC_NOUNS
    )


def _concrete(word: str, known: frozenset[str] = frozenset()) -> bool:
    """The scorer positively knows this word as a thing an idea can name: it is in the lexicon
    (singular or plural) or it is a word of the case's own blocks and stated facts (`known`),
    unless it is a quantifier, adjective or generic noun. Everything else is not concrete."""
    one = english_plural(word)
    if word in _CONCRETE or one in _CONCRETE:
        return True
    return (word in known or one in known) and not _denied(word)


def _is_in(word: str, words: frozenset[str]) -> bool:
    return word in words or english_plural(word) in words


def _thing(word: str, known: frozenset[str] = frozenset()) -> bool:
    """A concrete word that is something one can buy, hire, lease or subscribe to: in the lexicon
    outside the outcome, operations and time groups, or a case word that is not in the lexicon."""
    return _concrete(word, known) and not _is_in(word, _NONTHING)


def _non_concrete(word: str, known: frozenset[str] = frozenset()) -> bool:
    return not _concrete(word, known)


_NOT_A_VERB = {"be", "have", "do", "go", "get"}
# 'cannot lose X', 'cannot risk X': a stated goal, not a prohibition on ideas that name X
_GOAL_VERBS = {"lose", "miss", "risk", "waste", "delay", "harm", "afford"}
# Every text is collapsed to single spaces first and read only up to these lengths; a longer
# limit or idea is reported as 'unknown' with a flag, never scored. Keeps all parsing linear.
MAX_LIMIT_TEXT = 600
MAX_IDEA_TEXT = 1500
_MAX_AMOUNT_TEXT = 4000  # owner text read for stated figures


def collapse(text: str | None) -> str:
    """Whitespace runs become one space (also removes the blow-up of regexes on long runs)."""
    return " ".join((text or "").split())


class Rule(NamedTuple):
    kind: str  # "neg" (cannot VERB OBJECT), "goal" (cannot lose/afford X) or "tried"
    verbs: frozenset[str]  # full stems of the verb group; empty for "tried"
    alternatives: frozenset[str]  # full stems of verbs that do not break the limit
    objects: frozenset[str]  # full stems of the object's content words
    need: int  # how many object stems an idea must contain
    aliases: frozenset[str] = (
        frozenset()
    )  # things that count as the object ('oven' for 'equipment')
    particle: str = ""  # 'out' in 'cannot rent out X': same verb and particle


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


def _object_words(text: str, last: bool = False) -> list[str]:
    """The words of a limit's object, before any stemming or filler removal."""
    parts = _CUT.split(_TIME.sub(" ", text))
    cut = parts[-1] if last else parts[0]
    return [w for w in re.findall(r"[^\W\d_]+", cut.casefold()) if w not in _OBJECT_SMALL]


def phrasal_pairs(text: str, language: str | None) -> frozenset[tuple[str, str]]:
    """(verb stem, particle) for each 'rent out', 'hire on' ... in an idea text."""
    pieces = re.split(r"[\s-]+", collapse(text)[:MAX_IDEA_TEXT])
    words = [re.sub(r"[^a-z]", "", w.casefold()) for w in pieces]
    return frozenset(
        (stem_ascii(words[i], language, True), words[i + 1])
        for i in range(len(words) - 1)
        if words[i] and words[i + 1] in _PARTICLES
    )


def _last_clause(text: str) -> str:
    return re.split(r"[,;.:!?()]", text)[-1][-160:]


def _parse_rules(
    limit_text: str,
    language: str | None,
    stems_of: StemsOf,
    known: frozenset[str] = frozenset(),
) -> tuple[Rule, ...]:
    """Verb, goal and tried rules read from a limit's own text. `stems_of(text, language)` must
    return FULL stems, so a rule and an idea are always compared in the strict space. A limit
    longer than `MAX_LIMIT_TEXT` after whitespace is collapsed makes no rule (the caller reports it
    as truncated).

    Read: 'cannot|must not|unable to VERB OBJECT' (also with the curly apostrophe), 'cannot afford
    OBJECT' as buy, spend, hire or borrow when OBJECT is something a business buys (equipment,
    software, staff, a loan ...), 'OBJECT cannot be VERBed', 'we do not want to VERB OBJECT',
    Roman Urdu 'OBJECT VERB nahi kar sakte' and 'OBJECT nahi VERB sakte' for the listed Roman Urdu
    verbs only, and a tried-and-failed text. A stated goal ('cannot afford downtime', 'cannot lose
    customers') is a goal rule: an idea breaks it only with a verb such as cause, create, lose or
    risk on that subject, and not when the verb is negated ('avoid losing'). Not handled: a
    prohibition without a modal ('no hiring', 'never open', "won't change"), a verb whose object
    is a figure or a time ('cannot work after 6pm', compared as a number or not at all), and
    Roman Urdu verbs outside the list; a limit with no rule, ceiling or blocks is 'unknown'."""
    text = collapse(limit_text).casefold().replace("\u2019", "'").replace("\u2018", "'")
    rules: list[Rule] = []
    if len(text) > MAX_LIMIT_TEXT:
        return ()
    seen: set[tuple[str, str]] = set()
    groups, alts = _family_stems(language)
    afford = stem_ascii("afford", language, True)
    goal = {stem_ascii(w, language, True) for w in _GOAL_VERBS}
    money_only = {stem_ascii(w, language, True) for w in ("afford", "spend", "pay")}
    give = {stem_ascii(w, language, True) for w in ("give", "offer", "grant")}
    offer_also = {stem_ascii(w, language, True) for w in _OFFER_ALSO}
    actions = {stem_ascii(w, language, True) for w in _GOAL_ACTIONS}
    ru_known = set().union(*groups) if language == "roman_ur" else set()
    hyper = {
        stem_ascii(k, language, True): {stem_ascii(v, language, True) for v in vs}
        for k, vs in _HYPERNYMS.items()
    }

    def add_neg(verb: str, obj: str, last: bool = False, ru: bool = False) -> None:
        if verb in _NOT_A_VERB:
            return
        stem = stem_ascii(verb, language, True)
        if ru and stem not in ru_known:
            return  # a Roman Urdu verb the scorer does not know: the limit stays 'unknown'
        particle = ""
        first = obj.split(" ", 1)
        if not ru and not last and first and first[0] in _PARTICLES:
            particle, obj = first[0], (first[1] if len(first) > 1 else "")
        words = _object_words(obj, last)
        if not any(_concrete(w, known) for w in words):
            # No concrete noun in the object. 'cannot hire anyone' and 'we cannot close' forbid the
            # verb itself and stay rules; 'cannot afford much', 'unable to spend more', 'cannot
            # afford anything expensive', 'cannot take on more work' name nothing an idea could
            # use, so the limit stays unreadable ('unknown').
            plain_verb = stem not in money_only and stem not in goal
            verb_only = plain_verb and (
                not words or (not ru and all(w in _UNIVERSAL for w in words))
            )
            if not verb_only:
                return
        objects = _object_stems(obj, language, stems_of, last)
        if any(any(ch.isdigit() for ch in o) for o in objects):
            return  # a figure in the limit is compared as a number, not as a word
        concrete = [w for w in words if _concrete(w, known)]
        if concrete:  # only the concrete nouns are matched: 'big staff costs' is 'staff'
            objects = frozenset(stems_of(" ".join(concrete), language))
        if stem == afford:
            # 'cannot afford X': a thing is enforced with every way of getting it; an outcome is
            # a goal; anything else is not a rule, so the limit stays unreadable. Never inert.
            things = [w for w in concrete if _thing(w, known)]
            outs = [w for w in concrete if _is_in(w, _OUTCOME_WORDS)]
            if things:
                objects = frozenset(stems_of(" ".join(things), language))
                if not objects:
                    return  # a word too short to match ('ad'): no rule, the limit stays unknown
                aliases = frozenset().union(*(hyper.get(o, set()) for o in objects))
                group = {stem_ascii(w, language, True) for w in _AFFORD_VERBS} | {stem}
                key = ("afford", ",".join(sorted(objects)))
                if key not in seen:
                    seen.add(key)
                    rules.append(
                        Rule("neg", frozenset(group), frozenset(), objects, 1, aliases, particle)
                    )
            elif outs:
                objects = frozenset(stems_of(" ".join(outs), language))
                key = ("goal", ",".join(sorted(objects)))
                if key not in seen:
                    seen.add(key)
                    rules.append(
                        Rule("goal", frozenset(actions), frozenset(), objects, _need(len(objects)))
                    )
            return
        aliases = frozenset().union(*(hyper.get(o, set()) for o in objects))
        if stem in goal:
            if not objects:
                return
            verbs = frozenset(actions | {stem})
            key = ("goal", ",".join(sorted(objects)))
            if key not in seen:
                seen.add(key)
                rules.append(
                    Rule("goal", verbs, frozenset(), objects, _need(len(objects)), aliases)
                )
            return
        group = next((g for g in groups if stem in g), {stem})
        if group & give:
            group = group | offer_also
        alt = frozenset().union(*(alts.get(x, frozenset()) for x in group))
        key = (f"{stem} {particle}".strip(), ",".join(sorted(objects)))
        if key not in seen:
            seen.add(key)
            rules.append(
                Rule("neg", frozenset(group), alt, objects, _need(len(objects)), aliases, particle)
            )

    for m in _NEG.finditer(text):
        add_neg(m.group("verb"), m.group("obj"))
    for marker in _PASSIVE_MARKERS:
        at = text.find(marker)
        while at != -1:
            tail = text[at + len(marker) :].split(" ", 1)[0]
            add_neg(re.sub(r"[^a-z]", "", tail), _last_clause(text[:at]), last=True)
            at = text.find(marker, at + 1)
    if language == "roman_ur":
        pieces = _NEG_RU_SPLIT.split(text)
        for i in range(len(pieces) - 1):
            head = _last_clause(pieces[i]).split()
            sakt = _RU_SAKT.match(pieces[i + 1])
            if not sakt:
                continue
            mid = sakt.group("mid").split()
            if len(mid) == 1 and mid[0] != "kar":  # 'staff nahi rakh sakte': verb after nahi
                add_neg(mid[0], " ".join(head), ru=True)
            elif len(mid) <= 1 and len(head) >= 2:  # 'discount de nahi sakte', '... kar sakte'
                add_neg(head[-1], " ".join(head[:-1]), ru=True)
    fail = _FAIL_ALONE.search(text) or (_TRIED_MARK.search(text) and _FAIL_TRIED.search(text))
    if fail:
        before = text[: fail.start()]
        for marker in ("pehle", "try ", "aazma"):
            at = before.find(marker)
            if at > 0:
                before = before[:at]
        before = _strip_tried_tail(_TRIED_LEAD.sub("", before.strip()))
        objects = _object_stems(before, language, stems_of) - {"tried", "try"}
        if objects:
            rules.append(Rule("tried", frozenset(), frozenset(), objects, _need(len(objects))))
    return tuple(rules)


def rule_hit(
    rule: Rule,
    idea: set[str],
    idea_verbs: set[str] | None = None,
    phrasal: frozenset[tuple[str, str]] = frozenset(),
) -> bool:
    """The idea does what the rule forbids: the verb group (for 'cannot') and enough of the
    object, or an alias of it ('oven' for 'equipment'). A 'cannot VERB' with no object words is
    broken by the verb alone. A goal rule needs a goal-breaking verb that is not itself the
    subject ('waste' in 'reduce waste'). `idea` is the idea's FULL stem set; `idea_verbs` is the
    same without negated verbs and nouns that look like verbs ('a fire alarm')."""
    verbs = idea if idea_verbs is None else idea_verbs
    if rule.particle:  # 'cannot rent out X': only 'rent out' breaks it
        if not any((v, rule.particle) in phrasal for v in rule.verbs):
            return False
    elif rule.kind == "goal":
        if not ((rule.verbs & verbs) - rule.objects):
            return False
    elif rule.kind == "neg" and not (rule.verbs & verbs):
        return False
    return len(rule.objects & idea) >= rule.need or bool(rule.aliases & idea)


def rule_alternative(rule: Rule, idea: set[str]) -> bool:
    """The idea uses a milder verb the limit does not cover ('rent' against 'cannot buy')."""
    return rule.kind == "neg" and bool(rule.alternatives & idea) and not (rule.verbs & idea)


# The scorer reads the same limit and idea text several times per candidate; the readers are
# pure, so their results are kept (and handed out as fresh lists).
_amounts_cached = lru_cache(maxsize=2048)(_amounts)
_ceilings_cached = lru_cache(maxsize=1024)(_ceilings_of)
_rules_cached = lru_cache(maxsize=1024)(_parse_rules)


def amounts(text: str, context: bool = False) -> list[Amount]:
    return list(_amounts_cached(text, context))


def ceilings_of(limit_text: str, kind: str = "") -> list[Ceiling]:
    return list(_ceilings_cached(limit_text, kind))


def parse_rules(
    limit_text: str,
    language: str | None,
    stems_of: StemsOf,
    known: frozenset[str] = frozenset(),
) -> list[Rule]:
    return list(_rules_cached(limit_text, language, stems_of, known))


amounts.__doc__ = _amounts.__doc__
ceilings_of.__doc__ = _ceilings_of.__doc__
parse_rules.__doc__ = _parse_rules.__doc__
