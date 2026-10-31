"""L2-3: text folding and the patterns the blueprint rules scan with. Pure, no database.

The shared regexes (`constitution.PROMISE`, `brain_docs.MONEY_IN_TEXT`) are kept and still run, but
they miss ordinary spellings: letters spaced out, zero-width characters, look-alike letters, digits
in another script, a currency glued to its figure, numbers written as words. This module folds the
text first and adds patterns in English, Roman Urdu, Urdu, Hindi and Arabic. It only ever widens
what is caught; a text the old patterns catch is still caught.

`views(text)` gives the text as written, folded, and folded with spaced-out letters or digits
joined. A pattern matches if it matches any view.
"""

from __future__ import annotations

import math
import re
import unicodedata

# Copies of `brain_docs.MONEY_IN_TEXT` (brain_docs.py:60) and `brain_docs.WILL` (brain_docs.py:69),
# kept here because importing brain_docs pulls the database layer into a pure module and would
# make a cycle once brain_docs calls the blueprint rules. A unit test asserts they are identical.
MONEY_IN_TEXT = re.compile(
    r"\b(?:rs\.?|pkr|aed|cad|usd|dirhams?|rupees?|lakhs?|crores?)\b|[$€£₹]"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:k|m|lakh|lac|crore|million|thousand)\b"
    r"|\b(?:cost|costs|price|priced|fee|fees|charge|charged|budget|pay|paying)\b\D{0,15}\d{3,}",
    re.IGNORECASE,
)
WILL = re.compile(r"\bwill\b(?! not)", re.IGNORECASE)

# An option field is a sentence or two. A longer text is refused by the rules (MALFORMED), and the
# patterns only ever run on the first MAX_TEXT characters, so no input can make them slow.
MAX_TEXT = 1000

# --- folding -------------------------------------------------------------------------------------

_INVISIBLE = dict.fromkeys(
    map(
        ord,
        "​‌‍‎‏‪‫‬‭‮⁠⁡⁢⁣⁦⁧⁨⁩؜﻿­᠎͏",
    )
)
# look-alike letters (Cyrillic, Greek) to Latin, and the Arabic-script letter variants to one form
_LOOKALIKE = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
        "ѕ": "s", "һ": "h", "ԁ": "d", "ɡ": "g", "к": "k", "м": "m", "т": "t", "ӏ": "l",
        "α": "a", "ε": "e", "ο": "o", "ρ": "p", "ι": "i", "κ": "k", "ν": "v", "τ": "t", "υ": "u",
        "ي": "ي", "ى": "ي", "ی": "ي", "ې": "ي", "ے": "ي", "ك": "ك", "ک": "ك", "ہ": "ه", "ھ": "ه",
        "ة": "ه", "ۃ": "ه", "ٱ": "ا", "ँ": "ं",
    }
)  # fmt: skip
# combining marks: Latin accents, Arabic points, the Devanagari nukta
_MARKS = re.compile("[̀-ًͯ-ٰٟـۖ-़ۭ]")
_SPACED_LETTERS = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][ \-_.*]){3,}[^\W\d_](?![^\W\d_])")
_SPACED_DIGITS = re.compile(r"(?<!\d)\d(?: \d){3,}(?!\d)")
_SEPARATOR = re.compile(r"[ \-_.*]")


def _ascii_digits(text: str) -> str:
    """Arabic-Indic, Devanagari and full-width digits become ASCII digits."""
    return "".join(
        str(unicodedata.decimal(ch)) if ch.isdecimal() and not ch.isascii() else ch for ch in text
    )


def fold(text: str) -> str:
    """The text as plain lower-case: compatibility forms, invisible and bidi marks, accents and
    Arabic points, other-script digits and look-alike letters all folded away."""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.translate(_INVISIBLE)
    s = _ascii_digits(s)
    s = s.casefold().translate(_LOOKALIKE)
    s = _MARKS.sub("", s)
    return " ".join(s.split())


def views(text: str) -> tuple[str, ...]:
    """The text as written, folded, and folded with spaced-out letters and digits joined."""
    raw = str(text)[:MAX_TEXT]
    folded = fold(raw)
    joined = _SPACED_LETTERS.sub(lambda m: _SEPARATOR.sub("", m.group(0)), folded)
    joined = _SPACED_DIGITS.sub(lambda m: m.group(0).replace(" ", ""), joined)
    seen: list[str] = []
    for view in (raw, folded, joined):
        if view not in seen:
            seen.append(view)
    return tuple(seen)


def _alt(words: str) -> str:
    """An alternation of folded words, longest first."""
    items = sorted({fold(w) for w in words.split()}, key=len, reverse=True)
    return "|".join(re.escape(w) for w in items)


def _word(body: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![^\W\d_])(?:{body})(?![^\W\d_])")


# --- promises ------------------------------------------------------------------------------------

_PROMISE_WORDS = (
    # English
    "guarantee guarantees guaranteed guaranteeing guaranty assure assures assured assurance "
    "certainly definitely surely unfailing foolproof infallible"
    # Roman Urdu / Hindi in Latin letters
    " zaroor zarur zaror pakka pakki pukka yaqeen yaqeeni yakeen yakini yaqini zamanat "
    # Hindi
    "गारंटी गारण्टी पक्का पक्की ज़रूर जरूर यकीनन निश्चित निश्चय"
)
_PROMISE_ARABIC = (
    "ضمان ضمانت ضمانة مضمون مضمونة یقینی یقین ضرور پکا پکی حتما حتماً "
    "بالتاکید بالتأكيد مؤكد مؤكدة اكيد أكيد"
)
_PROMISE_PHRASES = (
    r"(?:is|are|be|been|it's|its|that's)\s+certain",
    r"certain\s+(?:to|that|of)",
    r"for\s+sure",
    r"sure\s+to\b",
    r"no\s+doubt",
    r"without\s+(?:any\s+)?fail",
    r"(?:works?|work)\s+every\s+(?:single\s+)?time",
    r"every\s+single\s+time",
    r"always\s+work",
    r"100\s?(?:%|percent|per\s?cent)",
    r"no\s+risk",
    r"risk\s?-?\s?free",
    r"bina\s+kisi\s+risk",
    r"koi\s+risk\s+nahi",
    r"zaroor\s+\w+",
    r"pakka\s+\w+",
    r"بلا\s+شبه",
    r"بغیر\s+کسی\s+خطر",
    r"من\s+دون\s+مخاطر",
    r"بدون\s+مخاطر",
    r"जोखिम\s+नहीं",
)
_ARABIC_PREFIX = "|".join(
    fold(p) for p in ("وال", "بال", "فال", "كال", "لل", "ال", "و", "ب", "ف", "ك", "ل")
)
PROMISE_EXTRA = re.compile(
    "|".join(
        [
            rf"(?<![^\W\d_])(?:{_alt(_PROMISE_WORDS)})(?![^\W\d_])",
            rf"(?<![؀-ۿ])(?:{_ARABIC_PREFIX})?(?:{_alt(_PROMISE_ARABIC)})(?![؀-ۿ])",
        ]
        + [rf"(?<![^\W\d_]){fold(p)}(?![^\W\d_])" for p in _PROMISE_PHRASES]
    )
)


def promise_in(text: str, *patterns: re.Pattern[str]) -> bool:
    """True when any view of the text matches the extra patterns or any of `patterns`."""
    return any(rx.search(v) for v in views(text) for rx in (PROMISE_EXTRA, *patterns))


# --- money ---------------------------------------------------------------------------------------

_CURRENCY_CODES = "rs pkr aed cad usd eur gbp inr sar"
_CURRENCY_WORDS = (
    "rs pkr aed cad usd eur gbp inr sar dollar dollars euro euros buck bucks pound pounds "
    "rupee rupees rupay rupaye rupiya rupye rupiye dirham dirhams riyal riyals "
    "روپے روپیہ روپیے روپے ریال درهم دراهم دولار يورو جنيه "
    "रुपये रुपया रुपए रुपैया"
)
_SYMBOLS = "[$€£₹¥₨]"
_MAGNITUDES = (
    "thousand thousands lakh lakhs lac lacs crore crores karor million millions billion "
    "hazar hazaar hajar hajaar "
    "لاکھ ہزار کروڑ ملین الف ألف مليون مليار "
    "लाख हज़ार हजार करोड़ करोड मिलियन"
)
_NUMBER_WORDS = (
    # English
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred "
    # Roman Urdu
    "ek aik do teen char chaar paanch panch paanchh chhe chay saat aath nau das gyarah barah "
    "pandrah bees pachis tees chalis pachas pachaas saath sattar assi nabbe sau "
    # Urdu
    "ایک دو تین چار پانچ چھ سات آٹھ نو دس بیس تیس چالیس پچاس ساٹھ ستر اسی نوے سو "
    # Hindi
    "एक दो तीन चार पाँच पांच छह सात आठ नौ दस बीस तीस चालीस पचास साठ सत्तर अस्सी नब्बे सौ "
    # Arabic
    "واحد اثنان اثنين ثلاثة ثلاث اربعة اربع خمسة خمس ستة ست سبعة سبع ثمانية ثماني تسعة تسع "
    "عشرة عشر عشرين ثلاثين اربعين خمسين ستين سبعين ثمانين تسعين مئة مائة ميه نصف "
    # fractions and articles that start a magnitude
    "half a an"
)
_N = _alt(_NUMBER_WORDS)
_MAG = _alt(_MAGNITUDES)
_CUR = _alt(_CURRENCY_WORDS)
_CODES = _alt(_CURRENCY_CODES)
_PRICE_WORDS = (
    "fee fees cost costs price prices priced pricing charge charges charged budget pay paying rate "
    "rates kharcha kharch qeemat keemat قیمت رقم لاگت خرچ خرچہ कीमत दाम سعر تكلفة ثمن"
)

MONEY_EXTRA = re.compile(
    # a currency code glued to or before a figure: "PKR50000", "Rs500", "usd 20"
    rf"(?<![^\W\d_])(?:{_CODES})\.?\s*\d"
    # a figure before a currency word: "500 dollars", "50000 rupay", "300 eur"
    rf"|(?<!\d)\d[\d.,]*\s*(?:{_CUR})(?![^\W\d_])"
    # a currency word before a figure
    rf"|(?<![^\W\d_])(?:{_CUR})\.?\s*\d"
    # symbols
    rf"|{_SYMBOLS}"
    # a figure with a magnitude: "5L", "5 lakh", "1.5m", "5 cr", "3 hazar"
    rf"|(?<![^\W\d_])(?<!\d)\d+(?:\.\d+)?\s?(?:k|l|m|cr|{_MAG})(?![^\W\d_])"
    # number words with a magnitude: "five hundred thousand", "fifty-thousand", "half a million",
    # "paanch hazaar", "پانچ لاکھ", "पाँच लाख"
    rf"|(?<![^\W\d_])(?:{_N})(?:[\s-]+(?:{_N}|and)){{0,4}}[\s-]+(?:{_MAG})(?![^\W\d_])"
    # a number word with a currency word: "paanch sau rupay"
    rf"|(?<![^\W\d_])(?:{_N})[\s-]+(?:{_CUR})(?![^\W\d_])"
    # grouped figures: 5,00,000 and 50 000
    r"|(?<![\d,.])\d{1,3}(?:,\d{2,3})+(?![\d])|(?<![\d,.])\d{1,3}(?: \d{3})+(?![\d])"
    # a figure of three or more digits near a price word
    rf"|(?<![^\W\d_])(?:{_alt(_PRICE_WORDS)})\w*\D{{0,15}}\d{{3,}}"
)
_DIGIT_RUN = re.compile(r"(?<![\d.,+])(\d+)(?![\d]*[%.,]\d)")


def _bare_figure(view: str) -> bool:
    """A bare run of five to nine digits ("50000") is a figure, not a count of people or a year.
    Ten or more digits, a "+" or a leading zero on nine or more digits is a phone number, and a
    figure followed by "%" is a percentage."""
    for m in _DIGIT_RUN.finditer(view):
        run, end = m.group(1), m.end(1)
        if not 5 <= len(run) <= 9:
            continue
        if run.startswith("0") and len(run) >= 9:
            continue
        if view[end : end + 1] == "%":
            continue
        return True
    return False


def money_in(text: str) -> bool:
    """True when any view of the text holds an amount: the old pattern, the extra patterns, or a
    bare figure of five to nine digits."""
    return any(
        MONEY_IN_TEXT.search(v) or MONEY_EXTRA.search(v) or _bare_figure(v) for v in views(text)
    )


# --- a guessed cause worded as a fact -------------------------------------------------------------

_STOP = frozenset(
    (
        "a an the is are was were be been do does did not no nor of at to in on and or for it its "
        "they we you i he she our your their this that these those with by from as so than then "
        "there here have has had will would can could may might should shall into over under about "
        "because since while when where which who whom what why how all any each every some such "
        "only own same too very just also still yet"
    ).split()
)
_HEDGE_WORDS = (
    "if may might could possibly perhaps maybe assuming suppose supposing seems apparently "
    "probably likely shayad agar mumkin شاید اگر ممکن لعل ربما إذا اذا यदि अगर शायद"
)
_HEDGE_PHRASES = ("ho sakta", "ho sakti", "हो सकता", "हो सकती")
_HEDGES = re.compile(
    "|".join(
        [rf"(?<![^\W\d_])(?:{_alt(_HEDGE_WORDS)})(?![^\W\d_])"]
        + [rf"(?<![^\W\d_]){fold(p)}(?![^\W\d_])" for p in _HEDGE_PHRASES]
    )
)
_SENTENCE = re.compile(r"[.!?؟۔\n;]+")
_CLAUSE = re.compile(
    r"[,،:()\[\]–—]|(?<![^\W\d_])(?:and|but|so|because|aur|lekin|phir|toh)(?![^\W\d_])"
)
_CONTRACTION = re.compile(r"(?<![^\W\d_])([^\W\d_]+)n['’]t(?![^\W\d_])")
_STEM = 5


def content_stems(text: str) -> set[str]:
    """The content words of a text, cut to a short stem so "counting" and "count" meet."""
    s = _CONTRACTION.sub(r"\1 not", fold(text))
    s = s.replace("'", "").replace("’", "")
    words = re.findall(r"[^\W\d_]+", s)
    return {w[:_STEM] for w in words if len(w) >= 3 and w not in _STOP}


def states_as_fact(cause: str, text: str) -> bool:
    """True when `text` words the guessed `cause` as a fact: a sentence that holds most of the
    cause's content words (or the cause itself when it has fewer than two) with no hedge word in
    the same clause as those words. A hedge in another sentence or clause does not count."""
    stems = content_stems(cause)
    if not stems:
        return False
    need = max(2, math.ceil(0.6 * len(stems))) if len(stems) >= 2 else 1
    whole = fold(cause)
    for sentence in _SENTENCE.split(text):
        if len(stems) < 2:
            found = whole in fold(sentence)
        else:
            found = len(content_stems(sentence) & stems) >= need
        if not found:
            continue
        hedged = any(
            _HEDGES.search(fold(clause)) and content_stems(clause) & stems
            for clause in _CLAUSE.split(sentence)
        )
        if not hedged:
            return True
    return False
