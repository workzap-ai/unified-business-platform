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
from typing import Any

from app.modules.pi import industry_packs

KEEP = 24  # closed slots kept per conversation
SAME = 0.6  # share of shared content words that makes two questions the same slot
MIN_WORDS = 3  # a question with fewer content words is too thin to compare
QUESTION_END = ("?", "؟")
STOP = frozenset(
    "the and for with from are was were been our your this that they them their have has had does"
    " did not can could would should will just very but about into than then there here what"
    " which who how when where why all any some more most much many also only own such ke ki ka"
    " ko se mein hai hain hua hui aur ya ye wo bhi nahi nhi koi kuch sab har par kar kya aap ap"
    " apne apka apki kis kaun kitna kitni kitne".split()
)


def question_of(reply: str) -> str:
    """The last question in the reply, "" when it asks none."""
    for sentence in reversed(re.split(r"(?<=[.!?؟])\s+|\n+", reply.strip())):
        sentence = sentence.strip()
        if sentence.endswith(QUESTION_END):
            return sentence[:160]
    return ""


def words(question: str) -> frozenset[str]:
    found = re.findall(r"[a-z]{3,}", industry_packs._fold(question))
    return frozenset(industry_packs._stem(w) for w in found if w not in STOP)


def same_question(a: str, b: str) -> bool:
    left, right = words(a), words(b)
    if len(left) < MIN_WORDS or len(right) < MIN_WORDS:
        return False
    return len(left & right) / len(left | right) >= SAME


def is_answer(said: str) -> bool:
    """Anything the person says closes the last question, unless it is only a request that pi
    answer something else first (a solution ask, a document ask) or too empty to be an answer."""
    from app.modules.pi import solution_ask

    text = " ".join((said or "").split())
    if not any(ch.isalnum() for ch in text):
        return bool(text)  # a thumbs-up or a number is an answer
    return not solution_ask.asked_for_ideas(text)


def advance(
    previous: dict[str, Any], said: str, reply: str, slot: str
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """(closed slots, the question now open) after a turn: the question asked last turn closes when
    the person answered it, and the question in this reply becomes the open one."""
    closed = [dict(c) for c in previous.get("closed_slots") or []]
    last = previous.get("last_question") or {}
    if last.get("q") and is_answer(said):
        known = any(
            (c.get("slot") and c["slot"] == last.get("slot")) or same_question(c["q"], last["q"])
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
    for entry in closed or []:
        if key and entry.get("slot") == key:
            return str(entry.get("q") or key)
        if same_question(str(entry.get("q") or ""), question):
            return str(entry["q"])
    return None
