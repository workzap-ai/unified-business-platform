"""A number the owner corrects ("not 10, 100", "10 nahi, 100", "no wait, it is 15 kg").

Platform spec B7.1/B7.3: a correction is kept, not lost. The saved problem must show the corrected
figure, the old figure stays in the revision history, and the reply must use the new figure.

Pure functions. `numeric_correction` finds (wrong, right) from the latest message and the owner's
earlier ones; it is deliberately strict (an explicit "not X, Y" pair, or a correction cue plus
an old number followed by the same word as the new one),
so an unrelated number is never swapped.

Languages (L1-7a): English, Roman Urdu, Urdu script, Hindi (Devanagari) and Arabic. Figures may be
written in Western, Arabic-Indic, Persian or Devanagari digits (mixed in one message too), with
lakh, crore, hazar, thousand, million or k after them in Latin, Devanagari, Urdu or Arabic script
("5 lakh" is 500000). Written by one author, not reviewed by a native speaker of Hindi, Urdu or
Arabic: tests/unit/test_pi_l1_cues_hindi_arabic.py measures recall and precision with its n.
"""

import re
from decimal import Decimal

from app.modules.pi.script_words import WORD, arabic_stem, fold

_DIGITS = str.maketrans(
    {
        **{ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")},  # Arabic-Indic
        **{ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")},  # Persian and Urdu
        **{ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")},  # Devanagari
        ord("٫"): ".",  # Arabic decimal separator
        ord("٬"): ",",  # Arabic thousands separator
    }
)
NUM = r"(\d[\d,]*(?:\.\d+)?)(?!\d)"
_NUMBER = re.compile(NUM)
NO = r"(?:nahi|nahin|nhi|nai|نہیں|نہی|नहीं|नही|नहि)"
# Arabic "not": لا, ليس, مش, مو (and with the joining و)
AR_NO = r"(?<!\w)(?:و?ليس|و?لا|مش|مو)(?!\w)"
# What may sit between the wrong and the right figure: "it was", "but", "बल्कि", "بلکہ", "بل".
_LINK = (
    r"(?:(?:it\s+(?:was|is)|its|it's|but|woh|wo|ye|yeh|balki|balkay|"
    r"बल्कि|वो|वह|ये|यह|दरअसल|असल\s+में|बजाय|بلکہ|وہ|یہ|اصل\s+میں|دراصل)\s+)?"
)
_AR_LINK = r"(?:(?:بل|لكن|ولكن|إنما|وإنما|بالعكس|هو|هي|كان|كانت|الصحيح|الرقم|في\s+الحقيقة)\s+)?"
_SEP = r"\s*[,;:.،؛-]?\s*"
CUE = re.compile(
    r"\b(?:not|no|sorry|correction|actually|wait|wrong|instead|rather|nahi|nahin|nhi|galat|ghalat|"
    r"darasal|asal|matlab|balki)\b"
    r"|نہیں|غلط|دراصل|اصل\s+میں|معاف|بلکہ|مطلب"
    r"|नहीं|नही|गलत|दरअसल|असल\s+में|माफ|सॉरी|मतलब|बल्कि|रुकिए|ठहरिए"
    r"|(?<!\w)(?:لا|ليس|مش|بل|خطأ|خطا|تصحيح|اقصد|أقصد|آسف|عفوا|الصحيح|في\s+الحقيقة)(?!\w)",
    re.IGNORECASE,
)
# A figure with a scale word after it: "5 lakh", "10 हज़ार", "2 کروڑ", "3 ملايين", "10k".
_SCALE = (
    r"(?:\s*(?:lakhs?|lacs?|crores?|karors?|haz+aar|hazar|hajar|thousand|million|"
    r"लाख|करोड|हजार|لاکھ|کروڑ|ہزار|ألف|الف|آلاف|ألاف|مليون|ملايين|ملیون|ملین)|k)"
)
_SCALE_END = r"(?![\wऀ-ॿً-ٟ])"
_FIGURE = re.compile(NUM + rf"(?:({_SCALE}){_SCALE_END})?", re.IGNORECASE)
_MULTIPLIER = (
    (("lakh", "lac", "لاکھ", "लाख"), Decimal(100000)),
    (("crore", "karor", "کروڑ", "करोड"), Decimal(10000000)),
    (("million", "مليون", "ملايين", "ملیون", "ملین"), Decimal(1000000)),
)
# "not 10, 100" / "not 10, it was 100" / "not 10 but 100"
NOT_THEN = re.compile(rf"\bnot\s+{NUM}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# "nahi 10 balki 100" / "नहीं 10 बल्कि 100" / "نہیں 10 بلکہ 100" (a leading "no")
NO_NUM_THEN = re.compile(rf"{NO}\s+{NUM}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# Arabic: "لا 10 بل 100" / "ليس 10 بل 100" / "مش 10، 100"
AR_NOT_THEN = re.compile(rf"{AR_NO}\s+{NUM}{_SEP}{_AR_LINK}{NUM}")
# "100, not 10"
THEN_NOT = re.compile(rf"{NUM}\s*[,;:.،؛-]?\s*not\s+{NUM}", re.IGNORECASE)
# Arabic: "100 وليس 10" / "100، لا 10"
AR_THEN_NOT = re.compile(rf"{NUM}{_SEP}{AR_NO}\s+{NUM}")
# "10 nahi, 100" / "nahi 20 nahi, 12" / "20 nahi 12 hain" / "10 नहीं, 100"
NUM_NAHI = re.compile(rf"{NUM}\s*{NO}{_SEP}{_LINK}{NUM}", re.IGNORECASE)
# "100 hai, 10 nahi" / "100 है, 10 नहीं" / "100 ہے، 10 نہیں" (the right figure first)
THEN_NAHI = re.compile(
    rf"{NUM}\s*(?:hai|hain|है|हैं|ہے|ہیں)?\s*[,;:.،؛-]?\s*{NUM}\s*{NO}", re.IGNORECASE
)
STOP = frozenset("the and was are for with that this have has had not but its our their".split())


def _plain(value: Decimal) -> str:
    return str(int(value)) if value == value.to_integral() else format(value.normalize(), "f")


def _value(match: re.Match[str]) -> Decimal:
    """The figure of a match with its scale word applied ("5 lakh" is 500000)."""
    base = Decimal(match.group(1).replace(",", ""))
    scale = (match.group(2) or "").strip().casefold()
    if not scale:
        return base
    for names, multiplier in _MULTIPLIER:
        if any(scale.startswith(n) for n in names):
            return base * multiplier
    return base * 1000  # hazar, thousand, k, ألف


def expand(text: str) -> str:
    """The text with Eastern digits as 0-9, nukta dropped, and every scaled figure written out
    ("5 lakh" gives "500000"). Matching runs on this, so one rule covers every script."""
    text = (text or "").translate(_DIGITS).replace("़", "")
    return _FIGURE.sub(lambda m: _plain(_value(m)) if m.group(2) else m.group(0), text)


def norm(token: str) -> str:
    """A number as a comparable string: commas out, Eastern digits turned into 0-9, no zero tail."""
    whole, _, frac = token.translate(_DIGITS).replace(",", "").partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> list[str]:
    return [norm(m) for m in _NUMBER.findall(expand(text))]


def _following_word(text: str, number: str) -> str:
    """The first word after the number ("10 clients" gives "client"): the same fact?"""
    plain = expand(text)
    for m in _NUMBER.finditer(plain):
        if norm(m.group(1)) == number:
            tail = [fold(w) for w in WORD.findall(plain[m.end() :]) if not w[0].isdigit()]
            tail = [arabic_stem(w) for w in tail if w not in STOP]
            return tail[0][:5] if tail else ""
    return ""


def numeric_correction(latest: str, earlier: list[str]) -> tuple[str, str] | None:
    """(wrong, right) when the latest message corrects a number, else None."""
    text = " ".join(expand(latest).split())
    if not text:
        return None
    for pattern, order in (
        (NOT_THEN, (0, 1)),
        (NUM_NAHI, (0, 1)),
        (NO_NUM_THEN, (0, 1)),
        (AR_NOT_THEN, (0, 1)),
        (THEN_NOT, (1, 0)),
        (THEN_NAHI, (1, 0)),
        (AR_THEN_NOT, (1, 0)),
    ):
        m = pattern.search(text)
        if m:
            wrong, right = norm(m.group(order[0] + 1)), norm(m.group(order[1] + 1))
            if wrong != right:
                return wrong, right
    if not CUE.search(text):
        return None
    mine = numbers_in(text)
    named = re.search(rf"\bnot\s+{NUM}", text, re.IGNORECASE)  # "5,000 subscribers, not 500"
    if named and len(set(mine)) == 2:
        wrong = norm(named.group(1))
        others = [n for n in dict.fromkeys(mine) if n != wrong]
        if len(others) == 1:
            return wrong, others[0]
    if len(set(mine)) != 1:
        return None
    right = mine[0]
    for old in reversed([e for e in earlier if e and e != latest]):
        olds = [n for n in dict.fromkeys(numbers_in(old)) if n != right]
        if not olds:
            continue
        word = _following_word(text, right)
        same = [n for n in olds if word and _following_word(old, n) == word]
        if len(same) == 1:
            return same[0], right
        return None  # the nearest earlier message with numbers does not match: do not guess
    return None


def standalone(number: str) -> re.Pattern[str]:
    """The number as its own figure: 10 matches "10 clients" but not "100", "10.5" or "5,10"."""
    plain = number.replace(".", r"\.")
    return re.compile(rf"(?<![\d.,]){plain}(?![\d]|[.,]\d)")


def has_figure(text: str, number: str) -> bool:
    return any(norm(n) == number for n in numbers_in(text))


def replace_figure(text: str, wrong: str, right: str) -> str:
    """The text with every standalone `wrong` figure (any comma style, any scale word) written as
    `right`."""
    out, last = [], 0
    source = text or ""
    for m in _FIGURE.finditer(source.translate(_DIGITS)):  # translate keeps the length
        if norm(_plain(_value(m))) == wrong:
            out.append(source[last : m.start()])
            out.append(right)
            last = m.end()
    out.append(source[last:])
    return "".join(out)


_ACK = re.compile(
    r"(?:\bnot\b|\binstead of\b|\brather than\b|\bnahi\b|\bnahin\b|\bnhi\b|\bnot\s+the\b|"
    r"के\s+बजाय|की\s+जगह|نہیں|کی\s+جگہ|ليس|بدل[اً]*\s+من|ولا|وليس)"
    r"[^.?!\n]{0,12}$",
    re.IGNORECASE,
)
_ACK_AFTER = re.compile(r"\s*(?:nahi|nahin|nhi|नहीं|नही|نہیں|نہی)(?!\w)", re.IGNORECASE)


def reply_problem(reply: str, wrong: str, right: str) -> str | None:
    """Why a reply to a correction cannot go: it does not use the new figure, or it still gives the
    old one as a fact ("not 10" or "instead of 10" is an acknowledgement, not a fact)."""
    if not has_figure(reply, right):
        return (
            f"the owner just corrected a figure to {right} (not {wrong}): the reply must use "
            f"{right}"
        )
    plain = expand(reply)
    for m in _NUMBER.finditer(plain):
        if norm(m.group(1)) != wrong:
            continue
        before = plain[max(0, m.start() - 14) : m.start()]
        after = plain[m.end() : m.end() + 8]
        if _ACK.search(before) or _ACK_AFTER.match(after):
            continue
        return (
            f"the owner corrected {wrong} to {right}, but the reply still gives {wrong} as a "
            f"fact: use {right} only"
        )
    return None


def superseded(old_word: str, new_texts: list[str], correction: bool) -> bool:
    """An earlier user_word that the correction replaces: it carries a figure that the new wording
    contradicts (a different figure about the same thing), so the record does not keep it as the
    current fact. It stays in the revision history, which holds the old list in full."""
    if not correction:
        return False
    old = set(numbers_in(old_word))
    new = {n for t in new_texts for n in numbers_in(t)}
    if not old or not new or old & new:
        return False
    stems = {w.casefold()[:5] for w in WORD.findall(old_word) if len(w) >= 4} - STOP
    fresh = {w.casefold()[:5] for t in new_texts for w in WORD.findall(t) if len(w) >= 4}
    return bool(stems & fresh)
