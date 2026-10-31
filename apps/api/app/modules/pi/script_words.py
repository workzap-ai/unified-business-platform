"""Words in every script pi meets: English, Roman Urdu, Urdu and Arabic script, Devanagari (Hindi).

Python's regex word class does not match combining marks, so a Devanagari word such as "दुकान"
splits at every vowel sign and an Arabic word with harakat splits at every mark. `WORD` keeps the
marks inside the word, and `fold` gives one shape for the letters people write several ways
(Arabic and Urdu forms of yeh, kaf, heh; Devanagari nukta and candrabindu), so two spellings of
one word meet.

Pure helpers, no state. The Arabic and Urdu fold table mirrors `industry_packs._SCRIPT_FOLD`
(copied, not imported, because that one is private).
Written by one author, not reviewed by a native speaker of Hindi, Urdu or Arabic.
"""

import re
import unicodedata

# Letters and digits (\w) plus the combining marks \w leaves out: Devanagari signs (U+0900-0963,
# U+0970-097F: not the danda, which is a full stop), Arabic harakat and Quranic marks, ZWNJ/ZWJ.
_MARK_CLASS = (
    "ऀ-ॣ॰-ॿ"  # Devanagari signs and letters, not the danda
    "ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ"  # Arabic marks
    "‌‍"
)
WORD = re.compile(rf"[\w{_MARK_CLASS}]+", re.UNICODE)

_ARABIC_MARKS = re.compile("[ً-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")
_DEVANAGARI_NOISE = re.compile("[़‌‍]")  # nukta, ZWNJ, ZWJ
_FOLD = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ۃ": "ه", "ى": "ي", "ی": "ي",
        "ے": "ي", "ې": "ي", "ہ": "ه", "ھ": "ه", "ک": "ك", "ں": "ن", "ؤ": "و", "ئ": "ي",
        "ँ": "ं",
    }
)  # fmt: skip
_ARABIC_LETTER = re.compile("[؀-ۿ]")
_DEVANAGARI_LETTER = re.compile("[ऀ-ॿ]")
_ARABIC_PREFIXES = ("وال", "بال", "فال", "كال", "لل", "ال")
_HINDI_ENDINGS = ("ियाँ", "ियां", "ाएँ", "ाएं", "ों", "ें")


def fold(text: str) -> str:
    """Lower-case, one shape for the letters written several ways, marks and tatweel dropped."""
    text = unicodedata.normalize("NFKC", text or "").casefold().replace("’", "'")
    text = _ARABIC_MARKS.sub("", _DEVANAGARI_NOISE.sub("", text))
    return text.translate(_FOLD)


def is_latin(word: str) -> bool:
    return not (_ARABIC_LETTER.search(word) or _DEVANAGARI_LETTER.search(word))


def arabic_stem(word: str) -> str:
    """Drop the Arabic article and a joining "و" ("والطلبات" gives "طلبات")."""
    if not _ARABIC_LETTER.search(word):
        return word
    for prefix in _ARABIC_PREFIXES:
        if word.startswith(prefix) and len(word) - len(prefix) >= 3:
            return word[len(prefix) :]
    return word[1:] if word.startswith("و") and len(word) >= 5 else word


def hindi_stem(word: str) -> str:
    """Drop a plural or oblique ending ("दुकानें", "दुकानों" give "दुकान")."""
    if not _DEVANAGARI_LETTER.search(word):
        return word
    for ending in _HINDI_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[: -len(ending)]
    return word


def english_stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def stem(word: str) -> str:
    """The folded word cut to its stem, whatever its script (a Latin word gets the English cut)."""
    return english_stem(hindi_stem(arabic_stem(word)))


def tokens(text: str) -> list[str]:
    """The words of a text, folded and stemmed, marks kept inside each word."""
    return [stem(fold(m.group(0)).replace("'", "")) for m in WORD.finditer(text or "")]


MARKS = _MARK_CLASS  # for patterns that build their own word class
