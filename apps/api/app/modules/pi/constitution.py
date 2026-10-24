# ruff: noqa: E501  (long regexes read better on one line)
"""pi's constitution and voice rules as a deterministic reply linter (pi Brain spec, Parts 1, 2, 6).

`lint` checks a drafted reply before it is sent and returns the rules it breaks. A hard
violation (identity, money, privacy, promises) must never reach the customer; a soft one is
style (length, one question, no hype) and is first sent back to the model for a rewrite.
`repair` fixes what can be fixed without changing the meaning (stray "!", emoji, a missing
AI disclosure). Only workspaces that turn on response_rules.constitution use it, because
the stricter voice differs from the shared prompt.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from app.modules.pi import flow

logger = logging.getLogger(__name__)

AI_WORDS = re.compile(
    r"\b(?:AI|A\.I\.|artificial intelligence|bot|robot)\b|مصنوعی|الذكاء الاصطناعي|ذكاء اصطناعي"
    r"|[اإ]صطناعي|[اإ]صطناعى|ذكاء صناعي|ذكاء اصطناعى|اے آئی|ای آئی|एआई|कृत्रिम बुद्धिमत्ता|रोबोट|बॉट",
    re.IGNORECASE,
)
# A first message names itself: the AI word sits in a sentence that speaks about pi or "I"
# (R-DISC-01), in English, Roman Urdu, Urdu, Arabic or Hindi.
SELF_WORDS = re.compile(
    r"\bI(?:'m| am)\b|\bI\b|\bpi\b|\bmain\b|\bmai\b|\bmein\b|\bhoon\b|\bhun\b|\bhu\b|\bhai\b"
    r"|میں|ہوں|ہے|أنا|انا|إنني|معك|مساعد|मैं|हूँ|हूं",
    re.IGNORECASE,
)
OPENING = {
    "en": "Hi, I'm pi, an AI from Workzap.",
    "roman_ur": "Hi, main pi hoon, Workzap ka AI.",
    "ur": "ہیلو، میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت۔",
    "ar": "مرحباً، أنا pi، ذكاء اصطناعي من Workzap.",
}


def opening_line(context: dict[str, Any]) -> str:
    """The one-line AI disclosure in the person's language and script (R-DISC-01, R-LANG-02)."""
    from app.modules.pi.language import ARABIC_SCRIPT, URDU_LETTERS

    language = context.get("reply_language")
    said = str(context.get("latest_customer_message", ""))
    if language == "roman_ur":
        return OPENING[
            "ur" if ARABIC_SCRIPT.search(said) and URDU_LETTERS.search(said) else language
        ]
    return OPENING.get(str(language), OPENING["en"])


SENTENCE = re.compile(r"(?<=[.!?؟۔])\s+|\n+")
QUESTION_MARKS = ("?", "؟")

ASKS_IF_AI = re.compile(
    r"\b(?:are|r) (?:you|u) (?:a |an )?(?:real |actual )?(?:human|person|bot|robot|ai|man|woman|guy|girl)\b"
    r"|\b(?:is this|am i (?:talking|speaking|chatting) (?:to|with)) (?:a |an )?(?:real |actual )?"
    r"(?:human|person|bot|robot|ai)\b"
    r"|\bwho am i (?:talking|speaking|chatting) (?:to|with)\b"
    r"|\byou(?:'re| are) (?:a |an )?(?:real |actual )?(?:human|person|bot|robot|man|woman|guy|girl)\b"
    r"|\badmit (?:it|you|that)\b|\btell me (?:you(?:'re| are)|the truth)\b"
    r"|\bkya (?:aap|ap|ye|yeh|tum|app)\b[^.?!؟]{0,20}\b(?:insaan|insan|bot|human|robot|machine)\b"
    r"|\b(?:insaan|insan|bot|robot) (?:ho|hai|hain)\b|هل أنت|هل هذا|کیا آپ[^؟?]{0,15}(?:انسان|بوٹ|روبوٹ)"
    r"|هل (?:انت|أنت) (?:إنسان|انسان|بشر|روبوت|بوت)|من (?:انت|أنت)\b|\baap kon (?:ho|hain)\b"
    r"|\btum kaun ho\b|آپ کون ہیں|تم کون ہو",
    re.IGNORECASE,
)

TEAM_READS = re.compile(
    r"\b(?:team|someone|somebody|a person|a human|staff|people)\b[^.?!\n]{0,40}"
    r"\b(?:reads?|is reading|are reading|will read|reading|sees?|monitors?)\b[^.?!\n]{0,25}"
    r"\b(?:this|the|your) (?:chat|conversation|messages?)\b",
    re.IGNORECASE,
)

HUMAN_CLAIM = re.compile(
    r"\bI(?:'m| am) (?:a |an )?(?:human|real person|person|man|woman|guy|girl|mum|mom|dad|father|mother)\b"
    r"|\bmy (?:family|wife|husband|kids|children|mum|mom|mother|father|brother|sister)\b"
    r"|\bI(?:'ve| have)?(?: also)? (?:run|ran|own|owned) (?:a|my own) (?:shop|business|store|company)\b"
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
    r"pin|cnic|emirates id|passport|iban|account number|bank login|sin number)\b"
    # Arabic and Urdu script (prefixes and suffixes stick to the word, so no word boundaries).
    r"|بطاقت[كيه]|رقم البطاقة|بطاقة (?:ائتمان|الائتمان|مصرفية|بنكية|الدفع)|كلمة (?:المرور|السر)|"
    r"رمز (?:التحقق|الأمان|الامان|التفعيل)|الرقم السري|رمز (?:ال)?(?:بن|otp)|آيبان|ايبان|رقم الحساب|"
    r"كلمة المرور|الحساب البنكي|[کك]ارڈ نمبر|[کك]ریڈٹ [کك]ارڈ|ڈیبٹ [کك]ارڈ|پاس ورڈ|اوٹی پی|او ٹی پی|"
    r"پن کوڈ|اکاؤنٹ نمبر|اکاونٹ نمبر|آئی بی اے این|پاسپورٹ|شناختی [کك]ارڈ|سی این آئی سی",
    re.IGNORECASE,
)
# National ID and similar numbers (R-PRIV-03): asked for in any wording.
NATIONAL_ID = re.compile(
    r"\b(?:national id|national identity|id card|identity card|id number|id photo|photo of your id|"
    r"emirates id|iqama|aadhaar|aadhar|ssn|social security|sin|nic|ntn|driving licen[cs]e|"
    r"licen[cs]e number|tax (?:id|number)|shanakhti card|national identification)\b"
    r"|رقم الهوية|بطاقة الهوية|الهوية الوطنية|هويتك|رقم الإقامة|الرقم الوطني|قومی شناختی|شناختی نمبر",
    re.IGNORECASE,
)
ASKING = re.compile(
    r"\b(?:send|share|give|provide|enter|type|tell me|forward|bhej\w*|batao|bata do|de do|dein)\b"
    r"|\bwhat(?:'s| is) your\b|\b(?:i need|i'll need|may i have|can i (?:have|get)) your\b|دیں|بھیج"
    r"|ارسل|أرسل|ارسلي|أرسلي|شارك|أعطني|اعطني|زودني|أدخل|ادخل|اكتب|أخبرني|اخبرني|أحتاج|احتاج|أريد|اريد"
    r"|ما هو رقم|ما هي|بتائیں|بتائیے|شیئر|دیجیے|دیجئے|درکار|لکھیں|ٹائپ|مجھے چاہیے",
    re.IGNORECASE,
)
REFUSING = re.compile(
    r"\b(?:don't|do not|dont|never|no need|not need|without|mat |na |nahi|nahin)\b|نہیں|ضرورت"
    r"|لا ترسل|لا تشارك|لا تعطني|لا داعي|لا تحتاج|لا أحتاج|لا احتاج|لا أطلب|لا اطلب|بدون|مت |نہ ",
    re.IGNORECASE,
)

IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{10,}\b")
ACCOUNT_NUMBER = re.compile(r"\baccount\s*(?:number|no\.?|#)\s*[:\-]?\s*[\d\- ]{8,}", re.IGNORECASE)
IBAN_LABEL = re.compile(r"\biban\b\s*[:\-]?\s*[A-Z0-9 ]{12,}", re.IGNORECASE)

PAYMENT_RECEIVED = re.compile(
    r"\b(?:payment|transfer|amount)\s+(?:has been |is |was |have been )?(?:received|confirmed|done)\b"
    r"|\b(?:we(?:'ve| have)|I(?:'ve| have)) received your (?:payment|transfer|money)\b"
    r"|payment (?:mil gayi|receive ho gayi|ho gayi|aa gayi|confirm ho gayi)"
    r"|\b(?:paise|raqam|amount|rakam|transfer) (?:mil gaya|mil gayi|mil gaye|aa gaya|aa gayi|receive ho gaya)\b"
    r"|\bwe(?:'ve| have) (?:got|had) your (?:payment|transfer|money)\b"
    r"|\bpayment (?:has |have )?(?:arrived|come through|landed|cleared)\b"
    r"|\bthank(?:s| you) for (?:the |your )?(?:payment|transfer)\b(?! (?:screenshot|slip|receipt|proof|details|info))"
    # Arabic: "تم استلام الدفع", "استلمنا المبلغ", "وصلت الدفعة", "تم الدفع"
    r"|تم (?:ال)?[اإ]ستلام (?:ال)?(?:دفع|دفعة|دفعتك|مبلغ|تحويل|حوالة)"
    r"|[اإ]ستلمنا (?:ال)?(?:دفع|دفعة|دفعتك|مبلغ|تحويل|حوالة)"
    r"|وصلت (?:ال)?(?:دفعة|دفع|حوالة|تحويل)|تم (?:ال)?دفع\b|تم تأكيد (?:ال)?(?:دفع|دفعة|تحويل)"
    # Urdu script
    r"|ادائیگی (?:موصول|وصول|مل گئی|مل چکی|ہو گئی|ہو چکی|کنفرم)|(?:پیمنٹ|رقم|پیسے) (?:مل گئی|مل گئے|موصول|وصول|ہو گئی)"
    r"|ہمیں (?:ادائیگی|پیمنٹ|رقم) مل",
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
# Template-sounding phrases (2.0.4: regenerate) and the things pi never says (2.4: hard).
CORPORATE = (
    "i have registered your concern", "please be informed", "kindly note",
    "thank you for your response", "thank you for contacting",
)  # fmt: skip
NEVER_SAY = (
    "as an ai language model", "i'm just a bot", "i am just a bot", "just a bot",
    "get back to you shortly", "get back to you soon", "our team will get back",
)  # fmt: skip
INTERNAL = re.compile(
    r"\b(?:knowledge pack|industry pack|pipeline|system prompt|LLM|S\d+_[A-Z_]+|X_[A-Z_]+|R-[A-Z]+-\d+)\b"
)
# "tool" and "prompt" are internal terms too (2.4), unless the person said them first.
INTERNAL_PLAIN = re.compile(r"\b(?:tools?|prompts?)\b", re.IGNORECASE)
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
    r"|\bonly \d+ (?:days?|hours?|spots?) left\b|\bact now\b|\bspecial offer\b"
    r"|\bbefore it(?:'s| is) too late\b|\bwhile (?:slots|stocks?|spots) last\b|\bspots are (?:filling|going)\b"
    r"|\bprice (?:will|is going to) (?:go up|increase|rise)\b|\brunning out of time\b|\bdon'?t wait\b"
    r"|\boffer (?:is )?(?:valid|open) (?:until|till|for)\b",
    re.IGNORECASE,
)
# Flattery used to move a decision (R-SELL-03): soft, the model rewrites it.
FLATTERY = re.compile(
    r"\b(?:great|excellent|smart|wise|brilliant|fantastic|wonderful|clever|sharp) "
    r"(?:idea|move|call|choice|decision|thinking|point|instinct|observation|approach|plan)\b"
    r"|\byou(?:'re| are) (?:clearly |obviously |so |very |really )?(?:smart|wise|clever|sharp|brilliant|"
    r"an expert|a great|doing (?:great|well|amazing))\b|\bwell done\b|\bimpressive\b"
    r"|\bwhat a (?:great|smart|wise|brilliant)\b",
    re.IGNORECASE,
)
# Offering a discount moves a decision; saying pi cannot give one does not.
DISCOUNT = re.compile(r"\bdiscounts?\b", re.IGNORECASE)
NEGATED_DISCOUNT = re.compile(
    r"(?:can't|cannot|can not|won't|no|not|never|nahi|unable)\W+(?:\w+\W+){0,4}$", re.IGNORECASE
)
ASKED_FOR_HELP = re.compile(
    r"\b(?:solution|fix|solve|build|quote|price|pricing|cost|how much|proposal|what can you do|"
    r"can you help|can you fix|what would you build|(?:kya|kuch) kar sakte|"
    r"kar sakte (?:ho|hain) ya nahi|(?:kya|koi) hal (?:hai|he)|kitna|qeemat|hal|"
    r"can you (?:make|create|develop|build|set up)|(?:make|build|create) (?:me )?an? "
    r"(?:app|system|software|website|tool)|app for this|kharcha|kharch|"
    r"what (?:do|does) (?:you|workzap) (?:sell|offer|do)|your (?:products?|services?))\b",
    re.IGNORECASE,
)

WORD_CAP = 60
SUMMARY_CAP = 160
DOCUMENT_CAP = 120


def _cap(context: dict[str, Any], key: str, default: int) -> int:
    """A word limit: the workspace's own value (kept within +-30% of the default by
    `brain_config`) or the default. These are the only voice numbers spec 9.10 lets it tune."""
    value = (context.get("brain_settings") or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


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


def _heard(context: dict[str, Any]) -> str:
    """Everything the person has said, lower case with straight quotes: words they used first."""
    return _customer_words(context).lower().replace("’", "'")


def _offers_discount(reply: str, heard: str = "") -> bool:
    """A discount offered. Saying pi cannot give one does not count, and neither does asking about
    a discount the person raised themselves ("is it the discounts you can't make sense of?")."""
    for sentence in _sentences(reply):
        for match in DISCOUNT.finditer(sentence):
            if NEGATED_DISCOUNT.search(sentence[max(0, match.start() - 40) : match.start()]):
                continue
            if sentence.rstrip().endswith(QUESTION_MARKS) and (
                "discount" in heard
                or re.search(
                    r"\b(?:the|your|their|these|those)\s+$", sentence[: match.start()], re.I
                )
            ):
                continue  # asking about the discounts they deal with is not offering one
            return True
    return False


ECHOABLE_PROMISE = re.compile(r"\bguarantee[ds]?\b", re.IGNORECASE)
NOT_ATTRIBUTIVE = re.compile(
    r"(?:\bis|\bare|\bwas|\bbe|\bbeen|\bwe|\bI|\bwill|'ll|\bit's|'s|\byou're|\bthey're|\band|\bor|"
    r"\bthat's|\bto)\W+$",
    re.IGNORECASE,
)


def _promise_hits(reply: str, heard: str = "") -> bool:
    for match in PROMISE.finditer(reply):
        if NEGATED_PROMISE.search(reply[max(0, match.start() - 30) : match.start()]):
            continue
        word = match.group(0).lower()
        # "guaranteed count" in a banquet hall: a word they used, as a name for a thing, is not a
        # promise. "we guarantee ..." or "it is guaranteed" still is.
        if (
            ECHOABLE_PROMISE.fullmatch(word)
            and (word[:9] in heard or ATTRIBUTIVE_NOUNS.match(reply[match.end() :]))
            and re.match(r"\s+[a-z]", reply[match.end() :], re.IGNORECASE)
            and not NOT_ATTRIBUTIVE.search(reply[max(0, match.start() - 14) : match.start()])
        ):
            continue
        return True
    return False


ABSENCE = re.compile(
    r"(?:\bno\b|\bwithout\b|\bnot\b|\bnahi\b|\bnever\b|\bmissing\b|\black of\b|\bno written\b)\W+(?:\w+\W+){0,3}$",
    re.IGNORECASE,
)
NOTING = re.compile(r"\bnoted?\b|note kar|likh liya|likh liye", re.IGNORECASE)
ATTRIBUTIVE_NOUNS = re.compile(
    r"\s+(?:count|number|minimum|headcount|guests?|deposit|amount)\b", re.IGNORECASE
)


def _stem(word: str) -> str:
    first = word.lower().split()[0]
    return first[:-1] if first.endswith("s") else first


def _unheard_offer_words(reply: str, heard: str) -> bool:
    """An offer word (quote, proposal, solution) the person did not use first. The owner's own trade
    words ("our quotes take a day to prepare") may be echoed back while listening."""
    said = {_stem(m.group(0)) for m in OFFER_WORDS.finditer(heard)}
    for m in OFFER_WORDS.finditer(reply):
        if _stem(m.group(0)) in said:
            continue
        # noting an absence ("no itemised quote", "without a proposal") offers nothing
        if ABSENCE.search(reply[max(0, m.start() - 30) : m.start()]):
            continue
        return True
    return False


def _unheard(pattern: re.Pattern[str], text: str, heard: str) -> str | None:
    """The first match of `pattern` in `text` whose words the person did not say first."""
    for match in pattern.finditer(text):
        if match.group(0).lower() not in heard:
            return match.group(0)
    return None


def _statements(reply: str) -> list[str]:
    """The sentences that are not questions: where pi asserts something."""
    return [s for s in _sentences(reply) if not s.rstrip().endswith(QUESTION_MARKS)]


def _contains(reply: str, phrases: tuple[str, ...]) -> str | None:
    lowered = reply.lower().replace("’", "'")
    return next((p for p in phrases if p in lowered), None)


# Phrases from the canonical bank (2.3) that must not repeat word for word (the opening and the
# offer are fixed and exempt).
CANONICAL = (
    "that's a real problem", "that sounds costly", "that's worth sorting", "no rush",
    "anything else getting in the way", "got it",
)  # fmt: skip

FESTIVAL = re.compile(
    r"\b(?:eid|mubarak|ramadan|ramzan|kareem|christmas|diwali|new year)\b|مبارك|عيد", re.IGNORECASE
)


def _allowed_bangs(context: dict[str, Any]) -> int:
    """R-VOICE-07: one exclamation mark in a whole conversation, and only for a festival greeting
    when the person used one first."""
    said = str(context.get("latest_customer_message", ""))
    earlier = any(
        "!" in str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "ai"
    )
    return 1 if "!" in said and FESTIVAL.search(said) and not earlier else 0


NOT_UNDERSTOOD = re.compile(
    r"\b(?:samajh|samjh|samjha|samja) (?:nahi|nhi|nahin)"
    r"(?: (?:aayi|aaya|aai|aya|ayi|paya|payi|saka|saki|aa raha|aa rahi))?\b"
    r"|\bdid(?:n'?t| not) (?:understand|follow|get)\b|\bdon'?t (?:understand|follow)\b",
    re.IGNORECASE,
)
STIFF_APOLOGY = re.compile(r"\bmaa?zrat\b|\bmaazerat\b", re.IGNORECASE)
BULLET = ("•", "- ")
WORDS_PER_POINT = 4  # a list point needs about this many of their words in the latest message


def _points(text: str) -> list[str]:
    return [
        " ".join(re.findall(r"\w+", line.lower()))
        for line in text.splitlines()
        if line.lstrip().startswith(BULLET)
    ]


def _relists(reply: str, context: dict[str, Any]) -> bool:
    """A list while listening that repeats itself, repeats an earlier list, or has more points
    than their latest message could hold ("no" answered with four points)."""
    points = _points(reply)
    if not points:
        return False
    earlier = {p for said in _pi_replies(context) for p in _points(said)}
    latest = len(str(context.get("latest_customer_message", "")).split())
    return (
        len(set(points)) < len(points)
        or any(p in earlier for p in points)
        or (len(points) >= 2 and latest < WORDS_PER_POINT * len(points))
    )


# A reply that was asked for may carry the ideas, the Workzap line and, for "how exactly?", the
# solution document. It may not pitch a product, recommend, offer a quote itself (the application
# adds the offer) or name an amount: those stay hard.
GIVEN_PITCH = re.compile(
    r"\bnori\b|\bour (?:product|products|service|services|software|platform|system|app)\b"
    r"|\bI(?:'d| would) recommend\b",
    re.IGNORECASE,
)
GIVEN_OFFER = re.compile(r"\bquotes?\b|\bquotation\b|\bproposals?\b", re.IGNORECASE)
SOLUTION_DOCUMENT = re.compile(r"\bsolution documents?\b", re.IGNORECASE)
AMOUNT_WORDS = re.compile(
    r"\b\d[\d,.]*\s*(?:k|lakh|lac|crore|rupees?|dollars?|dirhams?|usd|pkr|aed)\b"
    r"|\b(?:rupees|dollars|dirhams|lakhs?|crores?)\b",
    re.IGNORECASE,
)
WORKZAP_WILL = re.compile(r"\bWorkzap will\b|\bho jayega\b", re.IGNORECASE)
VALUE_LINE_RULES = (
    ("more than two", "R-VAL-01"),
    ("how-to", "R-VAL-04"),
    ("tool words", "R-BUILD-01"),
    ("automatically", "R-BUILD-04"),
    ("personal data", "R-PRIV-07"),
    ("claim", "R-PROM-01"),
)


def _given_turn_limits(reply: str, context: dict[str, Any], add: Any) -> None:
    """What a reply to a request for a fix or for the detail still may not say."""
    if GIVEN_PITCH.search(reply):
        add(
            Violation(
                "R-SELL-01",
                "no product, no nori, no recommendation: only the ideas "
                "and what Workzap would do for them",
                True,
            )
        )
    if GIVEN_OFFER.search(reply) or (
        context.get("solution_asked") and SOLUTION_DOCUMENT.search(reply)
    ):
        add(
            Violation(
                "R-OFFER-03",
                "do not make the offer or mention a quote yourself: the "
                "application adds the offer after your reply",
                True,
            )
        )
    if AMOUNT_WORDS.search(reply):
        add(Violation("R-OFFER-05", "never an amount, a range or a price before the quote", True))
    if WORKZAP_WILL.search(reply):
        add(Violation("R-BUILD-06", '"would" or "could", never "will": no promised results'))


def _value_line(reply: str, context: dict[str, Any], add: Any) -> None:
    """Addendum 2, 1.4 and 1.9: a "how exactly?" answer names what the document covers and gives no
    steps or app; a Workzap line never repeats its opener or "automatically" within a chat."""
    from app.modules.pi import solution_rules, solutions  # local: they import this module's users

    said = _customer_words(context)
    howto = context.get("solution_howto")
    if howto:
        for why in solution_rules.check_sample_reply(reply, said):
            rule = next((r for key, r in VALUE_LINE_RULES if key in why), "R-VAL-04")
            add(Violation(rule, f"how exactly: {why}", True))
        if howto.get("which_app") and solution_rules.VENDOR.search(reply):
            add(
                Violation(
                    "R-VAL-05", "do not recommend an app: the whole set-up is the build", True
                )
            )
    earlier = " ".join(_pi_replies(context)).lower()
    if solutions.AUTOMATIC.search(reply) and solutions.AUTOMATIC.search(earlier):
        add(Violation("R-BUILD-04", 'say "automatically" at most once in a conversation'))
    lowered = reply.lower()
    for opener in solutions.BRIDGE_OPENERS:
        for line in (opener["en"], opener["roman_ur"]):
            if line and line.lower() in lowered and line.lower() in earlier:
                add(Violation("R-BUILD-04", "that bridge opener was already used in this chat"))
    tools = solutions.banned_tool_words(reply, said)
    if tools:
        add(
            Violation(
                "R-BUILD-01", f"say what they would notice, not the tool ({', '.join(tools)})"
            )
        )
    phrases = {
        line.lower()
        for entry in solutions.CATALOGUE.values()
        for line in (entry["en"], entry["roman_ur"])
    }
    if sum(1 for phrase in phrases if phrase in lowered) > 2:
        add(
            Violation("R-BUILD-05", "one build in a message, two at most, never a list of features")
        )
    build = context.get("solution_build")
    if (
        isinstance(build, dict)
        and build.get("says")
        and not build.get("refer_back")
        and "workzap" not in lowered
    ):
        # Part 1.9: the point of the line is to tell them this is Workzap's build, not free
        # advice indistinguishable from the ideas above it. Dropping the name defeats that.
        add(
            Violation(
                "R-BUILD-03",
                'say it is Workzap who would do this ("Workzap would...", "Workzap could..."), '
                "not an unattributed third idea",
            )
        )


# --- R-HONEST-01: no invented timelines, clients, case studies, statistics or team members ---------
_NUM = (
    r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|"
    r"few|couple of|several|\d+)"
)
_UNIT = r"(?:minutes?|hours?|days?|weeks?|months?|years?|fortnights?)"
_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
TIMELINE_STRONG = re.compile(
    rf"\b(?:in|within|inside|after|in the next|over the next)\s+(?:about |around |roughly |just |only |another )?"
    rf"{_NUM}\s+(?:more |business |working )?{_UNIT}\b"
    rf"|\bby (?:next )?{_WEEKDAY}\b|\bby (?:the )?end of (?:the |this |next )?(?:day|week|month|year)\b"
    r"|\bby (?:tomorrow|tonight)\b|\bwithin (?:the )?(?:day|week|month)\b"
    # Roman Urdu
    r"|\bkal tak\b|\bparson tak\b|\baaj tak\b|\bagle (?:hafte|mahine)\b|\bis hafte (?:tak|mein)\b"
    r"|\b(?:ek|do|teen|char|chaar|paanch|panch|chhe|saat|aath|nau|das|kuch|chand|\d+) "
    r"(?:din|dino|hafte|haftay|hafta|mahine|mahina|mahinay|ghante|ghanta|saal)(?: mein| me| main| tak| ke andar)\b"
    # Arabic and Urdu script
    r"|خلال (?:يوم|يومين|أسبوع|اسبوع|أسبوعين|اسبوعين|شهر|شهرين|ساعة|ساعتين|\S+ (?:أيام|ايام|أسابيع|اسابيع|أشهر|اشهر|ساعات))"
    r"|بحلول (?:الغد|غدا|غداً|نهاية)|(?:دو|ایک|تین|چار|پانچ) (?:ہفتے|دن|مہینے|گھنٹے) (?:میں|تک)|کل تک",
    re.IGNORECASE,
)
TIMELINE_WEAK = re.compile(
    rf"\b(?:tomorrow|tonight|next (?:week|month|{_WEEKDAY})|this (?:week|weekend)|same day|"
    rf"(?:a|one|two|three|a few|a couple of) (?:day|week|month|fortnight)s?)\b",
    re.IGNORECASE,
)
PROMISE_CUE = re.compile(
    r"\b(?:will|'ll|would|should|can|could|shall|going to|usually|typically|normally|takes?|take|ready|"
    r"done|delivered?|deliver|finish(?:ed)?|complete[sd]?|launch|live|build|get it|get you|send|have it)\b",
    re.IGNORECASE,
)
INVENTED_PROOF = re.compile(
    r"\bcase stud(?:y|ies)\b|\bone of our (?:clients?|customers?)\b"
    r"|\b(?:our|other|previous|past) (?:clients?|customers?) (?:have|has|saw|got|reduced|increased|cut|saved|"
    r"like|such as|including)\b"
    r"|\bwe(?:(?:'ve| have) (?:helped|worked with|built|delivered|served|done)|"
    r" (?:helped|worked with|built|delivered|served))\b[^.?!\n]{0,40}\b"
    r"(?:businesses|clients|customers|shops|companies|clinics|restaurants|others|similar)\b"
    r"|\bsimilar (?:businesses|shops|clinics|companies|clients|restaurants) (?:to yours )?(?:we|that we|have|saw|"
    r"reduced|cut|increased|got)\b"
    r"|\b(?:studies|research|surveys?|statistics) (?:show|shows|suggest|suggests|indicate|say|says|found)\b"
    r"|\bon average\b|\bindustry (?:average|standard|benchmark)s?\b"
    r"|\b(?:typically|usually|normally) (?:save|saves|cut|cuts|reduce|reduces|increase|increases|boost|improve)\b"
    r"|\b(?:out of|in) (?:every )?(?:ten|\d+) (?:businesses|shops|owners|clients|customers|companies)\b"
    r"|\b\d+(?:\.\d+)?\s?(?:%|percent|per cent)"
    r"|\b(?i:my|our) (?i:colleague|teammate|manager|developer|engineer|designer|consultant|founder|ceo|cto|"
    r"account manager|specialist|expert) (?-i:(?!Workzap\b)[A-Z][a-z]{2,})\b"
    r"|\b(?:ask for|speak (?:to|with)|talk (?:to|with)|contact|meet) (?:Mr|Ms|Mrs|Dr)\.? ?[A-Z][a-z]+",
    re.IGNORECASE,
)
CURRENCY_AMOUNT = re.compile(
    r"(?:\bRs\.?|\bPKR|\bAED|\bUSD|\bCAD|[$₹€£])\s?\d[\d,.]*"
    r"|\b\d[\d,.]*\s?(?:rupees?|dollars?|dirhams?|k|lakhs?|lacs?|crores?|PKR|AED|USD)\b",
    re.IGNORECASE,
)


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,]*", text.replace(",", "")))


def _time_pairs(text: str) -> set[tuple[str, str]]:
    words = {
        "1": "one",
        "2": "two",
        "3": "three",
        "4": "four",
        "5": "five",
        "6": "six",
        "7": "seven",
    }
    pairs = set()
    for m in re.finditer(rf"\b({_NUM})\s+(?:more |business |working )?({_UNIT})\b", text.lower()):
        number = words.get(m.group(1), "one" if m.group(1) in ("a", "an") else m.group(1))
        pairs.add((number, m.group(2).rstrip("s")))
    roman_numbers = {"ek": "one", "do": "two", "teen": "three", "char": "four", "chaar": "four",
                     "paanch": "five", "panch": "five", "das": "ten"}  # fmt: skip
    roman_units = {"din": "day", "dino": "day", "hafta": "week", "hafte": "week", "haftay": "week",
                   "mahina": "month", "mahine": "month", "mahinay": "month", "ghanta": "hour",
                   "ghante": "hour", "saal": "year"}  # fmt: skip
    for m in re.finditer(r"\b(ek|do|teen|char|chaar|paanch|panch|das)\s+(din|dino|hafta|hafte|haftay|"
                         r"mahina|mahine|mahinay|ghanta|ghante|saal)\b", text.lower()):  # fmt: skip
        pairs.add((roman_numbers[m.group(1)], roman_units[m.group(2)]))
    return pairs


def _approved_text(context: dict[str, Any]) -> str:
    raw = context.get("approved_claims") or context.get("approved_context") or ""
    if isinstance(raw, (list, tuple)):
        raw = " ".join(str(x) for x in raw)
    return str(raw).lower()


def _honesty(reply: str, context: dict[str, Any], heard: str, add: Any) -> None:
    approved = _approved_text(context)
    said_pairs = _time_pairs(heard)
    for sentence in _statements(reply):
        low = sentence.lower()
        hit = None
        for m in TIMELINE_STRONG.finditer(low):
            text = m.group(0)
            if text in heard or text in approved:
                continue
            pairs = _time_pairs(text)
            if pairs and pairs <= said_pairs:
                continue
            # "Noted, ek hafte tak ki der": recording the delay they described is not a promise
            if NOTING.search(low) and re.search(
                r"hafte|hafta|din|mahin|ghant|week|day|month", heard
            ):
                continue
            hit = text
            break
        if not hit and PROMISE_CUE.search(low):
            for m in TIMELINE_WEAK.finditer(low):
                text = m.group(0)
                pairs = _time_pairs(text)
                if text in heard or text in approved or (pairs and pairs <= said_pairs):
                    continue
                hit = text
                break
        if hit:
            add(
                Violation(
                    "R-HONEST-01",
                    f'no timeline pi was not given ("{hit}"): never invent a date or duration',
                    True,
                )
            )
            break
    for m in INVENTED_PROOF.finditer(reply):
        text = m.group(0).lower()
        if text in heard or text in approved:
            continue
        if re.search(r"\d", text) and _numbers(text) <= _numbers(heard):
            continue
        add(
            Violation(
                "R-HONEST-01",
                f'no invented clients, case studies, statistics or team members ("{m.group(0)}")',
                True,
            )
        )
        break
    if not context.get("approved_quote"):
        for m in CURRENCY_AMOUNT.finditer(reply):
            if _numbers(m.group(0)) and _numbers(m.group(0)) <= _numbers(heard):
                continue
            add(Violation("R-HONEST-01", "no amount or price before an approved quote", True))
            break


# --- R-PRIV-03/04, R-ASK-06: things pi never asks for ----------------------------------------------
ASK_PEOPLE = re.compile(
    r"\b(?:your|the|his|her|their) (?:staff|employee|employees|cashier|manager|driver|customer|client|"
    r"supplier|worker|partner|accountant|patient|waiter|salesman|technician)(?:'s|s'| member's)? "
    r"(?:full )?(?:names?|phones?|phone numbers?|numbers?|addresses|address|mobile|whatsapp|cell|contacts?)\b"
    r"|\bnames? of (?:your |the )?(?:staff|employees?|customers?|clients?|suppliers?|workers?|cashiers?|"
    r"drivers?|patients?|managers?)\b"
    r"|\b(?:his|her|their|the customer's|the client's) (?:name|number|phone)\b",
    re.IGNORECASE,
)
ASK_MONEY = re.compile(
    r"\b(?:exact|precise|actual|accurate) (?:figure|number|amount)?\s*(?:of )?(?:your |the )?(?:monthly |annual |"
    r"yearly |daily |weekly )?(?:revenue|turnover|sales|profit|income|earnings|salary|salaries)\b"
    r"|\b(?:revenue|turnover|profit|income|earnings) (?:figures?|numbers?) (?:to the|exactly)\b"
    r"|\bhow much (?:exactly|precisely) (?:do you|did you|are you) (?:earn|make|sell|pay)\b"
    r"|\bbank (?:balance|statement)s?\b|\baccount balance\b|\bbalance in (?:your )?(?:bank|account)\b"
    r"|\b(?:what(?:'s| is)|how much (?:is|does)) (?:[A-Z][a-z]+'s|his|her|\w+'s) (?:salary|pay|wage)\b",
    re.IGNORECASE,
)
ASK_VERB = re.compile(
    r"\b(?:send|share|give|provide|tell me|what(?:'s| is)|what are|may i have|can i (?:have|get)|could you "
    r"(?:send|share|give|tell)|can you (?:send|share|give|tell)|i need|i'll need|please (?:send|share|give))\b",
    re.IGNORECASE,
)

# --- R-ADV: advice pi never gives (in its own reply) -----------------------------------------------
ADVICE = re.compile(
    # tax and legal
    r"\b(?:charge|add|apply|set|use|put)\b[^.?!\n]{0,40}\b\d+\s?%[^.?!\n]{0,20}\b(?:tax|vat|gst)\b"
    r"|\b(?:vat|gst|sales tax|tax) (?:rate )?(?:is|should be|of|at) (?:\d+|five|seven|eight|ten|fifteen|"
    r"seventeen|eighteen|twenty)\b"
    r"|\byou (?:can|may|could|are allowed to|have the right to|are legally allowed to) (?:legally )?"
    r"(?:fire|sack|terminate|dismiss|sue|withhold|evict|deduct|claim|write off)\b"
    r"|\byou (?:don't|do not) (?:need|have) to (?:pay|charge|file|register|declare) (?:any )?(?:tax|vat|gst)\b"
    r"|\bit(?:'s| is) (?:perfectly |completely |totally )?(?:legal|illegal|unlawful|lawful)\b"
    r"|\blegally (?:allowed|entitled|required|binding|obliged|fire|sack)\b"
    r"|\byou have a (?:strong |good |solid )?(?:legal )?(?:case|claim)\b|\bbreach of contract\b"
    r"|\byour contract (?:says|means|allows|lets)\b"
    # money
    r"|\b(?:take|get|apply for|go for|opt for|consider|try) (?:a |an )?(?:bank |business |personal )?loan\b"
    r"|\b(?:from|with|at|try|use|choose|go to|open an account (?:with|at)) (?:HBL|UBL|MCB|Meezan|Allied|"
    r"Bank Alfalah|Alfalah|Faysal|Standard Chartered|Emirates NBD|ADCB|Mashreq|RBC|Scotiabank|BMO|CIBC)\b"
    r"|\byou (?:should|could|can|ought to) (?:invest|borrow|take out)\b|\binvest in\b"
    r"|\b(?:buy|sell) (?:shares|stocks|gold|crypto|bitcoin|property)\b"
    # medical
    r"|\b\d+\s?(?:mg|mcg|ml)\b|\btake (?:\w+ ){0,2}(?:tablets?|pills?|capsules?|mg|ml)\b"
    r"|\b(?:dose|dosage)\b[^.?!\n]{0,20}\b(?:should be|of \w+ is)\b"
    r"|\byou (?:have|might have|probably have|may have|likely have)\b[^.?!\n]{0,20}\b(?:diabetes|infection|"
    r"cancer|flu|virus|allergy|depression|anxiety|covid|hepatitis|asthma)\b"
    # accusing someone
    r"|\b(?:your|the) (?:[a-z]+ ){0,2}(?:is|are|must be|has been|probably is|are probably) "
    r"(?:stealing|lying|cheating|embezzling|skimming|a thief|thieves)\b"
    r"|\b(?-i:[A-Z][a-z]{2,}) (?:is|was|has been|must be|may be|might be|is probably|is likely) "
    r"(?:stealing|a thief|lying|cheating|embezzling|skimming|a fraud|corrupt)\b",
    re.IGNORECASE,
)
OPINION = re.compile(
    r"\bvot(?:e|ing) for\b"
    r"|\b(?:the government|PTI|PML-N|PPP|BJP|Congress|Trump|Biden|Modi|Imran Khan|Nawaz Sharif|Zardari)\b"
    r"[^.?!\n]{0,40}\b(?:is|are|was|were) (?:corrupt|wrong|right|terrible|great|useless|to blame|the best|"
    r"the worst|failing|a (?:failure|disaster))\b"
    r"|\b(?:islam|muslims?|christianity|christians?|hindus?|hinduism|jews?|religion)\b[^.?!\n]{0,40}"
    r"\b(?:is|are) (?:better|worse|wrong|right|false|true|the best)\b"
    r"|\b(?:better|worse|cheaper|more reliable) than (?:Zoho|QuickBooks|Odoo|Shopify|Foodics|Square|Toast|SAP|"
    r"Tally|Xero|Salesforce|HubSpot|Wave|Marg)\b",
    re.IGNORECASE,
)
OFF_TOPIC = re.compile(
    r"```|\bdef \w+\(|\bonce upon a time\b|\bhere(?:'s| is) a (?:joke|poem|story|essay)\b",
    re.IGNORECASE,
)

# --- R-META-01, 2.4, R-ILLU-01, R-VOICE-14 ---------------------------------------------------------
META_POLICY = re.compile(
    r"\b(?:whatsapp|meta|facebook)\b[^.?!\n]{0,60}\b(?:policy|policies|terms|rules|guidelines|ban(?:s|ned)?|"
    r"block(?:s|ed)?|restrict(?:s|ed|ions?)?|suspend(?:s|ed)?|24[- ]hour|templates?|opt[- ]?in|compliance|"
    r"spam|fees?|pricing)\b"
    r"|\b(?:policy|policies|terms|rules|guidelines|ban(?:s|ned)?|blocked?|restrict\w*|suspend\w*)\b"
    r"[^.?!\n]{0,60}\b(?:whatsapp|meta|facebook)\b",
    re.IGNORECASE,
)
META_OK = re.compile(
    r"\b(?:not|isn't|aren't)\b[^.?!\n]{0,30}\b(?:made|run|endorsed|owned|affiliated|approved)\b"
    r"|\bmade by workzap\b|\bbusiness platform\b|\bthrough whatsapp\b|\bchat(?:s|ting)? (?:through|on|via)\b",
    re.IGNORECASE,
)
ILLUSTRATION = re.compile(
    r"\b(?:for example|for instance|e\.g\.|let's say|lets say|say you|(?<!can )(?<!can't )imagine|suppose|picture this|"
    r"misaal|maslan|farz karein)\b|\ba typical (?:case|day|client|customer)\b",
    re.IGNORECASE,
)
AMERICAN = re.compile(
    r"\b(?:colors?|colored|favorites?|behaviors?|neighbors?|honors?|labor|organi[z](?:e|es|ed|ing|ation|ations)|"
    r"centers?|analy[z](?:e|es|ed|ing)|catalogs?|grays?|jewelry|aluminum|defense|offense|fulfill|enrollment|"
    r"traveling|canceled|modeling|labeled|"
    r"(?:a|the|your|our|driving|software|trade|business) licenses?|"
    r"(?:training|loyalty|rewards|referral|membership|education|wellness) programs?|prioriti[z](?:e|es|ed|ing)|"
    r"customi[z](?:e|es|ed|ing)|recogni[z](?:e|es|ed|ing)|apologi[z](?:e|es|ed|ing)|summari[z](?:e|es|ed|ing)|"
    r"realiz(?:e|es|ed|ing)|minimiz(?:e|es|ed|ing)|optimiz(?:e|es|ed|ing)|standardiz(?:e|es|ed|ing))\b",
    re.IGNORECASE,
)
BOLD_SINGLE = re.compile(r"(?<![\w*])\*[^*\s][^*\n]*\*(?![\w*])")
NEUTRAL_EMOJI = "🙂😊👍🙏👌✅"
NEVER_EMOJI = "😂🤣😭😅😢😡🤬💀😩😞😔"
SKIN_TONES = re.compile("[\U0001f3fb-\U0001f3ff️]")
BULLET_STATES = frozenset(
    {
        flow.State.S1_LISTENING,
        flow.State.S3_NOTED,
        flow.State.S4_SORTED_SUMMARY,
        flow.State.S5_READINESS,
        flow.State.S7_DELIVERED,
    }
)


def allowed_emoji(context: dict[str, Any]) -> set[str]:
    """R-VOICE-08: a tick; and once the person uses emoji, one simple neutral one, or their own
    emoji when it is neutral. Never a laughing, crying or angry one on a business problem."""
    theirs = {m for m in EMOJI.findall(_customer_words(context)) if m not in NEVER_EMOJI}
    if not EMOJI.search(_customer_words(context)):
        return {ALLOWED_EMOJI}
    return ({ALLOWED_EMOJI} | theirs | set(NEUTRAL_EMOJI)) - set(NEVER_EMOJI)


def _discloses(reply: str) -> bool:
    """R-DISC-01: some sentence says, about pi itself, that it is an AI."""
    return any(AI_WORDS.search(s) and SELF_WORDS.search(s) for s in _sentences(reply))


def _claims_payment(reply: str) -> bool:
    return any(PAYMENT_RECEIVED.search(s) for s in _statements(reply))


def _asks_for_what_it_never_asks(reply: str, heard: str, add: Any) -> None:
    for sentence in _sentences(reply):
        refusing = bool(REFUSING.search(sentence))
        if NATIONAL_ID.search(sentence) and ASKING.search(sentence) and not refusing:
            add(
                Violation(
                    "R-PRIV-03", "never ask for national ID, passport or account numbers", True
                )
            )
            return
        if ASK_VERB.search(sentence) and not refusing:
            if ASK_PEOPLE.search(sentence):
                add(
                    Violation(
                        "R-PRIV-04",
                        "never ask for a staff member's or customer's name, phone or address: say the role",
                        True,
                    )
                )
                return
            if ASK_MONEY.search(sentence) and not re.search(
                r"\b(?:roughly|approximately|about|rough|ballpark)\b", sentence, re.IGNORECASE
            ):
                add(
                    Violation(
                        "R-ASK-06",
                        "never ask for exact revenue, salaries or bank balances: ask for rough scale",
                        True,
                    )
                )
                return


def _advice_and_policy(reply: str, heard: str, add: Any) -> None:
    for pattern, rule, message in (
        (ADVICE, "R-ADV-01", "no legal, medical, tax or financial advice and no accusing anyone"),
        (OPINION, "R-ADV-04", "no opinions on politics, religion or competitors"),
    ):
        for m in pattern.finditer(reply):
            if m.group(0).lower() in heard:
                continue
            add(Violation(rule, f'{message} ("{m.group(0)}")', True))
            break
    if OFF_TOPIC.search(reply):
        add(
            Violation("R-ADV-05", "pi is for the business problem: no code, jokes or stories", True)
        )
    for sentence in _sentences(reply):
        policy = META_POLICY.search(sentence)
        if not policy or META_OK.search(sentence):
            continue
        low = sentence.lower()
        key = policy.group(0).split()[-1].lower()[:4]
        if key in heard and (sentence.rstrip().endswith(QUESTION_MARKS) or "noted" in low):
            continue
        add(
            Violation(
                "R-META-01", "say nothing about Meta or WhatsApp policy beyond who made pi", True
            )
        )
        break


def _style_soft(reply: str, context: dict[str, Any], heard: str, state: Any, add: Any) -> None:
    if INTERNAL_PLAIN.search(reply):
        word = INTERNAL_PLAIN.search(reply)
        if (
            word
            and word.group(0).lower().rstrip("s") not in heard
            and word.group(0).lower() not in heard
        ):
            add(
                Violation(
                    "R-VOICE-06", f'internal term ("{word.group(0)}"): say what it does', True
                )
            )
    if FLATTERY.search(reply):
        add(Violation("R-SELL-03", "no flattery: react to the problem, not to the person"))
    if (
        ILLUSTRATION.search(" ".join(_statements(reply)))
        and "illustrative" not in reply.lower()
        and not ILLUSTRATION.search(heard)
    ):
        add(Violation("R-ILLU-01", 'label any made-up example "Illustrative"'))
    american = [m.group(0) for m in AMERICAN.finditer(reply) if m.group(0).lower() not in heard]
    if american:
        add(Violation("R-VOICE-14", f'British spelling, not "{american[0]}"'))
    if BOLD_SINGLE.search(reply) and state in (
        flow.State.S0_NEW,
        flow.State.S1_LISTENING,
        flow.State.S2_CLARIFYING,
    ):
        add(Violation("R-VOICE-09", "bold only for the noted problem title and document names"))
    lines = [x for x in reply.splitlines() if x.lstrip().startswith(("•", "- "))]
    if lines and (len(lines) == 1 or (state is not None and state not in BULLET_STATES)):
        add(Violation("R-VOICE-09", "bullets only in summaries"))


def lint(reply: str, context: dict[str, Any]) -> list[Violation]:
    """Every constitution or voice rule the draft breaks (empty when it is fine to send)."""
    found: list[Violation] = []
    add = found.append
    first_sentence = (_sentences(reply) or [""])[0]
    history = context.get("history") or []

    # Identity and disclosure (R-DISC)
    heard = _heard(context)
    if not any(h.get("role") == "ai" for h in history) and not _discloses(reply):
        add(Violation("R-DISC-01", "the first message must say plainly that pi is an AI", True))
    if ASKS_IF_AI.search(str(context.get("latest_customer_message", ""))) and not AI_WORDS.search(
        first_sentence
    ):
        add(
            Violation(
                "R-DISC-02", "they asked if pi is a person: say it is an AI in sentence one", True
            )
        )
    reply = reply.replace("\u2019", "'")
    if (
        TEAM_READS.search(reply)
        and flow.parse((context.get("flow") or {}).get("state")) != flow.State.X_HUMAN
    ):
        add(
            Violation(
                "R-DISC-04", "do not imply a person is reading this chat unless one took over", True
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
    _asks_for_what_it_never_asks(reply, heard, add)
    squashed = re.sub(r"(?<=\d) (?=\d)", "", reply)
    if IBAN.search(squashed) or ACCOUNT_NUMBER.search(reply) or IBAN_LABEL.search(reply):
        add(
            Violation(
                "R-PAY-03", "never type bank details: they are only on the approved quote", True
            )
        )
    if _claims_payment(reply) and not context.get("payment_confirmed"):
        add(Violation("R-PAY-05", "never say a payment was received until staff confirm it", True))

    # No pitching while listening (R-SELL)
    state = flow.parse((context.get("flow") or {}).get("state"))
    if URGENCY.search(reply) or _offers_discount(reply, heard):
        add(Violation("R-SELL-03", "no urgency, scarcity or discounts to move a decision", True))
    if state in flow.NO_OFFER:
        requested = bool(ASKED_FOR_HELP.search(str(context.get("latest_customer_message", ""))))
        # Solution mode (Addendum 2, 1.4 and 1.6): they asked for a fix or for the detail, so
        # this reply may carry the ideas, the Workzap line and the document. The value-line
        # checks below still apply.
        given = bool(context.get("solution_asked")) or "solution_howto" in context
        if given:
            _given_turn_limits(reply, context, add)
        elif PITCH_WORDS.search(reply) or (
            OFFER_WORDS.search(reply) and not requested and _unheard_offer_words(reply, heard)
        ):
            add(
                Violation(
                    "R-SELL-01",
                    "they are still describing problems: suggest no fix, product, document or "
                    "quote. If they asked, say only that Workzap can prepare a solution "
                    "document once the problems are noted, then go back to listening",
                    True,
                )
            )

    if "solution_howto" in context or context.get("solution_asked"):
        _value_line(reply, context, add)

    # Honesty (R-HONEST, R-PROM)
    if _promise_hits(reply, heard):
        add(Violation("R-PROM-01", "no guarantees, promised results or savings figures", True))
    if any(not NOT_SOLVED.search(s) for s in _sentences(reply) if SOLVED.search(s)):
        add(Violation("R-LANG-01", "sorted means noted and grouped, never solved", True))
    _honesty(reply, context, heard, add)
    _advice_and_policy(reply, heard, add)
    _style_soft(reply, context, heard, state, add)

    # The value line (R-VAL, R-BUILD): checked whenever pi was handed free ideas or a follow-up.
    if "solution_ideas" in context or "solution_followup" in context:
        from app.modules.pi import solution_rules  # local: it imports learning, which imports this

        for why in solution_rules.check_sample_reply(reply, _customer_words(context)):
            add(Violation("R-VAL-01", f"free ideas: {why}", True))

    # Voice (R-VOICE)
    asked = sum(reply.count(mark) for mark in QUESTION_MARKS)
    stripped = reply.rstrip().rstrip(ALLOWED_EMOJI).rstrip()
    if asked > 1:
        add(Violation("R-VOICE-02", "ask one question at most"))
    elif asked == 1 and not stripped.endswith(QUESTION_MARKS):
        add(Violation("R-VOICE-02", "the question must be the last sentence"))
    bullets = sum(1 for line in reply.splitlines() if line.lstrip().startswith(("•", "- ")))
    normal_cap = _cap(context, "word_cap", WORD_CAP)
    cap = (
        _cap(context, "summary_word_cap", SUMMARY_CAP)
        if bullets >= 3
        else _cap(context, "document_word_cap", DOCUMENT_CAP)
        if "http" in reply
        else normal_cap
    )
    words = len(reply.split())
    if (
        state in flow.LISTENING
        and state != flow.State.S4_SORTED_SUMMARY  # a corrected summary repeats its lines
        and _relists(reply, context)
    ):
        add(
            Violation(
                "R-VOICE-09",
                "do not list back what you already confirmed or restate their whole story: "
                "confirm only the new problem this message adds, in one short line",
            )
        )
    if context.get("said_wrong") and NOT_UNDERSTOOD.search(reply):
        add(
            Violation(
                "R-CORR-02",
                "they corrected something you noted: say they are right and that it is "
                "fixed or removed, never that you did not understand",
            )
        )
    if STIFF_APOLOGY.search(reply):
        add(Violation("R-VOICE-04", 'say "Maaf kijiye", not "mujhe maazrat chahiye"'))
    if words > cap:
        add(Violation("R-VOICE-01", f"too long: {words} words, the limit is {cap}"))
    elif cap == normal_cap and words > int(
        (context.get("style") or {}).get("reply_up_to_words") or cap
    ):
        # They write short: stay near one and a half times their length (spec 8.4.1).
        reach = context["style"]["reply_up_to_words"]
        add(Violation("R-VOICE-01", f"they write short: about {reach} words at most, not {words}"))
    hype = _contains(reply, tuple(p for p in HYPE if p not in heard))
    if hype:
        add(Violation("R-VOICE-05", f'no hype ("{hype}")', True))
    if empathy := _contains(reply, FAKE_EMPATHY):
        add(
            Violation(
                "R-VOICE-06",
                f'no scripted empathy ("{empathy}"): react briefly and specifically',
                True,
            )
        )
    if reply.count("!") > _allowed_bangs(context):
        add(Violation("R-VOICE-07", "no exclamation marks"))
    marks = EMOJI.findall(SKIN_TONES.sub("", reply))
    if len(marks) > 1 or (marks and marks[0] not in allowed_emoji(context)):
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
    if re.search("[؀-ۿ]", reply) and re.search(r"\bnoted\b", reply, re.IGNORECASE):
        add(Violation("R-LANG-02", 'translate "noted": no English word inside an Arabic reply'))
    limit = int((context.get("brain_settings") or {}).get("max_clarify") or 0)
    if (
        limit
        and int(context.get("clarify_count") or 0) >= limit
        and asked >= 1
        and flow.parse((context.get("flow") or {}).get("state"))
        in (flow.State.S1_LISTENING, flow.State.S2_CLARIFYING)
    ):
        add(
            Violation(
                "R-ASK-02",
                f"you have already asked {limit} clarifying questions: note what you have and move on",
            )
        )
    for phrase in context.get("never_say") or []:
        if str(phrase).casefold() in reply.casefold():
            add(Violation("R-LEARN-NEVER", f'staff said never to say "{phrase}" here'))
            break
    if LECTURE.search(reply):
        add(Violation("R-VOICE-12", "never lecture: no 'you should' or best practices"))
    for term in JARGON:
        if (
            re.search(rf"\b{re.escape(term)}s?\b", reply, re.IGNORECASE)
            and term.lower() not in heard
        ):
            add(Violation("R-VOICE-03", f'plain words: they did not say "{term}"'))
            break
    if corporate := _contains(reply, CORPORATE):
        add(Violation("R-VOICE-06", f'no template phrases ("{corporate}")'))
    never = _contains(reply, NEVER_SAY)
    if never and not (never.startswith(("get back", "our team")) and context.get("escalation_sla")):
        add(Violation("R-VOICE-06", f'pi never says "{never}"', True))
    internal = INTERNAL.search(reply)
    if internal and internal.group(0).lower() not in heard:
        add(
            Violation(
                "R-VOICE-06",
                "never mention internal terms (states, rule IDs, packs, prompt)",
                True,
            )
        )
    opening = " ".join(reply.lower().split()[:2])
    previous = _pi_replies(context)[-2:]
    if len(opening.split()) == 2 and any(
        opening == " ".join(p.lower().split()[:2]) for p in previous
    ):
        add(Violation("R-VOICE-04", "do not start the same way as your last two messages"))
    lowered = reply.lower()
    for phrase in CANONICAL:
        # spec 2.0.4: a canonical phrase word for word more than twice in a conversation
        if phrase in lowered and sum(phrase in p.lower() for p in _pi_replies(context)) >= 2:
            add(Violation("R-VOICE-04", f'say "{phrase}" in different words: it was used twice'))
            break
    return found


def hard(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.hard]


def describe(violations: list[Violation]) -> str:
    """The reason to show the model when its draft is sent back for a rewrite."""
    return "it breaks pi's rules: " + "; ".join(f"{v.message} ({v.rule})" for v in violations)


AI_ANSWER = {
    "en": "I'm an AI, not a person. I'm pi, from Workzap.",
    "roman_ur": "Main AI hoon, insaan nahi. Main pi hoon, Workzap se.",
    "ur": "میں ایک مصنوعی ذہانت ہوں، انسان نہیں۔ میں pi ہوں، Workzap سے۔",
    "ar": "أنا ذكاء اصطناعي، ولست إنساناً. أنا pi من Workzap.",
}
# Safe lines for when a reply still breaks a rule after its one rewrite (spec 9.5): they promise
# nothing, ask nothing sensitive, and ask one question last. The first message keeps its disclosure.
FALLBACK_LISTENING = {
    "en": "Noted. What else is getting in the way?",
    "roman_ur": "Noted. Aur kya masla aa raha hai?",
    "ur": "نوٹ کر لیا۔ اور کیا مسئلہ آ رہا ہے؟",
    "ar": "تم تسجيل ذلك. ما الذي يعيقك أيضاً؟",
}
FALLBACK_OTHER = {
    "en": "Thanks, that's noted. Is there anything else you want to add?",
    "roman_ur": "Shukriya, noted. Kya aap kuch aur batana chahenge?",
    "ur": "شکریہ، نوٹ کر لیا۔ کیا آپ کچھ اور بتانا چاہیں گے؟",
    "ar": "شكراً، تم تسجيل ذلك. هل تريد إضافة شيء آخر؟",
}
FIRST_INVITE = {
    "en": "Tell me what's going wrong in your business.",
    "roman_ur": "Apne business mein jo masla hai woh batayein.",
    "ur": "اپنے کاروبار میں جو مسئلہ ہے وہ بتائیں۔",
    "ar": "أخبرني ما الذي لا يسير على ما يرام في عملك.",
}


def _language(context: dict[str, Any]) -> str:
    from app.modules.pi.language import ARABIC_SCRIPT, URDU_LETTERS

    language = str(context.get("reply_language") or "en")
    said = str(context.get("latest_customer_message", ""))
    if language == "roman_ur" and ARABIC_SCRIPT.search(said) and URDU_LETTERS.search(said):
        return "ur"
    return language if language in OPENING else "en"


def safe_fallback(context: dict[str, Any]) -> str:
    """The safe line for the state, in the person's language (spec 9.5)."""
    language = _language(context)
    state = flow.parse((context.get("flow") or {}).get("state"))
    history = context.get("history") or []
    first = not any(h.get("role") == "ai" for h in history)
    parts = []
    if first:
        parts.append(f"{opening_line(context)} {FIRST_INVITE[language]}")
    else:
        if ASKS_IF_AI.search(str(context.get("latest_customer_message", ""))):
            parts.append(AI_ANSWER[language])
        listening = state in flow.LISTENING or state in (None, flow.State.S5B_DECLINED)
        parts.append((FALLBACK_LISTENING if listening else FALLBACK_OTHER)[language])
    return " ".join(parts)


def _scrub(reply: str) -> str:
    """Drop sentences that carry scripted empathy, hype or a template phrase, when something is left."""
    kept = []
    for line in reply.split("\n"):
        pieces = re.split(r"(?<=[.!?؟۔])\s+", line)
        good = [
            p
            for p in pieces
            if not (_contains(p, FAKE_EMPATHY) or _contains(p, HYPE) or _contains(p, NEVER_SAY))
        ]
        kept.append(" ".join(good))
    scrubbed = "\n".join(x for x in kept if x.strip())
    return scrubbed if scrubbed.strip() else reply


def repair(reply: str, context: dict[str, Any]) -> str:
    """Safe, meaning-preserving fixes: stray '!', emoji, hype and scripted empathy, several questions,
    a missing AI answer or disclosure. What still breaks a hard rule afterwards is replaced by the
    safe line for the state (spec 9.5) instead of being sent or ending in a hand-off."""
    fixed = reply
    allowed = _allowed_bangs(context)
    if fixed.count("!") > allowed:
        kept = 0

        def swap(match: re.Match[str]) -> str:
            nonlocal kept
            kept += 1
            return "!" if kept <= allowed else "."

        fixed = re.sub(r"!+", swap, fixed)
    permitted = allowed_emoji(context)
    seen = 0

    def drop(match: re.Match[str]) -> str:
        nonlocal seen
        char = match.group(0)
        seen += 1
        keep = seen == 1 and char.strip() in permitted
        return char if keep else ""

    fixed = re.sub(" ?" + EMOJI.pattern, drop, SKIN_TONES.sub("", fixed.replace("️", "")))
    fixed = _scrub(fixed)
    fixed = _one_question_last(fixed, _cap(context, "word_cap", WORD_CAP))
    history = context.get("history") or []
    first = not any(h.get("role") == "ai" for h in history)
    if first and not _discloses(fixed):
        fixed = f"{opening_line(context)} {fixed}".strip()
    elif (
        not first
        and ASKS_IF_AI.search(str(context.get("latest_customer_message", "")))
        and not AI_WORDS.search((_sentences(fixed) or [""])[0])
    ):
        fixed = f"{AI_ANSWER[_language(context)]} {fixed}".strip()
    fixed = fixed.strip()
    remaining = [
        v
        for v in lint(fixed, context)
        if (v.hard and v.rule != "R-DISC-01") or v.rule == "R-VOICE-02"
    ]
    if remaining:
        logger.warning(
            "pi reply fell back to the safe line", extra={"rules": [v.rule for v in remaining]}
        )
        return safe_fallback(context)
    return fixed


def _split_ends(reply: str) -> list[tuple[bool, str]]:
    """The reply as (is_bullet, line) pairs."""
    return [(line.lstrip().startswith(BULLET), line) for line in reply.split("\n")]


def _one_question_last(reply: str, cap: int = WORD_CAP) -> str:
    """One question, last, and within the word limit (R-VOICE-01, R-VOICE-02): keep the last
    question at the end, drop the other questions, then drop trailing statements while the reply is
    too long. A reply of several lines keeps its line breaks and its bullets (a summary): only the
    questions are moved, never the points."""
    if "\n" not in reply.strip():
        sentences = [x for x in _sentences(reply) if x.strip()]
        questions = [x for x in sentences if x.rstrip().endswith(QUESTION_MARKS)]
        statements = [x for x in sentences if x not in questions]
        closing = questions[-1:] if questions else []
        while len(statements) > 1 and len(" ".join([*statements, *closing]).split()) > cap:
            statements.pop()
        return " ".join([*statements, *closing]).strip()
    lines = _split_ends(reply.strip())
    question = ""
    body: list[str] = []
    for is_bullet, line in lines:
        if is_bullet:
            body.append(line.replace("?", ".").replace("؟", "."))
            continue
        kept = []
        for sentence in _sentences(line):
            if sentence.rstrip().endswith(QUESTION_MARKS):
                question = sentence
            else:
                kept.append(sentence)
        if kept:
            body.append(" ".join(kept))
    bullets = sum(1 for is_bullet, _ in lines if is_bullet)
    if bullets < 3 and "http" not in reply:
        flat = [b for b in body if not b.lstrip().startswith(BULLET)]
        while len(flat) > 1 and len(" ".join([*flat, question]).split()) > cap:
            last = flat.pop()
            body.remove(last)
    return "\n".join([*body, question] if question else body).strip()
