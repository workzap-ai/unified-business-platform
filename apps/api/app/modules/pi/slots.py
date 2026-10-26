"""Closed slots: a question pi asked and the person answered is never asked again (R-ASK-07).

Platform spec Book 2 10.4 and Book 4 5.3: every pi question is a slot (`footfall.current_marketing`,
`shops.count`); any answer, including "no" or "pata nahi", closes it; a closed slot stays closed
across sessions and across a change of language, and a reply that asks it again is sent back.

The model names the slot of the question it asks (`ServiceTurn.asked_slot`), which is what makes the
guard work across languages. When it names none, the question's own words are compared (a question
with most of the same content words is the same slot), which catches a repeat in the same language.
Only pi's own question text is stored, never the person's words.
"""

import re
import unicodedata
from typing import Any

from app.modules.pi import constitution_langs as langs
from app.modules.pi import industry_packs

KEEP = 24  # closed slots kept per conversation
SAME = 0.6  # share of shared content words that makes two questions the same slot
MIN_WORDS = 3  # a question with fewer content words is too thin to compare
CROSS_SHARED = 2  # words two questions in different languages must share to be the same slot
CROSS_SHARE = 0.35  # and the share of the shorter question's words those make
QUESTION_END = ("?", "؟")
STOP = frozenset(
    "the and for with from are was were been our you your this that they them their have has had"
    " does did not can could would should will just very but about into than then there here what"
    " which who how when where why all any some more most much many also only own such ke ki ka"
    " ko se mein hai hain hua hui aur ya ye wo bhi nahi nhi koi kuch sab har par kar kya aap ap"
    " apne apka apki kis kaun kitna kitni kitne".split()
)
# Question words of the other priority languages (French and Spanish are Latin and fold like the
# rest; Hindi, Urdu, Arabic and Persian are kept as written, `industry_packs._fold` splits them).
STOP |= frozenset(
    "les des est que qui dans pour avec vous votre vos une pas plus ont sont quel quelle quels"
    " quoi comment depuis cette ces aux sur par los las del por para con una usted como cual"
    " cuando donde esta estos sus tiene tienen".split()
)
STOP_OTHER_SCRIPT = frozenset(
    "है हैं का के की में से को पर और या क्या आप कब कौन कैसे आपके आपकी आपका"
    " ہے ہیں کا کے کی میں سے کو پر اور یا کیا آپ کب کون کیسے"
    " هل ما هو هي في من على إلى عن أو هذا هذه كان كيف متى"
    " است را در به از که یا آیا شما کدام چه چرا چگونه".split()
)
WORD_SPLIT = re.compile(r"[^\ẁ-ًͯ-ٟऀ-ॿ‌]+")


# R-ASK-05: the generic closer ("anything else?", "aur koi masla?") is a slot of its own. An "ok" or
# a "hmm" skips it, and a skipped question is not asked again until they raise a new problem.
ANYTHING_ELSE_SLOT = "anything_else"
ANYTHING_ELSE = re.compile(
    r"\banything else\b|\bwhat else\b|\bis there anything\b|\bany other (?:problem|issue)\b"
    r"|\b(?:aur|or) koi (?:masla|cheez|baat|problem)\b|\bkoi aur (?:masla|cheez|baat|problem)\b"
    r"|\baur kya (?:masla|cheez)\b|\bmasla ho to\b" + langs.ANYTHING_ELSE,
    re.IGNORECASE,
)
SKIP_ACK = re.compile(
    r"^\W*(?:(?:ok|okay|k|hmm+|hm+|acha|accha|theek|thik|hai|fine|alright|sure|thanks|thank|you|shukriya|ji|g)\b\W*){1,3}$",
    re.IGNORECASE,
)
SKIP_ACK_OTHER = re.compile(langs.SKIP_ACK, re.IGNORECASE)


def question_of(reply: str) -> str:
    """The last question in the reply, "" when it asks none."""
    for sentence in reversed(re.split(r"(?<=[.!?؟])\s+|\n+", reply.strip())):
        sentence = sentence.strip()
        if sentence.endswith(QUESTION_END):
            return sentence[:160]
    return ""


def words(question: str) -> frozenset[str]:
    found: set[str] = set()
    for token in WORD_SPLIT.split(unicodedata.normalize("NFC", question).lower()):
        if re.fullmatch(r"[a-zÀ-ɏ']+", token):  # Latin: fold accents, drop stop words
            word = industry_packs._fold(token)
            if len(word) >= 3 and word not in STOP and re.fullmatch(r"[a-z]+", word):
                found.add(industry_packs._stem(word))
        elif len(token) >= 3 and token not in STOP_OTHER_SCRIPT:
            found.add(industry_packs._arabic_stem(token.replace("‌", "")))
    return frozenset(found)


def _language_of(question: str) -> str | None:
    from app.modules.pi.language import detect_language

    return detect_language(question)


def same_question(a: str, b: str) -> bool:
    left, right = words(a), words(b)
    if len(left) < MIN_WORDS or len(right) < MIN_WORDS:
        return False
    if len(left & right) / len(left | right) >= SAME:
        return True
    # English one turn, Roman Urdu the next: the wording differs but the names and loan words they
    # share ("Instagram", "price", "delivery") are the topic.
    shared = left & right
    one, two = _language_of(a), _language_of(b)
    return bool(
        one
        and two
        and one != two
        and len(shared) >= CROSS_SHARED
        and len(shared) / min(len(left), len(right)) >= CROSS_SHARE
    )


def is_answer(said: str) -> bool:
    """Anything the person says closes the last question, unless it is only a request that pi
    answer something else first (a solution ask, a document ask) or too empty to be an answer."""
    from app.modules.pi import solution_ask

    text = " ".join((said or "").split())
    if not any(ch.isalnum() for ch in text):
        return bool(text)  # a thumbs-up or a number is an answer
    return not solution_ask.asked_for_ideas(text)


def advance(
    previous: dict[str, Any], said: str, reply: str, slot: str, *, new_problem: bool = False
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """(closed slots, the question now open) after a turn: the question asked last turn closes when
    the person answered it, and the question in this reply becomes the open one. A new problem
    reopens the generic "anything else?" (R-ASK-05)."""
    closed = [dict(c) for c in previous.get("closed_slots") or []]
    if new_problem:
        closed = [c for c in closed if c.get("slot") != ANYTHING_ELSE_SLOT]
    last = previous.get("last_question") or {}
    if last.get("q") and is_answer(said):
        if ANYTHING_ELSE.search(str(last["q"])):
            # only a skip ("ok", "hmm") closes it; anything else they say answers it for real
            if (
                SKIP_ACK.match(" ".join((said or "").split()))
                or SKIP_ACK_OTHER.match(" ".join((said or "").split()))
            ) and not any(c.get("slot") == ANYTHING_ELSE_SLOT for c in closed):
                closed.append({"slot": ANYTHING_ELSE_SLOT, "q": str(last["q"])})
        else:
            known = any(
                (c.get("slot") and c["slot"] == last.get("slot"))
                or same_question(c["q"], last["q"])
                for c in closed
            )
            if not known:
                closed.append({"slot": str(last.get("slot") or ""), "q": str(last["q"])})
    question = question_of(reply)
    opened = {"slot": slot.strip()[:60], "q": question} if question else {}
    return closed[-KEEP:], opened


def asked_again(slot: str, reply: str, closed: list[dict[str, Any]]) -> str | None:
    """The closed question this reply asks again (same slot name, or the same question), if any."""
    question = question_of(reply)
    if not question:
        return None
    key = slot.strip()
    if ANYTHING_ELSE.search(question) or key == ANYTHING_ELSE_SLOT:
        skipped = next((c for c in closed or [] if c.get("slot") == ANYTHING_ELSE_SLOT), None)
        if skipped is not None:
            return str(skipped.get("q") or "anything else?")
    for entry in closed or []:
        if key and entry.get("slot") == key:
            return str(entry.get("q") or key)
        if same_question(str(entry.get("q") or ""), question):
            return str(entry["q"])
    return None
