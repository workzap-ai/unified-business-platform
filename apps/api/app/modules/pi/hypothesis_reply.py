# ruff: noqa: E501
"""What the owner's reply does to the question pi just asked (Engagement Engine, Book 5, Part 3.5).

Pure functions, no model and no database. Two uses:

* `landed(asked, said)`: did the owner's reply take up pi's last message (True), or was it a
  deflection or an "ok" (False)? It is the `landed` of `moves.Turn`, which the variety rule "a move
  that did not land is not repeated" reads.
* `judge(said, hypothesis, ...)`: what the reply does to a hypothesis pi put to the owner: it adds
  evidence for it, evidence against it, leaves it unanswered ("ignored"), or the owner plainly says
  yes to "is that the reason?" ("confirm"). Only an explicit owner yes confirms; a reply that merely
  supports the cause adds evidence and never confirms (`HypothesisLedger.confirm(by="owner")` is the
  only way to the confirmed state).
"""

import re
from typing import Literal

from app.modules.pi import solution_ask

Verdict = Literal["confirm", "for", "against", "ignored", "none"]

QUESTION_MARKS = ("?", "؟")
MIN_SHARED = 2  # content words a reply must share with the hypothesis to count as about it
SHORT_ASK_WORDS = (
    6  # "solution do", "kuch karo": a bare request that leaves the question unanswered
)

# "ok", "hmm", "theek hai": the owner heard it and gave nothing back.
ACK_ONLY = re.compile(
    r"^\W*(?:ok(?:ay)?|k|hmm+|hm+|acha|accha|achha|theek(?: hai| he)?|thik(?: hai| he)?|haan ji|han ji|ji|jee|"
    r"alright|fine|sure|chalo|اوکے|ٹھیک ہے|اچھا|حسنا|تمام|طيب|\U0001f44d|\U0001f64f)\W*$",
    re.IGNORECASE,
)
# "I do not know", "leave it", "later": the question was not answered.
NOT_ANSWERED = re.compile(
    r"\b(?:pata nahi|pata nhi|nahi pata|nhi pata|maloom nahi|malum nahi|don'?t know|do not know|no idea|not sure|"
    r"chhodo|chorro|choro|rehne do|rehnay do|baad mein|baad me|later|skip|chalo chhodo|kuch nahi pata|idk)\b"
    r"|پتا نہیں|معلوم نہیں|لا أعرف|ما أدري|पता नहीं",
    re.IGNORECASE,
)
YES_WORDS = re.compile(
    r"^\W*(?:haan|han|haa|ji haan|ji han|jee haan|yes|yeah|yep|yup|bilkul|sahi|sahi hai|sahi kaha|exactly|correct|"
    r"(?:that'?s|it'?s|you'?re) (?:right|true|correct)|theek kaha|ji bilkul|ji sahi|"
    r"جی ہاں|ہاں|جی بالکل|بالکل|نعم|صح|صحيح|हाँ|हां|बिल्कुल)\b",
    re.IGNORECASE,
)
CONFIRM_MAX_WORDS = 10
ANY_NEGATION = re.compile(
    r"\b(?:nahi|nahin|nhi|no|not|never|wrong|galat|ghalat)\b|نہیں|نہی|غلط|لا |नहीं|गलत",
    re.IGNORECASE,
)
BUT = re.compile(r"\b(?:but|lekin|magar|par|however|though|halanke)\b|لیکن|مگر|لكن", re.IGNORECASE)
NO_WORDS = re.compile(
    r"^\W*(?:nahi|nahin|nhi|no|nope|galat|ghalat|bilkul nahi|aisa nahi|ye nahi|yeh nahi|wajah nahi|not really|wrong|"
    r"نہیں|نہی|غلط|لا|نه|नहीं|गलत)\b"
    r"|\b(?:wajah|waja|reason|sabab) (?:nahi|nhi|not)\b|\bnot (?:the )?(?:reason|cause|why)\b|\baisa (?:nahi|nhi) hai\b",
    re.IGNORECASE,
)


def stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[^\W\d_]{4,}", (text or "").lower())}


def is_question(text: str) -> bool:
    return (text or "").rstrip().endswith(QUESTION_MARKS)


def asks_back(said: str) -> bool:
    """The reply is a question or a request of its own ("solution do", "kitna lagega?")."""
    return is_question(said) or solution_ask.asked_for_ideas(said)


def deflected(said: str) -> bool:
    """An acknowledgement with nothing in it, "I do not know", or a request that ignores the
    question: the owner did not answer."""
    text = " ".join((said or "").split())
    if not text:
        return True
    if ACK_ONLY.match(text) or (len(text.split()) <= 6 and NOT_ANSWERED.search(text)):
        return True
    return solution_ask.asked_for_ideas(text) and len(text.split()) <= SHORT_ASK_WORDS


def substantive(said: str) -> bool:
    """The reply gives a fact (an answer, even one word: "cash"), not an "ok" or "I do not know"."""
    return not deflected(said)


def landed(asked: str, said: str) -> bool | None:
    """Did the owner's reply take up pi's message? None: nothing was asked or there is no reply."""
    if not is_question(asked) or not (said or "").strip():
        return None
    return not deflected(said)


def judge(said: str, hypothesis: str, *, put_to_owner: bool) -> Verdict:
    """What `said` does to one hypothesis. `put_to_owner`: pi's last message put this hypothesis to
    the owner as a question. A yes confirms only then, and only when it is a plain yes."""
    text = " ".join((said or "").split())
    if not text:
        return "ignored" if put_to_owner else "none"
    if deflected(text):
        return "ignored" if put_to_owner else "none"
    shared = len(stems(text) & stems(hypothesis))
    if NO_WORDS.search(text) and (put_to_owner or shared >= MIN_SHARED):
        return "against"
    if (
        put_to_owner
        and len(text.split()) <= CONFIRM_MAX_WORDS  # "right now customers leave" is not a yes
        and YES_WORDS.match(text)
        and not BUT.search(text)
        and not NO_WORDS.search(text)
        and not ANY_NEGATION.search(text)  # "sahi nahi hai" says no
    ):
        return "confirm"
    if shared >= MIN_SHARED:
        return "for"
    if put_to_owner and shared == 0 and asks_back(text):
        return "ignored"  # it asked something else instead of answering
    return "none"
