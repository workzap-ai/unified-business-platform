"""Platform spec v1.5, Part 18: checks in code that run before a reply is sent.

Pure functions. Each returns a short reason the model can act on (None when the reply may go), so
the caller can add it to the one rewrite request, as for every other guard. The rules here:

- openingGate (18.2): the first reply to a number with no profile and no earlier conversation has
  the AI line and the identity question, never the old greeting, never a problem question.
- noEmptyOpener (18.8): a reply may not start with filler ("Understood", "Noted", "That covers a lot
  of ground", "Here are some ideas for you:").
- alreadyAnswered (18.5): a question whose answer the owner already gave is dropped; a closed list
  of areas is never offered before the business is known.
- offer text (18.3): "You can say no" is removed from an offer, and an offer never rides in the
  same turn as the first map.
"""

import os
import re
from typing import Any

from app.modules.pi.script_words import MARKS, fold, is_latin, stem

# 18.2 "Forbidden strings": the old greeting in English, Roman Urdu and Urdu.
FORBIDDEN_OPENING = re.compile(
    r"going\s+wrong\s+in\s+your\s+business|i['’`]?ll\s+start\s+on\s+it|"
    r"aap\s+ke\s+(?:business|karobar|karobaar)\s+mein\s+kya\s+(?:masla|galat)|"
    r"(?:business|karobar|karobaar)\s+mein\s+jo\s+masla\s+hai\s+woh\s+batayein|"
    r"main\s+(?:us\s+par|is\s+par)\s+kaam\s+shuru|"
    r"آپ\s+کے\s+کاروبار\s+میں\s+کیا\s+(?:مسئلہ|غلط)|کاروبار\s+میں\s+جو\s+مسئلہ\s+ہے\s+وہ\s+بتائیں",
    re.IGNORECASE,
)
AI_LINE = re.compile(
    r"\b(?:an?\s+AI|AI\s+from|AI\s+assistant|ka\s+AI|ai\s+hoon)\b|ذکاء\s+اصطناعی|مصنوعی\s+ذہانت|"
    r"\bAI\b",
    re.IGNORECASE,
)
# The identity question: the business name or what it does/makes/sells (EN, Roman Urdu, Urdu).
IDENTITY_QUESTION = re.compile(
    r"(?:what\s+(?:is|does)\s+(?:it|your\s+business)|your\s+business|business\s+called|"
    r"what\s+do\s+you\s+(?:make|sell|do)|karobar|business\s+(?:kya|ka\s+naam)|kya\s+kaam|"
    r"naam\s+kya|kis\s+cheez|کاروبار|نام\s+کیا|کیا\s+کام)",
    re.IGNORECASE,
)
# A problem question in a first reply (18.2): it asks about trouble before the business is known.
PROBLEM_QUESTION = re.compile(
    r"(?:what(?:['’]s|\s+is)\s+(?:going\s+wrong|the\s+(?:problem|issue)|bothering|worrying)|"
    r"what\s+(?:problem|issue|trouble)|where\s+(?:does\s+it|do\s+you)\s+hurt|"
    r"kya\s+(?:masla|mushkil|pareshani)|kon\s*sa\s+masla|مسئلہ\s+کیا|کیا\s+مسئلہ)",
    re.IGNORECASE,
)


def _questions(reply: str) -> list[str]:
    parts = re.split(r"(?<=[?؟])\s+", reply.strip())
    return [p for p in parts if p.endswith(("?", "؟"))]


def forbidden_opening(reply: str) -> str | None:
    """The old greeting (or its translation) anywhere in a reply: blocked in every reply (OG2)."""
    if FORBIDDEN_OPENING.search(reply or ""):
        return (
            "it contains the old opening line ('what's going wrong in your business' / 'I'll start "
            "on it'). Never use it"
        )
    return None


def is_first_reply(context: dict[str, Any]) -> bool:
    """A number with no earlier pi reply and no stored profile with a confirmed business name
    (18.2 return rule: a number that merely sent messages before is not skipped)."""
    if context.get("force_opening") or os.environ.get("FORCE_OPENING", "").lower() == "true":
        return True  # FORCE_OPENING: a known test number sees what a new owner sees
    if context.get("noted_problems") or context.get("returning_customer"):
        return False
    profile = (context.get("brief") or {}).get("business_profile") or {}
    if profile.get("confirmed_name") or profile.get("business_name"):
        return False
    return not any(h.get("role") == "ai" for h in context.get("history") or [])


def opening_problem(
    reply: str, context: dict[str, Any], business_known: bool = False
) -> str | None:
    """openingGate (18.2) for the first reply: the AI line first, then one identity question, and
    no problem question. When the owner already said what the business is, the identity question
    is not required (the next missing item is asked)."""
    if not is_first_reply(context):
        return None
    text = (reply or "").strip()
    if not text:
        return None
    if forbidden_opening(text):
        return forbidden_opening(text)
    problems: list[str] = []
    if not AI_LINE.search(text):
        problems.append("it must say pi is an AI from Workzap in the greeting")
    questions = _questions(text)
    if any(PROBLEM_QUESTION.search(q) for q in questions):
        problems.append(
            "it asks a problem question; ask only who they are and what the business does"
        )
    elif not business_known and not any(IDENTITY_QUESTION.search(q) for q in questions):
        problems.append(
            "it must ask one identity question: the business name and what it makes or sells"
        )
    if not problems:
        return None
    return "the first reply to a new number is wrong: " + "; ".join(problems)


# 18.8: filler the first sentence may not be.
EMPTY_OPENERS = re.compile(
    r"^\s*(?:(?:internal\s+(?:issues|problems),?\s+)?understood|noted|got\s+it|i\s+see|"
    r"that\s+covers\s+a\s+lot\s+of\s+ground|that['’]s\s+a\s+lot\s+of\s+ground|"
    r"here\s+are\s+some\s+(?:ideas|tips|suggestions)\s+for\s+you|okay|ok|sure|alright|"
    r"(?:alag\s+)?note\s+kar\s+li(?:ya|a)?|samajh\s+gaya|samajh\s+gayi)\s*[.!:,\-–—]*(?:\s|$)",
    re.IGNORECASE,
)
_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def empty_opener(reply: str) -> str | None:
    """noEmptyOpener (18.8): a reply that starts with filler. The first sentence must carry
    content: what pi noticed, a number worked, or the answer."""
    if EMPTY_OPENERS.match(reply or ""):
        return (
            "it starts with an empty opener ('Understood', 'Noted', 'That covers a lot of ground', "
            "'Here are some ideas for you:'). Start with content: what you noticed, a number "
            "worked, or the answer"
        )
    return None


def shares_owner_fact(sentence: str, owner_texts: list[str]) -> bool:
    """True when the sentence uses at least one fact (a number or a content word) from the owner."""
    theirs = " ".join(owner_texts).casefold()
    for number in re.findall(r"\d+(?:[.,]\d+)?", sentence):
        if number in theirs:
            return True
    return any(w.casefold()[:5] in theirs for w in _WORD.findall(sentence))


# 18.5: "sales, stock, staff or cash" before the business is known.
CLOSED_AREAS = re.compile(
    r"\b(?:sales|stock|staff|cash|customers|marketing|suppliers)\b"
    r"(?:\s*,\s*(?:sales|stock|staff|cash|customers|marketing|suppliers)\b){1,}"
    r"(?:\s*,?\s*(?:or|ya|aur)\s+\w+)?",
    re.IGNORECASE,
)


AREA_WORDS = ("sales", "stock", "staff", "cash", "customers", "marketing", "suppliers")


def closed_list_early(reply: str, owner_texts: list[str], business_known: bool) -> str | None:
    """Before the business is known, a question never lists areas the owner did not say."""
    if business_known:
        return None
    theirs = " ".join(owner_texts).casefold()
    for q in _questions(reply):
        m = CLOSED_AREAS.search(q)
        if not m:
            continue
        listed = [w for w in AREA_WORDS if re.search(rf"\b{w}\b", m.group(0), re.IGNORECASE)]
        if any(w not in theirs for w in listed):
            return (
                "it offers a closed list of areas (sales, stock, staff or cash) before the "
                "business is known. Ask what the business does instead"
            )
    return None


def question_already_answered(reply: str, said: list[str], profile_text: str = "") -> str | None:
    """alreadyAnswered (18.5), the narrow case that is certain: pi asks for the business name or
    what the business does when the owner or the profile already gave it."""
    known = profile_text.strip()
    if not known:
        return None
    for q in _questions(reply):
        if IDENTITY_QUESTION.search(q) and re.search(
            r"(?:business\s+called|what\s+does\s+(?:it|your\s+business)|what\s+do\s+you\s+(?:make|sell))",
            q,
            re.IGNORECASE,
        ):
            return (
                "it asks what the business is, but the owner already said: "
                f"'{known[:120]}'. Use it; ask the next thing you do not know"
            )
    return None


_NUMBER_WORDS = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|ek|do|teen|char|paanch|panch)"
_COUNT = rf"(?:\d+|{_NUMBER_WORDS})"
_UNITS = r"(?:days?|weeks?|months?|years?|din|hafte|mahine|mahino|saal)"
# A question about a count: "how many shops", "kitni dukaan" -> the noun it counts.
ASK_COUNT = re.compile(r"(?:how\s+many|kitn[eiy]|kitna)\s+(?:of\s+)?([^\W\d_]{3,})", re.IGNORECASE)
ASK_SINCE = re.compile(
    r"since\s+when|how\s+long|kab\s+se|kitne\s+(?:din|hafte|mahine|saal|dino|mahino)\s+se",
    re.IGNORECASE,
)
SAID_SINCE = re.compile(
    rf"(?:since\s+(?!when\b)[a-z0-9]+|for\s+{_COUNT}\s+{_UNITS}|{_COUNT}\s+{_UNITS}\s+se|"
    r"pichh?le\s+\w+\s+se)",
    re.IGNORECASE,
)
ASK_OFTEN = re.compile(r"how\s+often|kitni\s+(?:baar|dafa|bar)", re.IGNORECASE)
SAID_OFTEN = re.compile(
    r"\b(?:every\s*(?:day|week|month|morning|evening|time)|daily|weekly|monthly|hamesha|always|"
    r"har\s+(?:roz|din|hafta|mahine|baar)|roz)\b|"
    rf"\b{_COUNT}\s+times?\s+(?:a|per)\s+\w+",
    re.IGNORECASE,
)


# L1-7a: the same three asks in Hindi (Devanagari), Urdu script and Arabic. Patterns are written
# in the folded shape (`script_words.fold`: one form of yeh, kaf, heh, hamza, no nukta, no
# harakat) and run on folded text. Written by one author, not reviewed by a native speaker.
# fold() lower-cases the whole pattern, so never write an upper-case escape (\S, \W) in them.
_LETTER = rf"(?:[^\W\d_]|[{MARKS}])"  # a letter or a combining mark inside a word
_WB = rf"(?<![\w{MARKS}])"  # a word starts here
_WE = rf"(?![\w{MARKS}])"  # a word ends here

_SCRIPT_NUMBER_WORDS = fold(
    "एक|दो|तीन|चार|पांच|पाँच|छह|छः|सात|आठ|नौ|दस|बीस|तीस|"  # Hindi
    "ایک|دو|تین|چار|پانچ|چھ|سات|آٹھ|نو|دس|بیس|تیس|"  # Urdu
    "واحد|اثنين|اثنان|ثلاثة|ثلاث|أربعة|أربع|خمسة|خمس|ستة|ست|سبعة|سبع|ثمانية|ثماني|تسعة|تسع|"
    "عشرة|عشر|عشرين|ثلاثين"  # Arabic
)
_SCRIPT_COUNT = rf"(?:\d+|{_WB}(?:{_SCRIPT_NUMBER_WORDS}){_WE})"
_SCRIPT_UNITS = fold(
    "दिन|हफ्ते|हफ्ता|सप्ताह|महीने|महीना|महीनों|साल|सालों|वर्ष|"  # Hindi
    "دن|دنوں|ہفتے|ہفتہ|مہینے|مہینہ|مہینوں|سال|سالوں|برس|"  # Urdu
    "يوم|ايام|أيام|اسبوع|أسبوع|اسابيع|أسابيع|شهر|أشهر|اشهر|شهور|سنة|سنوات|سنين|عام|أعوام"  # Arabic
)
_SCRIPT_UNIT = rf"{_WB}(?:{_SCRIPT_UNITS}){_WE}"


def _f(pattern: str) -> str:
    """The pattern in folded shape. <wb>, <we>, <count> and <unit> stand for the shared pieces
    (put in after folding, because folding would strip the combining marks from their classes)."""
    return (
        fold(pattern)
        .replace("<wb>", _WB)
        .replace("<we>", _WE)
        .replace("<count>", _SCRIPT_COUNT)
        .replace("<unit>", _SCRIPT_UNIT)
    )


# "how many X": Hindi/Urdu कितने/کتنے anywhere; Arabic كم only at the start of the question (in
# Urdu كم means "less" and would otherwise read as a count question).
ASK_COUNT_SCRIPT = re.compile(
    _f(
        r"(?:<wb>(?:कितने|कितनी|कितना|کتنے|کتنی|کتنا)<we>|^\s*[وف]?كم<we>(?:\s+عدد)?)"
        r"\s+(?:सारे\s+|سارے\s+)?"
    )
    + rf"({_LETTER}{{3,}})"
)
ASK_COUNT_NOT_A_COUNT = frozenset(
    fold(w)
    for w in "दिन हफ्ते महीने साल बार دن ہفتے مہینے سال بار يوم اسبوع شهر سنة مرة مرات وقت".split()
)
ASK_SINCE_SCRIPT = re.compile(
    _f(
        r"<wb>(?:कब\s+से|कितने\s+(?:दिन|हफ्ते|महीने|साल|समय)\s+से|कितनी\s+देर\s+से|"
        r"کب\s+سے|کتنے\s+(?:دن|ہفتے|مہینے|سال|عرصے)\s+سے|"
        r"منذ\s+متى|من\s+متى|منذ\s+كم|كم\s+(?:من\s+)?(?:الوقت|مدة|يوم|أسبوع|شهر|سنة)|"
        r"من\s+كم\s+(?:يوم|أسبوع|شهر|سنة))"
    )
)
SAID_SINCE_SCRIPT = re.compile(
    _f(
        r"(?:<count>\s+<unit>\s+(?:से|سے)|"
        r"منذ\s+(?:<count>\s+)?<unit>|"
        r"<wb>منذ\s+(?:سنتين|شهرين|أسبوعين|يومين)|"
        r"पिछले\s+[^\s]+\s+से|پچھلے\s+[^\s]+\s+سے)"
    )
)
ASK_OFTEN_SCRIPT = re.compile(
    _f(r"<wb>(?:कितनी\s+(?:बार|दफा|दफ़ा)|کتنی\s+(?:بار|دفعہ|دفعه)|كم\s+(?:مرة|مرات))<we>")
)
SAID_OFTEN_SCRIPT = re.compile(
    _f(
        r"<wb>(?:हर\s+(?:दिन|रोज|हफ्ते|महीने|बार)|रोज|रोजाना|हमेशा|प्रतिदिन|"
        r"ہر\s+(?:روز|دن|ہفتے|مہینے|بار)|روز|روزانہ|ہمیشہ|"
        r"كل\s+(?:يوم|أسبوع|شهر|مرة)|يوميا|أسبوعيا|شهريا|دائما|مرتين)"
        r"<we>|<count>\s+(?:बार|بار|مرات)"
    )
)


def _owner_count_hit(noun: str, theirs: str) -> str | None:
    """The owner's own words for "N <the noun>", in Latin, Devanagari, Urdu or Arabic script."""
    word = stem(fold(noun))
    if fold(noun) in ASK_COUNT_NOT_A_COUNT or word in ASK_COUNT_NOT_A_COUNT:
        return None
    key = word[: 4 if is_latin(word) else 3]
    hit = re.search(
        rf"{_SCRIPT_COUNT}\s+(?:{_LETTER}+\s+)?{_LETTER}*{re.escape(key)}{_LETTER}*", theirs
    )
    return hit.group(0) if hit else None


def _script_fact(question: str, theirs: str) -> str | None:
    """A Hindi, Urdu-script or Arabic ask (count, since when, how often) the owner already
    answered, as the owner's own words; None when it asks nothing of the kind or it is not said."""
    q, said = fold(question), fold(theirs)
    for m in ASK_COUNT_SCRIPT.finditer(q):
        if hit := _owner_count_hit(m.group(1), said):
            return hit
    if ASK_SINCE_SCRIPT.search(q) and (m2 := SAID_SINCE_SCRIPT.search(said)):
        return m2.group(0)
    if ASK_OFTEN_SCRIPT.search(q) and (m3 := SAID_OFTEN_SCRIPT.search(said)):
        return m3.group(0)
    return None


def asks_since(question: str) -> bool:
    return bool(ASK_SINCE.search(question) or ASK_SINCE_SCRIPT.search(fold(question)))


def asks_often(question: str) -> bool:
    return bool(ASK_OFTEN.search(question) or ASK_OFTEN_SCRIPT.search(fold(question)))


def fact_already_given(reply: str, owner_texts: list[str]) -> str | None:
    """alreadyAnswered (18.5) for a count, a duration or a frequency: when the reply asks it and the
    owner already stated it, the reason (quoting their words) so the model can use it instead.
    Narrow on purpose: an unstated fact, or a different thing asked, is never blocked."""
    theirs = " ".join(owner_texts)
    for q in _questions(reply):
        if hit_text := _script_fact(q, theirs):
            return _said(hit_text)
        for noun in ASK_COUNT.findall(q):
            stem = noun.casefold()[:4]
            hit = re.search(
                rf"{_COUNT}\s+(?:\w+\s+)?[^\W\d_]*{re.escape(stem)}[^\W\d_]*", theirs, re.IGNORECASE
            )
            if hit:
                return _said(hit.group(0))
        if ASK_SINCE.search(q) and (hit := SAID_SINCE.search(theirs)):
            return _said(hit.group(0))
        if ASK_OFTEN.search(q) and (hit := SAID_OFTEN.search(theirs)):
            return _said(hit.group(0))
    return None


def _said(words: str) -> str:
    return (
        f"it asks something the owner already said: '{words.strip()}'. Use it, ask what is unknown"
    )


def known_in_record(reply: str, noted: list[dict[str, Any]]) -> str | None:
    """alreadyAnswered (18.5) from the problem record (B6 S5): the reply asks when it began or how
    often, and every noted problem already holds that fact (its `missing` list does not name it).
    The record belongs to the customer, so this holds after the 20-message window and in a new
    chat. Conservative: no noted problem, a record without a `missing` list, or one problem still
    missing the fact, and the question may go."""
    if not noted or not all(isinstance(p.get("missing"), list) for p in noted):
        return None
    for question in _questions(reply):
        for ask, key, what in (
            (asks_since, "since", "when it began"),
            (asks_often, "how_often", "how often it happens"),
        ):
            if ask(question) and all(key not in p["missing"] for p in noted):
                return (
                    f"it asks {what}, but the noted problem already holds it: use it, ask what is "
                    "unknown"
                )
    return None


def opening_log(passed: bool, path: str, prompt_version: str) -> dict[str, str]:
    """What the openingGate log line carries (18.2 Logging): the result, which path wrote the
    opening (the model or the fixed fallback) and the prompt version in force. Never the text."""
    return {
        "result": "pass" if passed else "fail",
        "path": path,
        "prompt_version": prompt_version,
    }


# 18.3: the offer never says the owner may refuse.
SAY_NO = re.compile(
    r"\s*(?:you\s+can\s+(?:always\s+)?say\s+no|no\s+pressure|you\s+can\s+decline)\s*[.!]?",
    re.IGNORECASE,
)


def without_say_no(reply: str) -> str:
    """'You can say no' is pressure, not courtesy: removed from the reply (declining is easy)."""
    cleaned = SAY_NO.sub("", reply or "").rstrip()
    return re.sub(r"[ \t]{2,}", " ", cleaned) or reply
