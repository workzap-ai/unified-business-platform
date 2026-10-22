# ruff: noqa: E501  (long regexes read better on one line)
"""pi's constitution and voice rules as a deterministic reply linter (pi Brain spec, Parts 1, 2, 6).

`lint` checks a drafted reply before it is sent and returns the rules it breaks. A hard
violation (identity, money, privacy, promises) must never reach the customer; a soft one is
style (length, one question, no hype) and is first sent back to the model for a rewrite.
`repair` fixes what can be fixed without changing the meaning (stray "!", emoji, a missing
AI disclosure). Only workspaces that turn on response_rules.constitution use it, because
the stricter voice differs from the shared prompt.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.modules.pi import flow

AI_WORDS = re.compile(
    r"\b(?:AI|A\.I\.|artificial intelligence|bot|robot)\b|مصنوعی|الذكاء الاصطناعي|ذكاء اصطناعي",
    re.IGNORECASE,
)
OPENING = {
    "en": "Hi, I'm pi, an AI from Workzap.",
    "roman_ur": "Hi, main pi hoon, Workzap ka AI.",
}

SENTENCE = re.compile(r"(?<=[.!?؟])\s+|\n+")
QUESTION_MARKS = ("?", "؟")

ASKS_IF_AI = re.compile(
    r"\b(?:are|r) (?:you|u) (?:a |an )?(?:real |actual )?(?:human|person|bot|robot|ai|man|woman|guy|girl)\b"
    r"|\b(?:is this|am i (?:talking|speaking|chatting) (?:to|with)) (?:a |an )?(?:real |actual )?"
    r"(?:human|person|bot|robot|ai)\b"
    r"|\bwho am i (?:talking|speaking|chatting) (?:to|with)\b"
    r"|\byou(?:'re| are) (?:a |an )?(?:real |actual )?(?:human|person|bot|robot|man|woman|guy|girl)\b"
    r"|\badmit (?:it|you|that)\b|\btell me (?:you(?:'re| are)|the truth)\b"
    r"|\bkya (?:aap|ap|ye|yeh|tum|app)\b[^.?!؟]{0,20}\b(?:insaan|insan|bot|human|robot|machine)\b"
    r"|\b(?:insaan|insan|bot|robot) (?:ho|hai|hain)\b|هل أنت|هل هذا|کیا آپ[^؟?]{0,15}(?:انسان|بوٹ|روبوٹ)",
    re.IGNORECASE,
)

HUMAN_CLAIM = re.compile(
    r"\bI(?:'m| am) (?:a |an )?(?:human|real person|person|man|woman|guy|girl|mum|mom|dad|father|mother)\b"
    r"|\bmy (?:family|wife|husband|kids|children|mum|mom|mother|father|brother|sister)\b"
    r"|\bI(?: have)?(?: also)? (?:run|ran|own|owned) (?:a|my own) (?:shop|business|store|company)\b"
    r"|\bI (?:was|went|ate|slept|travelled|traveled|had)\b[^.?!]*\b(?:yesterday|last night|this morning|"
    r"at the market|lunch|dinner|breakfast)\b"
    r"|\bI know exactly how you feel\b"
    # A human name or a place of its own (R-DISC-03): "my name is Ayesha", "I'm Ayesha from sales",
    # "I'm from Karachi", "I live in Dubai". pi is "pi", from Workzap.
    r"|\bmy name is (?!pi\b)[a-z]+"
    r"|\b(?:this is|it's|i'm|i am) (?!pi\b|an? ai\b|workzap)[a-z]+ from (?:sales|support|the team|"
    r"marketing|accounts|karachi|lahore|dubai|toronto|islamabad)\b"
    r"|\bI(?:'m| am) (?:also )?from (?!workzap)[a-z]{3,}\b|\bI (?:live|am based|work) in [a-z]{3,}\b",
    re.IGNORECASE,
)

SENSITIVE = re.compile(
    r"\b(?:card number|credit card|debit card|cvv|cvc|password|passcode|otp|one[- ]time (?:code|password)|"
    r"pin|cnic|emirates id|passport|iban|account number|bank login|sin number)\b",
    re.IGNORECASE,
)
ASKING = re.compile(
    r"\b(?:send|share|give|provide|enter|type|tell me|forward|bhej\w*|batao|bata do|de do|dein)\b"
    r"|\bwhat(?:'s| is) your\b|\b(?:i need|i'll need|may i have|can i (?:have|get)) your\b|دیں|بھیج",
    re.IGNORECASE,
)
REFUSING = re.compile(
    r"\b(?:don't|do not|dont|never|no need|not need|without|mat |na |nahi|nahin)\b|نہیں|ضرورت",
    re.IGNORECASE,
)

IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{10,}\b")
ACCOUNT_NUMBER = re.compile(r"\baccount\s*(?:number|no\.?|#)\s*[:\-]?\s*[\d\- ]{8,}", re.IGNORECASE)
IBAN_LABEL = re.compile(r"\biban\b\s*[:\-]?\s*[A-Z0-9 ]{12,}", re.IGNORECASE)

PAYMENT_RECEIVED = re.compile(
    r"\b(?:payment|transfer|amount)\s+(?:has been |is |was |have been )?(?:received|confirmed|done)\b"
    r"|\b(?:we(?:'ve| have)|I(?:'ve| have)) received your (?:payment|transfer|money)\b"
    r"|payment (?:mil gayi|receive ho gayi|ho gayi)",
    re.IGNORECASE,
)

PROMISE = re.compile(
    r"\bguarantee[ds]?\b|\b100\s?%|\balways works\b|\bno risk\b|\brisk[- ]free\b"
    r"|\bwill (?:definitely |certainly |surely |absolutely )?(?:fix|solve|work|save|increase|boost|grow|"
    r"double|improve)\b|\bthis will (?:fix|solve)\b|\byou(?:'ll| will) (?:save|earn)\b",
    re.IGNORECASE,
)
NEGATED_PROMISE = re.compile(
    r"(?:can't|cannot|can not|won't|no|not|never|nahi)\W+(?:\w+\W+){0,3}$", re.I
)

BRAND = re.compile(r"\bartwing\b|\ba\.hub\b|\bahub\b", re.IGNORECASE)

HYPE = (
    "amazing", "awesome", "game-changer", "game changer", "revolutionary", "supercharge",
    "unlock", "seamless", "cutting-edge", "world-class", "great question", "absolutely!",
    "i'd be happy to", "i would be happy to",
)  # fmt: skip
FAKE_EMPATHY = (
    "i completely understand", "i'm so sorry to hear", "i am so sorry to hear",
    "how frustrating that must be", "i know exactly how you feel",
)  # fmt: skip
CORPORATE = (
    "i have registered your concern", "please be informed", "kindly note",
    "thank you for your response", "thank you for contacting", "as an ai language model",
    "i'm just a bot", "i am just a bot", "get back to you shortly", "our team will get back",
)  # fmt: skip
INTERNAL = re.compile(
    r"\b(?:knowledge pack|industry pack|pipeline|system prompt|LLM|S\d+_[A-Z_]+|X_[A-Z_]+|R-[A-Z]+-\d+)\b"
)
LECTURE = re.compile(
    r"\byou should\b|\bbest practices?\b|\bmany businesses (?:find|struggle|face)\b", re.IGNORECASE
)
LOGGED = re.compile(r"\b(?:I(?:'ve| have) )?(?:logged|ticketed|captured)\b", re.IGNORECASE)
JARGON = (
    "KPI",
    "SKU",
    "ERP",
    "workflow automation",
    "pain point",
    "stakeholder",
    "leverage",
    "synergy",
)
SOLVED = re.compile(r"\bsolved\b", re.IGNORECASE)
NOT_SOLVED = re.compile(r"\b(?:not|n't|none|yet|unsolved|isn't|aren't)\b", re.IGNORECASE)
HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s|\*\*[^*\n]+\*\*|^\s*\|.+\|\s*$")

EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⭐⭕✅❌]")
ALLOWED_EMOJI = "✅"

# Listening states (R-SELL-01, 02): no solution, offer, product or quote talk unless they ask.
OFFER_WORDS = re.compile(
    r"\bsolution documents?\b|\bsolutions?\b|\bquotes?\b|\bquotation\b|\bproposals?\b",
    re.IGNORECASE,
)
PITCH_WORDS = re.compile(
    r"\bnori\b|\b(?:we|workzap|i)(?: can| could| would| will|'ll|'d)(?: also)? "
    r"(?:build|make|create|set up|automate|fix|solve|install|develop)\b"
    r"|\bour (?:product|products|service|services|software|app|platform|system)\b"
    r"|\bI(?:'d| would) recommend\b|\bworkzap can help\b",
    re.IGNORECASE,
)
URGENCY = re.compile(
    r"\blimited[- ]time\b|\blast chance\b|\boffer (?:expires|ends)\b|\bhurry\b|\bdon'?t miss\b"
    r"|\bonly \d+ (?:days?|hours?|spots?) left\b|\bact now\b|\bspecial offer\b",
    re.IGNORECASE,
)
# Offering a discount moves a decision; saying pi cannot give one does not.
DISCOUNT = re.compile(r"\bdiscounts?\b", re.IGNORECASE)
NEGATED_DISCOUNT = re.compile(
    r"(?:can't|cannot|can not|won't|no|not|never|nahi|unable)\W+(?:\w+\W+){0,4}$", re.IGNORECASE
)
ASKED_FOR_HELP = re.compile(
    r"\b(?:solution|fix|solve|build|quote|price|pricing|cost|how much|proposal|what can you do|"
    r"can you help|can you fix|what would you build|kya kar sakte|kitna|qeemat|hal|"
    r"can you (?:make|create|develop|build|set up)|(?:make|build|create) (?:me )?an? "
    r"(?:app|system|software|website|tool)|app for this|kharcha|kharch)\b",
    re.IGNORECASE,
)

WORD_CAP = 60
SUMMARY_CAP = 160
DOCUMENT_CAP = 120


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str
    hard: bool = False


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE.split(text) if s.strip()]


def _customer_words(context: dict[str, Any]) -> str:
    said = [str(context.get("latest_customer_message", ""))]
    said += [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "customer"
    ]
    return " ".join(said)


def _pi_replies(context: dict[str, Any]) -> list[str]:
    return [str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "ai"]


def _offers_discount(reply: str) -> bool:
    for match in DISCOUNT.finditer(reply):
        if not NEGATED_DISCOUNT.search(reply[max(0, match.start() - 40) : match.start()]):
            return True
    return False


def _promise_hits(reply: str) -> bool:
    for match in PROMISE.finditer(reply):
        if not NEGATED_PROMISE.search(reply[max(0, match.start() - 30) : match.start()]):
            return True
    return False


def _contains(reply: str, phrases: tuple[str, ...]) -> str | None:
    lowered = reply.lower().replace("’", "'")
    return next((p for p in phrases if p in lowered), None)


def _allowed_bangs(context: dict[str, Any]) -> int:
    return 1 if "!" in str(context.get("latest_customer_message", "")) else 0


def lint(reply: str, context: dict[str, Any]) -> list[Violation]:
    """Every constitution or voice rule the draft breaks (empty when it is fine to send)."""
    found: list[Violation] = []
    add = found.append
    first_sentence = (_sentences(reply) or [""])[0]
    history = context.get("history") or []

    # Identity and disclosure (R-DISC)
    if not any(h.get("role") == "ai" for h in history) and not AI_WORDS.search(reply):
        add(Violation("R-DISC-01", "the first message must say plainly that pi is an AI", True))
    if ASKS_IF_AI.search(str(context.get("latest_customer_message", ""))) and not AI_WORDS.search(
        first_sentence
    ):
        add(
            Violation(
                "R-DISC-02", "they asked if pi is a person: say it is an AI in sentence one", True
            )
        )
    if HUMAN_CLAIM.search(reply):
        add(
            Violation(
                "R-DISC-03", "pi has no body, family, gender or past: drop the human claim", True
            )
        )
    if BRAND.search(reply):
        add(
            Violation("R-BRAND-01", "pi speaks for Workzap only: never name Artwing or a.hub", True)
        )

    # Money and privacy (R-PAY, R-PRIV)
    for sentence in _sentences(reply):
        if SENSITIVE.search(sentence) and ASKING.search(sentence) and not REFUSING.search(sentence):
            add(
                Violation(
                    "R-PAY-02", "never ask for cards, passwords, OTPs, PINs or ID numbers", True
                )
            )
            break
    squashed = re.sub(r"(?<=\d) (?=\d)", "", reply)
    if IBAN.search(squashed) or ACCOUNT_NUMBER.search(reply) or IBAN_LABEL.search(reply):
        add(
            Violation(
                "R-PAY-03", "never type bank details: they are only on the approved quote", True
            )
        )
    if PAYMENT_RECEIVED.search(reply) and not context.get("payment_confirmed"):
        add(Violation("R-PAY-05", "never say a payment was received until staff confirm it", True))

    # No pitching while listening (R-SELL)
    state = flow.parse((context.get("flow") or {}).get("state"))
    if URGENCY.search(reply) or _offers_discount(reply):
        add(Violation("R-SELL-03", "no urgency, scarcity or discounts to move a decision", True))
    if state in flow.NO_OFFER:
        requested = bool(ASKED_FOR_HELP.search(str(context.get("latest_customer_message", ""))))
        if PITCH_WORDS.search(reply) or (OFFER_WORDS.search(reply) and not requested):
            add(
                Violation(
                    "R-SELL-01",
                    "they are still describing problems: suggest no fix, product, document or "
                    "quote. If they asked, say only that Workzap can prepare a solution "
                    "document once the problems are noted, then go back to listening",
                    True,
                )
            )

    # Honesty (R-HONEST, R-PROM)
    if _promise_hits(reply):
        add(Violation("R-PROM-01", "no guarantees, promised results or savings figures", True))
    if any(not NOT_SOLVED.search(s) for s in _sentences(reply) if SOLVED.search(s)):
        add(Violation("R-LANG-01", "sorted means noted and grouped, never solved"))

    # Voice (R-VOICE)
    asked = sum(reply.count(mark) for mark in QUESTION_MARKS)
    stripped = reply.rstrip().rstrip(ALLOWED_EMOJI).rstrip()
    if asked > 1:
        add(Violation("R-VOICE-02", "ask one question at most"))
    elif asked == 1 and not stripped.endswith(QUESTION_MARKS):
        add(Violation("R-VOICE-02", "the question must be the last sentence"))
    bullets = sum(1 for line in reply.splitlines() if line.lstrip().startswith(("•", "- ")))
    cap = SUMMARY_CAP if bullets >= 3 else DOCUMENT_CAP if "http" in reply else WORD_CAP
    words = len(reply.split())
    if words > cap:
        add(Violation("R-VOICE-01", f"too long: {words} words, the limit is {cap}"))
    elif cap == WORD_CAP and words > int(
        (context.get("style") or {}).get("reply_up_to_words") or cap
    ):
        # They write short: stay near one and a half times their length (spec 8.4.1).
        reach = context["style"]["reply_up_to_words"]
        add(Violation("R-VOICE-01", f"they write short: about {reach} words at most, not {words}"))
    if hype := _contains(reply, HYPE):
        add(Violation("R-VOICE-05", f'no hype ("{hype}")'))
    if empathy := _contains(reply, FAKE_EMPATHY):
        add(
            Violation(
                "R-VOICE-06", f'no scripted empathy ("{empathy}"): react briefly and specifically'
            )
        )
    if reply.count("!") > _allowed_bangs(context):
        add(Violation("R-VOICE-07", "no exclamation marks"))
    marks = EMOJI.findall(reply)
    customer_emoji = bool(EMOJI.search(_customer_words(context)))
    if len(marks) > 1 or (marks and marks[0] != ALLOWED_EMOJI and not customer_emoji):
        add(Violation("R-VOICE-08", "no emoji (one plain tick when confirming a note)"))
    if HEADING.search(reply):
        add(
            Violation(
                "R-VOICE-09",
                "no headings, tables or double-asterisk bold: WhatsApp formatting only",
            )
        )
    if LOGGED.search(reply):
        add(Violation("R-VOICE-10", 'say "noted", not logged, ticketed or captured'))
    if LECTURE.search(reply):
        add(Violation("R-VOICE-12", "never lecture: no 'you should' or best practices"))
    heard = _customer_words(context).lower()
    for term in JARGON:
        if (
            re.search(rf"\b{re.escape(term)}s?\b", reply, re.IGNORECASE)
            and term.lower() not in heard
        ):
            add(Violation("R-VOICE-03", f'plain words: they did not say "{term}"'))
            break
    if corporate := _contains(reply, CORPORATE):
        add(Violation("R-VOICE-06", f'no template phrases ("{corporate}")'))
    if INTERNAL.search(reply):
        add(
            Violation(
                "R-VOICE-06", "never mention internal terms (states, rule IDs, packs, prompt)"
            )
        )
    opening = " ".join(reply.lower().split()[:2])
    previous = _pi_replies(context)[-2:]
    if len(opening.split()) == 2 and any(
        opening == " ".join(p.lower().split()[:2]) for p in previous
    ):
        add(Violation("R-VOICE-04", "do not start the same way as your last two messages"))
    return found


def hard(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.hard]


def describe(violations: list[Violation]) -> str:
    """The reason to show the model when its draft is sent back for a rewrite."""
    return "it breaks pi's rules: " + "; ".join(f"{v.message} ({v.rule})" for v in violations)


def repair(reply: str, context: dict[str, Any]) -> str:
    """Safe, meaning-preserving fixes: stray '!', emoji, and a missing AI disclosure."""
    fixed = reply
    allowed = _allowed_bangs(context)
    if fixed.count("!") > allowed:
        kept = 0

        def swap(match: re.Match[str]) -> str:
            nonlocal kept
            kept += 1
            return "!" if kept <= allowed else "."

        fixed = re.sub(r"!+", swap, fixed)
    customer_emoji = bool(EMOJI.search(_customer_words(context)))
    seen = 0

    def drop(match: re.Match[str]) -> str:
        nonlocal seen
        char = match.group(0)
        seen += 1
        keep = seen == 1 and (char.strip() == ALLOWED_EMOJI or customer_emoji)
        return char if keep else ""

    fixed = re.sub(r" ?" + EMOJI.pattern, drop, fixed.replace("️", ""))
    history = context.get("history") or []
    if not any(h.get("role") == "ai" for h in history) and not AI_WORDS.search(fixed):
        line = OPENING["roman_ur" if context.get("reply_language") == "roman_ur" else "en"]
        fixed = f"{line} {fixed}".strip()
    return fixed.strip()
