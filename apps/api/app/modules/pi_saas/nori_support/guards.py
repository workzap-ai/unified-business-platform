"""Checks a support reply must pass before it is sent. Deterministic; the model is never trusted.

A reply that fails any check is dropped and the person gets the plain acknowledgement instead (the
card is filed either way). The checks are the CLAUDE.md non-negotiables that apply to a support
reply: pi says it is an AI, at most one question and it is last, no payment or secrets, no claim
that a payment arrived, no advice, no invented figure, no promise of timing, no foreign link.
Nothing here is learnable.
"""

import re

from app.modules.pi.language import notice_in
from app.modules.pi_saas.nori_credits.resilience import METRICS
from app.modules.pi_saas.nori_credits.send_door import foreign_urls

MAX_REPLY = 700
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")
_NUMBER = re.compile(r"\d[\d,.]*")
_MONTH = re.compile(
    # "may" is left out: far more often the verb than the month, and a date still needs digits.
    r"\b(january|february|march|april|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
# Asking for, or taking, what pi never handles in a chat (rule: no payment in chat).
_SECRETS = re.compile(
    r"\b(?:(?:credit |debit )?cards?(?: numbers?| details?)?|cvv|cvc|otps?|pins?|passcodes?|"
    r"one[- ]time (?:codes?|passwords?)|verification codes?|passwords?|cnic|national id|"
    r"id card|passport|iban|account (?:no|numbers?)|bank (?:details?|transfers?|accounts?)|"
    r"jazz ?cash|easy ?paisa|wallets?|send (?:the )?(?:money|payment)|pay me|transfer to|"
    r"code bhej\w*|password bata\w*)\b|پاسورڈ|کارڈ",
    re.IGNORECASE,
)
# pi never says a payment arrived or that credits were added: only staff confirm that.
_PAID = re.compile(
    r"\b(?:payment|paisa|paise|amount|transfer)\b[^.?!]{0,40}\b(?:received|mil gay\w*|"
    r"confirmed|successful|done|hogay\w*|mausool)\b|\bcredits? (?:are |were |have been )?added\b",
    re.IGNORECASE,
)
# A promise of timing, or a sales push: pi notes a request, it never commits or upsells.
_PROMISE = re.compile(
    r"\b(?:tomorrow|soon|shortly|within|right away|immediately|kal tak|jald\w*|upgrade|"
    r"i recommend|best plan|by (?:today|tonight|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)|you should (?:buy|subscribe|upgrade))\b",
    re.IGNORECASE,
)
# Words that mean legal, tax, medical or financial advice. A support reply has no use for them.
_ADVICE_WORDS = re.compile(
    r"\b(?:tax(?:es|ation)?|legal(?:ly)?|lawyer|lawsuit|court|medical|medicine|diagnos\w*|"
    r"dosage|invest(?:ment|ing)?|loans?|insurance)\b|ٹیکس|قانونی",
    re.IGNORECASE,
)
_AI = re.compile(r"\bAI\b")
_PI = re.compile(r"\bpi\b", re.IGNORECASE)
_SENTENCE = re.compile(r"[.!?؟۔\n]")

DISCLOSURE = {
    "en": "I'm pi, an AI assistant.",
    "roman_ur": "Main pi hoon, ek AI assistant.",
    "ur": "میں pi ہوں، ایک AI اسسٹنٹ۔",
}


def _digits(text: str) -> set[str]:
    """Every number written in the text, without separators."""
    found = set()
    for item in _NUMBER.findall(text):
        plain = re.sub(r"[,.]", "", item)
        if plain:
            found.add(plain)
    return found


def _questions(reply: str) -> int:
    return reply.count("?") + reply.count("؟")


def _with_disclosure(text: str, language: str | None, needed: bool) -> str:
    """The first sentence says pi is an AI (R-DISC-01/02): put in front when it does not."""
    if not needed:
        return text
    first = _SENTENCE.split(text, maxsplit=1)[0]
    said = _AI.search(first) and _PI.search(first)
    return text if said else f"{notice_in(DISCLOSURE, language)} {text}"


def vet(
    reply: str | None,
    *,
    facts_text: str,
    person_text: str,
    nori_host: str,
    language: str | None,
    first_reply: bool,
    fixed: bool = False,
) -> str | None:
    """The reply ready to send, or None when it must not be sent.

    `fixed` marks a line pi wrote itself (a safety notice): only the disclosure rule applies, so a
    warning about card details is kept. `person_text` is used for months and nothing else: a digit
    the person typed is never a licence to repeat it as a fact."""
    if not isinstance(reply, str):
        return None
    text = _CONTROL.sub("", reply).strip()
    if not text:
        return None
    if fixed:
        return _with_disclosure(text, language, first_reply)
    if len(text) > MAX_REPLY:
        METRICS.inc("support", "too_long")
        return None
    if _SECRETS.search(text) or _PAID.search(text):
        METRICS.inc("support", "secrets")
        return None
    if _PROMISE.search(text):
        METRICS.inc("support", "promise")
        return None
    from app.modules.pi import safety

    if safety.advice_asked(text) is not None or _ADVICE_WORDS.search(text):
        METRICS.inc("support", "advice")
        return None
    if foreign_urls(text, nori_host):
        METRICS.inc("support", "foreign_link")
        return None
    if _digits(text) - _digits(facts_text):
        METRICS.inc("support", "ungrounded_number")
        return None
    months = {m.lower() for m in _MONTH.findall(text)}
    known = {m.lower() for m in _MONTH.findall(facts_text + " " + person_text)}
    if months - known:
        METRICS.inc("support", "ungrounded_date")
        return None
    asked = _questions(text)
    if asked > 1 or (asked == 1 and not text.endswith(("?", "؟"))):
        METRICS.inc("support", "question_rule")
        return None
    return _with_disclosure(text, language, first_reply)
