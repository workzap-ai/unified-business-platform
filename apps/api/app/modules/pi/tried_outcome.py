"""How an earlier attempt went, read from the owner's own words (L1 follow-up, live path).

Pure functions. `failed_attempt` finds a failed attempt in a text: a failure cue (negation + effect,
benefit or work word, in English, Roman Urdu, Urdu, Arabic and Hindi), or a weaker cue ("got mixed
up", "came out wrong", "was useless") that counts only beside an attempt word that comes BEFORE it.
It returns what was tried, in the owner's own wording, so the stored `tried` entry can be matched
against a new idea (PS-3 `idea_relevance` reads `tried[].what`). `outcome_of` says "failed",
"worked" or "unclear".

What never counts as the owner's attempt (`owner_clauses` drops it): a question, a hypothetical or
conditional ("if I tried", "agar main try karun", "do you think"), and a third party's attempt (a
competitor, a brother, "neighbour ne aazmaya", "woh log") when the owner does not say they did it
too. A negated failure ("has not failed", "nakam nahi hue") is not a failure, and "did not help" /
"it never worked" are.

Only the owner's text is ever read here; a model's wording proves nothing (the caller passes the
owner's messages). Best effort: object words in Urdu, Arabic and Hindi are cut at the cue and at
attempt words, nothing more.
"""

import re
from typing import NamedTuple

# An attempt word: tried / before / experiment, in the five languages. Not "used" or "started":
# those are not an attempt that failed, and a third party uses things too.
ATTEMPT = re.compile(
    r"\b(?:tried|try|trying|aazma\w*|pehle|kiya tha|rakha tha|already did)\b"
    r"|آزما|کوشش|پہلے|جرب|حاول|سابق|आज़मा|आजमा|कोशिश|पहले"
)

# Strong: a failed outcome on its own, like "did not work".
FAIL_STRONG = re.compile(
    r"\b(?:did not work|didn't work|didnt work|does not work|doesn't work|not worked|"
    r"never worked|made no difference|did nothing|did not help|didn't help|didnt help|"
    r"not helped|never helped|has not helped|hasn't helped|no help|nothing helped)\b"
    r"|\b(?:kaam|faida|fayda|faeda|asar|nateeja|natija)\s+(?:nahi|nahin|nhi)"
    r"(?:\s+(?:aaya|aya|hua|kiya|diya|kia|raha))?\b"
    r"|\bnakam\b|\bbe-?asar\b"
    r"|ناکام|(?:فائدہ|فایدہ|اثر|نتیجہ)\s+(?:نہیں|نھیں)|کام\s+نہیں\s+(?:آیا|کیا)"
    r"|لم\s+[يت](?:نجح|فد|نفع)|ما\s+(?:نفع|نجح|أفاد|افاد)|و?فشل|دون\s+جدوى|بدون\s+فائدة"
    r"|काम\s+नहीं\s+आया|(?:फायदा|फ़ायदा|असर|नतीजा)\s+नहीं|असफल|नाकाम"
    r"|\b(?:stopped working|then (?:it )?(?:stopped|failed|died|dropped|faded)|wore off|fizzled"
    r"|petered out|worked (?:only )?(?:at first|initially|for a (?:week|while|few days|bit)))\b"
    r"|\bphir band\b|\bbaad mein (?:kaam )?nahi\b|\bkuch din (?:chala|kaam kiya) phir\b"
)
# 'failed', 'useless' and the like count only beside an attempt word that comes before them, and
# never as "failed to ..." (something that did not happen, not an outcome).
FAIL_BESIDE_ATTEMPT = re.compile(
    r"\b(?:failed(?! to\b)|useless|flopped|no use|no result|kaam nahi)\b"
    r"|\bmix\s+ho\s+gay[ei]\b|\bghalat\s+nikl(?:a|i|e)\b"
    r"|\bbekaar\s+(?:raha|rahi|nikla|nikli|gaya)\b"
    r"|بیکار\s+(?:رہا|رہی|نکلا|نکلی)|غلط\s+نکل|گڈ\s+مڈ\s+ہو|اختلط"
    r"|बेकार\s+(?:रहा|निकला)|गलत\s+निकला|मिक्स\s+हो\s+गए"
)
WORKED = re.compile(
    r"\b(?:it worked|worked well|that worked|helped|kaam aaya|faida hua|fayda hua|asar hua)\b"
    r"|فائدہ\s+ہوا|بہت\s+فائدہ|نفع|نجح|काम\s+आया|फायदा\s+हुआ"
)

# A cue that carries its own negation ("did not work", "kaam nahi aaya") is not checked again.
_OWN_NEGATION = re.compile(
    r"\bnot\b|n't\b|\bnever\b|\bno\b|\bnahi\b|\bnahin\b|\bnhi\b|نہیں|نھیں|नहीं|^لم|^ما\s|دون|بدون"
)
# 'has not failed', 'never failed', 'nobody ...': a negation just before the cue
_NEG_BEFORE = re.compile(
    r"(?:\b(?:not|never|no|hasn't|haven't|hadn't|isn't|wasn't|aren't|weren't|didn't|doesn't|"
    r"don't|won't|cannot|can't|nahi|nahin|nhi|kabhi)\b|نہیں|نھیں|नहीं|\bلم\b|\bلا\b|\bليس\b)"
    r"[\s,]*(?:\S+\s+){0,2}\S*$"
)
# 'nakam nahi hue', 'ناکام نہیں ہوا', 'असफल नहीं हुआ': a negation right after the cue
_NEG_AFTER = re.compile(r"^\s*(?:\S+\s+)?(?:nahi|nahin|nhi|نہیں|نھیں|नहीं)(?:\s|$)")

# A hypothetical, conditional or question: not something that happened
_HYPOTHETICAL = re.compile(
    r"\b(?:if|what if|suppose|supposing|in case|should i|shall i|would it|do you think|"
    r"can i|could i|will it|would)\b"
    r"|\bagar\b|\bkya (?:main|hum|aap|yeh|ye|is|isse|mujhe|humein)\b|\bkarun\b|\bkarte to\b"
    r"|\bjo\b.{0,30}\bto\b.{0,30}\bkaisa\b"
    r"|اگر|^\s*کیا\s|\bلو\b|إذا|^\s*هل\s|अगर|^\s*क्या\s"
)
# A third party did it (a competitor, a brother, 'neighbour ne aazmaya', 'woh log')
_THIRD_PARTY = re.compile(
    r"\b(?:they|he|she|someone|somebody|people|others|competitors?|neighbou?rs?|brother|sister|"
    r"friend|cousin|uncle|aunt|father|mother|wife|husband|partner|colleague|supplier|rival)\b"
    r"|\b(?:woh log|wo log|dusre log|doosre log|baaz log|unhon ?e? ?ne|unho ?ne|usne|us ne|"
    r"bhai ne|behan ne|padosi(?: ne)?|dost ne|competitor ne|neighbou?r ne|rishtedar)\b"
    r"|پڑوسی|بھائی نے|دوست نے|انہوں نے|اس نے|وہ لوگ|ان لوگوں|مقابل"
    r"|جاري|جيراني|أخي|اخي|منافس|صديقي|هم جربوا|هم حاولوا"
    r"|पड़ोसी|भाई ने|दोस्त ने|उन्होंने|उसने|वो लोग|वह लोग"
)
# The owner says they did it too
_FIRST_PERSON = re.compile(
    r"\b(?:i|we|maine|humne|mene|main ne|hum ne|mein ne)\b"
    r"|میں نے|ہم نے|جربت|جربنا|حاولت|حاولنا|मैंने|हमने"
)

_LEAD = re.compile(
    r"^(?:(?:we|i|hum|humne|already|have|had|previously|once|maine|so|and|but|lekin|phir)\s+)*"
    r"(?:(?:tried|try|aazmaya|used)\s+)?"
    r"(?:(?:جربت|جربنا|حاولت|حاولنا)\s+)?"
)
_TAIL = re.compile(
    r"(?:\s*(?:,|\band\b|\bbut\b|\blekin\b|\bpar\b|\bmagar\b|\bit\b|\bthat\b|\bthey\b|\bwhich\b|"
    r"\bbefore\b|\bearlier\b|\balready\b|\bpehle\b|\btry\b|\btried\b|\bkiye\b|\bkiya\b|\btha\b|"
    r"\bthe\b|\baazmaya\b|\bistemal\b|\bistamal\b|\buse\b|\bused\b|\bonce\b|"
    r"\blast (?:year|month|week)\b|\bin the past\b|\bpreviously\b))*\s*$"
)
_DELIMITER = re.compile(r"([.!?؟;\n]+)")  # a comma, Arabic or Latin, does not split a clause
MAX_TEXT = 4000
MAX_WHAT = 160


class FailedAttempt(NamedTuple):
    what: str  # what was tried, in the owner's own wording ("rang wale folder")
    cue: str  # the failure words found


def _squash(text: str) -> str:
    return " ".join(str(text or "").casefold().replace("’", "'").split())[:MAX_TEXT]


def split_clauses(text: str | None) -> list[tuple[str, bool]]:
    """(clause, is_question) pairs. A comma does not split ("folders tried, kaam nahi aaya")."""
    parts = _DELIMITER.split(str(text or ""))
    out: list[tuple[str, bool]] = []
    for i in range(0, len(parts), 2):
        body = parts[i]
        delimiter = parts[i + 1] if i + 1 < len(parts) else ""
        if body.strip():
            out.append((body, "?" in delimiter or "؟" in delimiter))
    return out


# Said as not done, or not yet done: no attempt happened.
_NOT_TRIED = re.compile(
    r"\b(?:never|haven't|hasn't|hadn't|have not|has not|had not|did not|didn't|do not|don't|"
    r"not yet|yet to|plan(?:s|ned|ning)? to|going to|want(?:ed)? to|hope(?:fully)?|intend(?:ed)? to"
    r"|will|would|may|might|should)\b(?:\s+\w+){0,3}?\s+(?:try|tried|trying)\b"
    r"|\bnot (?:tried|try)\b|\bnot yet\b|\bhope(?:fully)?\b|\bhaven't\b.{0,12}\byet\b"
    r"|\btry (?:nahi|nahin|nhi)\b|\baazma\w* (?:nahi|nahin|nhi)\b"
    r"|\bkabhi (?:\w+ ){0,3}(?:nahi|nahin|nhi)\b|\b(?:nahi|nahin|nhi) (?:kiye|kiya|try|aazma\w*)\b"
    r"|\babhi (?:tak )?(?:nahi|nahin)\b|\bsuna hai\b|\bsocha hai\b|\bkarenge\b|\bkaren ge\b"
    r"|\bkaroonga\b|\bkarungi\b|\bkarun\b|\bkarna chahte\b"
    r"|نہیں آزما|آزما\w* نہیں|کبھی نہیں|ابھی نہیں|سنا ہے|ارادہ|کوشش نہیں"
    r"|لم (?:أ|ن|ا)?جرب|لم (?:أ|ن|ا)?حاول|لا (?:أ|ن)جرب|سأجرب|سنجرب|سمعت|لن (?:أ|ن)جرب"
    r"|नहीं आज़माया|नहीं आजमाया|आज़माया नहीं|कभी नहीं|अभी नहीं|सुना है|इरादा|करेंगे"
)
_URDU_LETTER = re.compile(r"[ٹڈڑںھہےکگچپژی]")
_ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ROMAN_URDU = re.compile(
    r"\b(?:kiye|kiya|kiyay|aazma\w*|hain|nahi|nahin|lekin|pehle|gaye|gayi|raha|rahi|rahe|istemal"
    r"|kaam|aur|mein|humne|maine|mene)\b"
)
_NE = re.compile(r"(\S+) (?:ne|نے|ने)(?=\s|$)")
_OWN_NE = frozenset({"hum", "main", "mein", "mai", "ہم", "میں", "मैं", "हम"})


def _dropped_subject_ok(said: str) -> bool:
    """No first-person word in the clause: Roman Urdu, Urdu and Hindi leave the subject out
    ("folder try kiye lekin mix ho gaye") and that is read as the owner's, unless another subject
    is named. English and Arabic need the owner as a named subject."""
    if any(m.group(1) not in _OWN_NE for m in _NE.finditer(said)):
        return False  # "padosi ne ...": someone else did it
    if _THIRD_PARTY.search(said):
        return False
    if _ARABIC_SCRIPT.search(said):
        return _URDU_LETTER.search(said) is not None
    if _DEVANAGARI.search(said):
        return True
    return _ROMAN_URDU.search(said) is not None


def _owner_attempt(said: str, is_question: bool) -> bool:
    """Whether a squashed clause is the OWNER saying they tried something: the owner is the
    subject (a first-person word, or no named subject in a language that drops it), an attempt
    word is there, and it is not a question, a hypothetical, a plan or a "never tried"."""
    if is_question or _HYPOTHETICAL.search(said) or not ATTEMPT.search(said):
        return False
    if _NOT_TRIED.search(said):
        return False
    if _FIRST_PERSON.search(said):
        return True
    return _dropped_subject_ok(said)


def owner_clauses(text: str | None) -> list[str]:
    """The squashed clauses of `text` that can be the owner's own statement of an attempt: not a
    question, not a hypothetical, not only a third party's attempt."""
    return [s for c, q in split_clauses(text) if _owner_attempt(s := _squash(c), q)]


def _negated(said: str, found: re.Match[str]) -> bool:
    cue = found.group(0)
    if _OWN_NEGATION.search(cue):
        return False
    return bool(_NEG_BEFORE.search(said[: found.start()]) or _NEG_AFTER.search(said[found.end() :]))


def _failure(said: str) -> re.Match[str] | None:
    """The failure cue in one squashed clause, or None (negated and weak-without-attempt cues do
    not count)."""
    strong = FAIL_STRONG.search(said)
    if strong and not _negated(said, strong):
        return strong
    attempt = ATTEMPT.search(said)
    if attempt:
        for weak in FAIL_BESIDE_ATTEMPT.finditer(said):
            if weak.start() > attempt.start() and not _negated(said, weak):
                return weak
    return None


def _worked(said: str) -> bool:
    found = WORKED.search(said)
    return found is not None and not _NEG_BEFORE.search(said[: found.start()])


def clause_outcome(said: str) -> str:
    """ "failed", "worked" or "unclear" for ONE squashed clause that passed owner_clauses."""
    if _failure(said) is not None:
        return "failed"
    return "worked" if _worked(said) else "unclear"


def _what_before(said: str, at: int) -> str:
    before = said[:at]
    for marker in ("pehle", "try ", "aazma", "kiya tha", "rakha tha"):
        spot = before.find(marker)
        if spot > 0:
            before = before[:spot]
    before = _TAIL.sub("", _LEAD.sub("", before.strip()[-240:]))
    return before.strip(" ,:-")[:MAX_WHAT].strip()


def failed_attempt(text: str | None, language: str | None = None) -> FailedAttempt | None:
    """The first failed attempt the owner's text says, or None. `language` is accepted for callers
    that know it; the cues are read for every language at once (a mixed message is common)."""
    for said in owner_clauses(text):
        found = _failure(said)
        if found is not None:
            return FailedAttempt(_what_before(said, found.start()), found.group(0))
    return None


def outcome_of(text: str | None) -> str:
    """ "failed" when the text says the attempt did not help, "worked" when it says it did (and not
    the opposite), else "unclear". Questions, hypotheticals and a third party's attempt are
    ignored."""
    outcomes = [clause_outcome(s) for s in owner_clauses(text)]
    if "failed" in outcomes:
        return "failed"
    return "worked" if "worked" in outcomes else "unclear"


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
