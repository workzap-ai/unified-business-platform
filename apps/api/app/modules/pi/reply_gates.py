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


def fact_already_given(reply: str, owner_texts: list[str]) -> str | None:
    """alreadyAnswered (18.5) for a count, a duration or a frequency: when the reply asks it and the
    owner already stated it, the reason (quoting their words) so the model can use it instead.
    Narrow on purpose: an unstated fact, or a different thing asked, is never blocked."""
    theirs = " ".join(owner_texts)
    for q in _questions(reply):
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
    r"[,;]?\s*(?:(?:and|aur)\s+)?(?:you\s+can\s+(?:always\s+)?say\s+no(?:\s+to\s+it)?|no\s+pressure|"
    r"you\s+can\s+decline|aap\s+(?:mana|inkaar|inkar)\s+(?:bhi\s+)?kar\s+sakte\s+hain)\s*[.!]?",
    re.IGNORECASE,
)  # English and Roman Urdu: "aur aap mana bhi kar sakte hain" is the same pressure (spec 18.3)


def without_say_no(reply: str) -> str:
    """'You can say no' is pressure, not courtesy: removed from the reply (declining is easy)."""
    cleaned = SAY_NO.sub("", reply or "").rstrip()
    if cleaned and cleaned != (reply or "").rstrip() and cleaned[-1] not in ".!?؟":
        cleaned += "."  # the clause went, the sentence before it still needs its full stop
    return re.sub(r"[ \t]{2,}", " ", cleaned) or reply
