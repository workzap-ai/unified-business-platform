# ruff: noqa: E501  (word lists and patterns read better on one line)
"""The thinking checks of the linter (Engagement Engine, Book 5, spec 3.9).

Seven soft flags, pure functions of a drafted reply and the conversation context:

  Q-streak       two of the last three messages ended in a question and gave nothing new
  Move repeat    the same move appears three times in four messages
  No-insight     no reflection, number, link, fork or idea
  Echo           the first sentence overlaps the owner's last message
  Filler         a banned filler question outside a check-in
  Unproved claim a hypothesis stated as a fact
  Forecast       a number about the future that the owner did not give

They are SOFT: `constitution.lint` adds them only behind `response_rules.brain.thinking` (context key
`thinking`), and a soft flag sends the draft back for a rewrite; it never blocks a reply on its own.
They sit beside the hard rules and never replace them.
"""

import itertools
import re
from dataclasses import dataclass
from typing import Any

SENTENCE = re.compile(r"(?<=[.!?؟۔।])\s+|\n+")
QUESTION_END = re.compile(r"[?؟]\s*[\"'”’)]*\s*$")
WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?", re.UNICODE)
LINK = re.compile(r"https?://|www\.", re.IGNORECASE)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

MIN_STATEMENT_WORDS = 5  # a statement shorter than this adds nothing ("Theek hai.", "Samajh aaya.")
ECHO_SHARE = 0.7  # the share of the first sentence's words that are the owner's
ECHO_MIN_WORDS = 4
WINDOW = 4
REPEAT_LIMIT = 3


@dataclass(frozen=True)
class Flag:
    rule: str
    message: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text or "") if s.strip()]


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall((text or "").replace("’", "'"))]


def ends_in_question(text: str) -> bool:
    return bool(QUESTION_END.search((text or "").strip()))


def _pi_turns(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [h for h in context.get("history") or [] if h.get("role") == "ai"]


def _customer_texts(context: dict[str, Any]) -> list[str]:
    said = [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "customer"
    ]
    latest = context.get("latest_customer_message")
    if latest:
        said.append(str(latest))
    return said


# --- what counts as giving something -------------------------------------------------------

ACK_LEAD = re.compile(
    r"^\W*(?:theek\s+hai|thik\s+hai|acha|accha|achha|ok|okay|sure|got it|i see|samajh\s+aaya|"
    r"bilkul|shukriya|thanks|thank you|alright)\b\W*",
    re.IGNORECASE,
)
FORK = re.compile(r"\b(?:ya|ya phir|or|ou|o|یا|या|أو|oder)\b", re.IGNORECASE)
FORK_MIN_WORDS = 8


def _statement_words(sentence: str) -> int:
    return len(_words(ACK_LEAD.sub("", sentence)))


def adds_something(text: str) -> bool:
    """The message gives a reading, a number, a link, a fork or an idea, not only a question.

    A statement of five words or more counts as a reading or an idea; a figure or a link counts;
    so does a fork (one question that offers two paths, "maal se ya cash se?")."""
    if LINK.search(text or "") or NUMBER.search(text or ""):
        return True
    for s in _sentences(text):
        if ends_in_question(s):
            if FORK.search(s) and len(_words(s)) >= FORK_MIN_WORDS:
                return True
            continue
        if _statement_words(s) >= MIN_STATEMENT_WORDS:
            return True
    return False


# --- the seven checks ----------------------------------------------------------------------


def q_streak(reply: str, context: dict[str, Any]) -> Flag | None:
    """Two of the last three messages (this one and the two before) ended in a question and gave
    nothing new."""
    messages = [str(t.get("text", "")) for t in _pi_turns(context)[-2:]] + [reply]
    bare = [m for m in messages if ends_in_question(m) and not adds_something(m)]
    if len(bare) >= 2 and ends_in_question(reply) and not adds_something(reply):
        return Flag(
            "T-QSTREAK-01",
            "two of the last three messages were only a question: give something first (a reading, a number, a link, a fork or an idea)",
        )
    return None


def recent_moves(context: dict[str, Any]) -> list[str]:
    """The moves of pi's earlier messages, when the history carries them (key `move`)."""
    return [str(t["move"]) for t in _pi_turns(context) if t.get("move")]


def move_repeat(reply: str, context: dict[str, Any]) -> Flag | None:
    """The same move three times in four messages (this message's move comes from the plan)."""
    plan = context.get("plan") or {}
    current = plan.get("move") if isinstance(plan, dict) else None
    moves = recent_moves(context)[-(WINDOW - 1) :]
    if current:
        moves = [*moves, str(current)]
    else:
        moves = moves[-WINDOW:]
    for move in set(moves):
        if moves.count(move) >= REPEAT_LIMIT:
            return Flag(
                "T-REPEAT-01",
                f"the move {move} would appear {REPEAT_LIMIT} times in the last {WINDOW} messages: choose another",
            )
    return None


def no_insight(reply: str, context: dict[str, Any]) -> Flag | None:
    """No reflection, number, link, fork or idea: the owner would have nothing new. A reply that
    is only a short acknowledgement ("Theek hai.") is the application's own wording and passes."""
    if not (reply or "").strip() or adds_something(reply):
        return None
    if not ends_in_question(reply) and len(_words(reply)) <= 4:
        return None
    return Flag(
        "T-INSIGHT-01",
        "so what? the owner has nothing after this message that they did not have before: add a reading, a number, a link, a fork or an idea",
    )


def echo(reply: str, context: dict[str, Any]) -> Flag | None:
    """The first sentence mostly repeats the owner's last message."""
    latest = str(context.get("latest_customer_message") or "")
    sentences = _sentences(reply)
    if not latest or not sentences:
        return None
    first = _words(ACK_LEAD.sub("", sentences[0]))
    if len(first) < ECHO_MIN_WORDS:
        return None
    theirs = set(_words(latest))
    share = sum(1 for w in first if w in theirs) / len(first)
    if share >= ECHO_SHARE:
        return Flag(
            "T-ECHO-01",
            "the first sentence repeats what they just said: say what it means instead",
        )
    return None


BANNED_FILLERS = (
    "is anything else getting in the way",
    "anything else getting in the way",
    "anything else",
    "kuch aur",
    "aur kya masla hai",
    "aur koi masla",
    "کچھ اور",
    "اور کیا مسئلہ ہے",
)
FILLER_MAX_WORDS = 8  # a long, specific question that happens to contain the phrase is not filler


def filler(reply: str, context: dict[str, Any]) -> Flag | None:
    """A banned filler question outside a check-in. Allowed as a door after the problem is
    understood only when phrased specifically (longer, naming where the pull is)."""
    if context.get("check_in") or context.get("summary_turn"):
        return None
    for s in _sentences(reply):
        if not ends_in_question(s):
            continue
        low = " ".join(_words(s))
        if len(low.split()) <= FILLER_MAX_WORDS and any(f in low for f in BANNED_FILLERS):
            return Flag(
                "T-FILLER-01",
                'a filler question ("anything else?", "kuch aur?") adds nothing: ask something specific or give something',
            )
    return None


CAUSAL = re.compile(
    r"\b(?:the (?:reason|cause|problem|issue) is|that(?:'s| is) (?:why|because)|this is (?:why|because)|because of|caused by|due to|is the reason|"
    r"wajah(?!\s+se)|isliye|is liye|is sabab|yehi masla|asal wajah|kyunke|kyun ke|kyonki|"
    r"السبب هو|بسبب|وجہ|اسی لیے|اس لیے)\b",
    re.IGNORECASE,
)
HUMBLE = re.compile(
    r"\b(?:meri (?:ek )?soch|galat bhi ho sakti|shayad|ho sakta|ho sakti|lagta hai|lagti hai|lag raha|aksar|aam tor par|aam taur par|kabhi kabhi|"
    r"might|maybe|perhaps|could be|may be|may|i think|i wonder|my guess|my hunch|it seems|seems|looks like|often|usually|generally|tends? to|can be|"
    r"possibly|probably|sounds like|i suspect|not sure|correct me|"
    r"ممکن|شاید|لگتا ہے|اکثر|عام طور|"
    r"peut-être|peut être|sans doute|je pense|il semble|souvent|"
    r"quizá|quizás|tal vez|creo que|parece|a menudo|"
    r"شاید|به نظر می رسد|ممکن است|"
    r"ربما|قد يكون|يبدو)\b",
    re.IGNORECASE,
)
CLAIM_OVERLAP = 0.5  # a causal sentence the owner said first is theirs, not a pi hypothesis


def unproved_claim(reply: str, context: dict[str, Any]) -> Flag | None:
    """A hypothesis stated as a fact: a causal claim with no sign of humility that the owner did not
    say first. A confirmed hypothesis (context `hypothesis_confirmed`) may be stated plainly."""
    if context.get("hypothesis_confirmed"):
        return None
    theirs = set(itertools.chain.from_iterable(_words(t) for t in _customer_texts(context)))
    for s in _sentences(reply):
        if ends_in_question(s) or not CAUSAL.search(s) or HUMBLE.search(s):
            continue
        ws = _words(s)
        if ws and sum(1 for w in ws if w in theirs) / len(ws) >= CLAIM_OVERLAP:
            continue
        return Flag(
            "T-CLAIM-01",
            'a guess is stated as a fact: say it is a guess ("meri ek soch hai, galat bhi ho sakti hai") and let the owner confirm',
        )
    return None


FUTURE = re.compile(
    r"\b(?:will|would|going to|next (?:month|year|week|quarter)|by (?:the end|next)|in \d+ (?:months?|weeks?|days?|years?)|within|forecast|expect(?:ed)? to|"
    r"hoga|hogi|honge|ho jaye ga|ho jayega|ho jaye|jaye ga|jayega|aaye ga|agle|agla|agli|aane wale|mahine mein|saal mein|hafte mein)\b",
    re.IGNORECASE,
)
FUTURE_URDU = re.compile(r"(?:ہوگا|ہوگی|ہوں گے|جائے گا|جائیں گے)")
NEGLIGIBLE = {"1", "2"}  # "1 se shuru", "2 ideas": not a forecast figure
HALF = re.compile(r"\b(?:aadha|adha|half|nisf|moitié|moitie|mitad)\b|آدھا|نصف", re.IGNORECASE)
THIRD = re.compile(r"\b(?:tihai|third|tercio|tiers)\b", re.IGNORECASE)
QUARTER = re.compile(r"\b(?:chauthai|quarter|cuarto|quart)\b", re.IGNORECASE)


def _figures(text: str) -> list[float]:
    out = []
    for raw in NUMBER.findall(text or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _derivable(context: dict[str, Any]) -> set[float]:
    """Figures the owner gave, and plain arithmetic on them (sums, differences, products, ratios,
    percentages, a half, a third, a quarter, double): working their numbers is allowed (M2, M7)."""
    texts = _customer_texts(context)
    base = sorted({f for t in texts for f in _figures(t)})
    allowed = set(base)
    for a, b in itertools.permutations(base, 2):
        allowed.update({a + b, abs(a - b), a * b})
        if b:
            allowed.update({a / b, a / b * 100})
    for a in base:
        allowed.update({a * 2, a / 2, a / 3, a / 4})
    joined = " ".join(texts)
    if HALF.search(joined) or THIRD.search(joined) or QUARTER.search(joined):
        for a in base:
            allowed.update({a / 2, a / 3, a / 4})
    return {round(v, 2) for v in allowed}


def forecast(reply: str, context: dict[str, Any]) -> Flag | None:
    """A figure about the future that the owner did not give and that does not follow from theirs
    by plain arithmetic. 'Isi raftar par 3 crore aur purana ho jaye ga' (half of their 6 crore) is
    allowed; 'Aap ko 40 lakh ka nuqsan hoga' is not."""
    allowed = _derivable(context)
    for s in _sentences(reply):
        if ends_in_question(s) or not (FUTURE.search(s) or FUTURE_URDU.search(s)):
            continue
        for raw in NUMBER.findall(s):
            if raw in NEGLIGIBLE:
                continue
            try:
                value = round(float(raw.replace(",", "")), 2)
            except ValueError:
                continue
            if value not in allowed:
                return Flag(
                    "T-FORECAST-01",
                    f'never forecast a number the owner did not give ("{raw}"): say what it causes, not how much',
                )
    return None


CHECKS = (q_streak, move_repeat, no_insight, echo, filler, unproved_claim, forecast)


def think_flags(reply: str, context: dict[str, Any]) -> list[Flag]:
    """Every thinking flag the draft raises (soft: a rewrite is asked for, nothing is blocked)."""
    return [f for check in CHECKS if (f := check(reply, context)) is not None]
