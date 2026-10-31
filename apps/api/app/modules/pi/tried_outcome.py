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
from collections.abc import Callable
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
    r"|\bnothing came of (?:it|them)\b|\bno luck\b|\bkuch(?:h)? nahi hua\b|\bbek(?:a)?ar gaye\b"
    r"|\bnakam\b|\bbe-?asar\b|\b(?:nahi|nahin|nhi) chal(?:a|e|i)\b"
    r"|نہیں چل(?:ا|ے|ی)|नहीं चल(?:ा|े|ी)|لم (?:يعمل|تعمل|تنفع)"
    r"|ناکام|(?:فائدہ|فایدہ|اثر|نتیجہ)\s+(?:نہیں|نھیں)|کام\s+نہیں\s+(?:آیا|کیا)"
    r"|لم\s+[يت](?:نجح|فد|نفع)|ما\s+(?:نفع|نجح|أفاد|افاد)|و?فشل|دون\s+جدوى|بدون\s+فائدة"
    r"|काम\s+नहीं\s+आया|(?:फायदा|फ़ायदा|असर|नतीजा)\s+नहीं|असफल|नाकाम"
    r"|\b(?:stopped working|then it stopped|then (?:it )?(?:failed|died|dropped|faded)|wore off"
    r"|fizzled"
    r"|petered out|worked (?:only )?(?:at first|initially|for a (?:week|while|few days|bit)))\b"
    r"|\bphir band ho (?:gaya|gayi|gaye)\b|\bbaad mein (?:kaam )?nahi\b"
    r"|\bkuch din (?:chala|kaam kiya) phir\b"
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
    r"\b(?:it worked|worked well|that worked|worked|which did|that did|helped"
    r"|brought (?:in )?(?:some |more )?(?:customers|sales|orders)|kaam aaya|kaam aaye|faida hua"
    r"|fayda hua|asar hua|chal gaye|chal gaya|chal gayi|chale|chala|kaam kar gaye|kaam kar gaya)\b"
    r"|چل گئے|چل گیا|چل گئی|کام کر گئے|کام کر گیا|चल गए|चल गया|चले|काम कर गए|काम आए|نجحت"
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


_AUX_EN = (
    r"(?:(?:have|had|did|do|really|already|also|even|just|then|first|once|previously|personally"
    r"|actually|finally|both|all|ourselves|myself|definitely|certainly|honestly)\s+)*"
)
# The ALLOWLIST (L1 round 4): the owner is the grammatical subject of the attempt verb, said in
# their own first person. Anything else (a passive "were tried", a noun subject, "I know ... tried",
# a verb with no subject, a bare "tried flyers") is not read as the owner's attempt.
_OWN_ATTEMPT = re.compile(
    r"\b(?:i|we)(?:'ve|'d)?\s+" + _AUX_EN + r"(?:tried|try|trying)\b"
    r"|\b(?:maine|mene|main ne|humne|hum ne|mein ne|hamne|ham ne)\b(?:\s+\S+){0,4}?"
    r"\s+(?:try|aazma\w*|koshish)\b"
    r"|(?<![؀-ۿ])(?:میں نے|ہم نے)(?![؀-ۿ])(?:\s+\S+){0,4}?\s+(?:آزما\S*|کوشش\S*)"
    r"|^\s*(?:(?:و|ف)?(?:أنا|انا|نحن)\s+|(?:و|ف|ثم|لقد|قد)\s*)?"
    r"(?:جربت|جربنا|حاولت|حاولنا)(?![؀-ۿ])"
    r"|(?<![ऀ-ॿ])(?:मैंने|हमने)(?![ऀ-ॿ])(?:\s+\S+){0,4}?\s+(?:आज़मा\S*|आजमा\S*|कोशिश\S*)"
)
# "I used / ran / put up X" is an attempt only when it comes with a failure cue in the same clause.
_OWN_USE = re.compile(
    r"\b(?:i|we)(?:'ve|'d)?\s+"
    + _AUX_EN
    + r"(?:ran|used|launched|printed|distributed|gave\s+\S+\s+a go)\b"
    r"|\b(?:maine|mene|main ne|humne|hum ne|mein ne|hamne|ham ne)\b(?:\s+\S+){0,4}?"
    r"\s+(?:lagaye|lagaya|lagai|laga diye|chalaye|chalaya|istemal kiya|istamal kiya)\b"
    r"|(?<![؀-ۿ])(?:میں نے|ہم نے)(?![؀-ۿ])(?:\s+\S+){0,4}?\s+(?:لگائے|لگایا|چلائے|استعمال)"
    r"|^\s*(?:(?:و|ف)?(?:أنا|انا|نحن)\s+|(?:و|ف|ثم|لقد|قد)\s*)?(?:استخدمت|استخدمنا)(?![؀-ۿ])"
    r"|(?<![ऀ-ॿ])(?:मैंने|हमने)(?![ऀ-ॿ])(?:\s+\S+){0,4}?\s+(?:लगाए|लगाया|चलाए|इस्तेमाल)"
)
# Even with the owner as subject, these say it was not an attempt of theirs or not an attempt to
# solve the problem (avoid, whether, instead of), or not theirs (took over, was away, I know).
_NOT_THEIRS = re.compile(
    r"\b(?:to avoid|to stop|not to|whether|instead of|rather than|took over|take over|joined|"
    r"was away|were away|wasn't here|i know|i heard|i was told|they say|people say|"
    r"suna|suni|kehte hain|logon ne|log kehte|bachne)\b"
    r"|سنا|سنی|لوگوں نے|سمعت|قيل|सुना|लोगों ने|बचने के"
)


def _owner_attempt(said: str, is_question: bool) -> bool:
    """Whether a squashed clause is the OWNER saying they tried something: an allowlist, not a
    blocklist. The owner is the subject in their first person (`_OWN_ATTEMPT`: "I/we tried",
    "maine/humne ... try/aazmaya", "میں نے/ہم نے ... آزمایا", "جربت/جربنا", "मैंने/हमने ... आज़माया"),
    and the clause is not a question, a hypothetical, a plan, a "never tried", a source ("I heard",
    "maine suna"), another subject's ("log ne", "padosi ne") or someone else's attempt."""
    if is_question or _HYPOTHETICAL.search(said):
        return False
    used = _OWN_USE.search(said) is not None and FAIL_STRONG.search(said) is not None
    if not (ATTEMPT.search(said) or used):
        return False
    if _NOT_TRIED.search(said) or _NOT_THEIRS.search(said) or _THIRD_PARTY.search(said):
        return False
    if any(m.group(1) not in _OWN_NE for m in _NE.finditer(said)):
        return False  # "padosi ne ...": someone else did it
    return _OWN_ATTEMPT.search(said) is not None or used


def owner_clauses_with_followups(text: str | None) -> list[str]:
    """Each owner attempt clause with the plain clauses right after it ("I tried flyers and ads;
    flyers did nothing, ads brought customers"): only for reading an outcome, never for finding an
    attempt. A follow-up that is a question, a hypothetical, a source or someone else's is cut."""
    parts = split_clauses(text)
    out: list[str] = []
    for n, (clause, is_question) in enumerate(parts):
        said = _squash(clause)
        if not _owner_attempt(said, is_question):
            continue
        joined = [said]
        for follow, follow_question in parts[n + 1 :]:
            f = _squash(follow)
            if (
                follow_question
                or _owner_attempt(f, False)
                or _HYPOTHETICAL.search(f)
                or _THIRD_PARTY.search(f)
                or _NOT_THEIRS.search(f)
                or _NOT_TRIED.search(f)
                or any(m.group(1) not in _OWN_NE for m in _NE.finditer(f))
            ):
                break
            joined.append(f)
        out.append(" ; ".join(joined))
    return out


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


_PARTLY = re.compile(
    r"\b(?:half|partly|partially|somewhat|barely|hardly|kind of|sort of|a bit)\s+(?:\w+\s+)?$"
)
_NONE_WORKED = re.compile(r"\b(?:neither|none of (?:them|these)|nothing)\b.*\bworked\b")


def _worked(said: str) -> bool:
    found = WORKED.search(said)
    if found is None or _NONE_WORKED.search(said):
        return False
    before = said[: found.start()]
    return not _NEG_BEFORE.search(before) and not _PARTLY.search(before)


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


# --- one outcome per attempt (L1 round 4) -------------------------------------------------------
_SEGMENT = re.compile(
    r"[,;:،؛]|(?:^|\s)(?:but|while|whereas|then|lekin|magar|par|jabke|phir)(?=\s)|"
    r"(?<![؀-ۿऀ-ॿ])(?:مگر|لکن|لیکن|لكن|ثم|पर|लेकिन|मगर|फिर)(?![؀-ۿऀ-ॿ])"
)
_ALL = re.compile(
    r"\b(?:both|neither|none of (?:them|these)|all of them|dono|donon|sab)\b"
    r"|دونوں|كلاهما|كلتاهما|दोनों"
)
_ELLIPSIS_NO = re.compile(
    r"\b(?:did not|didn't|didnt|do not|don't|could not|couldn't|nahi|nahin|nhi)\s*$"
    r"|نہیں\s*$|नहीं\s*$"
)


def _segment_outcome(seg: str) -> str:
    """failed, worked or "" for one segment, with no attempt word needed ("flyers failed",
    "ads worked", "flyers did not", "kuch nahi hua")."""
    strong = FAIL_STRONG.search(seg)
    if strong and not _negated(seg, strong):
        return "failed"
    weak = FAIL_BESIDE_ATTEMPT.search(seg)
    if weak and not _negated(seg, weak):
        return "failed"
    if _ELLIPSIS_NO.search(seg) or _NONE_WORKED.search(seg):
        return "failed"
    return "worked" if _worked(seg) else ""


def item_outcomes(said: str, mentions: list[Callable[[str], bool]]) -> list[str]:
    """The outcome of EACH attempt named in one squashed owner clause ("failed", "worked" or "" for
    not said). The clause is cut into segments; a cue applies to the attempts named in its own
    segment, a cue with no attempt named ("it did not work") to the attempts named just before it,
    and "both" / "neither" to every attempt named so far. A clause that names one attempt only reads
    as a whole. Two cues for one attempt: failed wins (a repeat of a failure is the unsafe one)."""
    named = [i for i, m in enumerate(mentions) if m(said)]
    if len(named) <= 1:
        result = clause_outcome(said)
        return [result if i in named and result != "unclear" else "" for i in range(len(mentions))]
    segments = [t.strip() for t in _SEGMENT.split(said) if t and t.strip()]
    out = [""] * len(mentions)
    seen: list[int] = []
    last: list[int] = []
    for seg in segments:
        here = [i for i, m in enumerate(mentions) if m(seg)]
        cue = _segment_outcome(seg)
        if here:
            seen = list(dict.fromkeys([*seen, *here]))
            last = here
        targets = here or (seen if _ALL.search(seg) else last)
        if cue:
            for i in targets:
                out[i] = "failed" if "failed" in (out[i], cue) else cue
    return out
