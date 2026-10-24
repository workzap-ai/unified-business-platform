# ruff: noqa: E501  (the reply texts read better on one line each)
"""The offer and the decision gates (pi Brain spec 3.8, 5.5, 5.6, 6.4): reading a person's answer
and choosing pi's fixed reply, the next state and what happens next.

Deterministic on purpose. An explicit yes never comes from a model's judgement: `classify` reads
the words (and button titles) in English, Roman Urdu, Urdu and Arabic, and only an explicit yes
at 0.9 or more moves the conversation (R-OFFER-03). `decide` is pure: it takes the state, the
person's message and a few facts, and returns the reply, the move and the effects, or None when
the model should answer (a question, a correction, a cost question).
"""

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from app.modules.pi.flow import State

YES_AT = 0.9  # an explicit yes needs this much confidence to start anything


class Answer(StrEnum):
    YES = "explicit_yes"
    NO = "no"
    LATER = "later"
    UNCLEAR = "unclear"


YES_WORDS = (
    r"yes|yeah|yep|yup|yess+|sure|of course|please do|go ahead|go for it|do it|"
    r"haan|han|haa|ji|ji haan|ji han|jee|theek hai|thik hai|theek|bilkul|zaroor|zarur|"
    r"kar do|kardo|bhej do|bana do|bana dein|bhej dein|kar dein|"
    r"نعم|ايوه|أيوه|اي|أكيد|تمام|جي|جی|ہاں|ٹھیک ہے|ٹھیک|بالکل|کر دیں|کر دو|"
    r"👍|✅|🙏"
)
NO_WORDS = (
    r"no|nope|nah|no thanks|no thank you|not interested|don'?t|do not|nahi|nahin|nai|na|"
    r"nahi shukriya|nahi chahiye|mat karo|mat banao|لا|لا شكرا|لا شكرًا|نہیں|نہیں شکریہ|"
    r"نہیں چاہیے|👎"
)
LATER_WORDS = (
    r"later|not now|maybe later|some other time|baad mein|baad me|abhi nahi|abhi nhi|"
    r"phir kabhi|kal baat karte|ليس الآن|لاحقا|لاحقًا|بعد|ابھی نہیں|بعد میں"
)
HEDGE = re.compile(
    r"\b(?:ok|okay|hmm+|hm+|maybe|perhaps|let me think|i'll think|will think|sochta|sochti|"
    r"soch(?:ta|ti)? hoon|dekhte hain|dekhta hoon|dekhti hoon|not sure)\b|\?|؟"
    r"|\b(?:how much|kitna|qeemat|price|cost|but|lekin|magar|if|agar)\b",
    re.IGNORECASE,
)
_YES = re.compile(rf"^\W*(?:(?:{YES_WORDS})\W*){{1,3}}$", re.IGNORECASE)
_YES_LEAD = re.compile(rf"^\W*(?:{YES_WORDS})\b", re.IGNORECASE)
_YES_REQUEST = re.compile(
    r"(?:document|quote|quotation|proposal|solution).*(?:bana|banwa|bhej|send|prepare|make|create|dein|den|do)"
    r"|(?:bana|banwa|bhej|send|prepare|make|create).*(?:document|quote|quotation|proposal|solution)",
    re.IGNORECASE,
)
_NO = re.compile(rf"^\W*(?:{NO_WORDS})\W*$", re.IGNORECASE)
_NO_LEAD = re.compile(rf"^\W*(?:{NO_WORDS})\b", re.IGNORECASE)
_LATER = re.compile(rf"\b(?:{LATER_WORDS})\b|(?:{LATER_WORDS})", re.IGNORECASE)
# Acknowledging the summary ("looks right", "theek hai"): not a yes to the offer, but enough
# to move on from it (R-OFFER-01).
SUMMARY_OK = re.compile(
    r"^\W*(?:ok(?:ay)?|fine|good|great|right|correct|that'?s (?:right|correct|fine|all)|"
    r"looks? (?:good|right|fine)|all good|nothing (?:is )?(?:wrong|missing)|sahi hai|theek hai|"
    r"thik hai|bilkul sahi|ji|ji haan|haan|han|yes|yeah|sab theek|sab sahi|ٹھیک ہے|صحيح|تمام|👍|✅)"
    r"[\W\w]{0,24}$",
    re.IGNORECASE,
)
# A "but" after the acknowledgement means something is still wrong or missing: not a confirmation.
CORRECTING = re.compile(
    r"\b(?:but|however|except|lekin|magar|par|wrong|missing|ghalat|reh gaya|raha)\b|\?|غلط|لكن",
    re.IGNORECASE,
)


def summary_ok(message: str) -> bool:
    """The person accepted the summary as it stands (not "ok but P2 is wrong")."""
    said = " ".join(message.split())
    return bool(SUMMARY_OK.match(said)) and not CORRECTING.search(said)


ALL = re.compile(
    r"\b(?:all|everything|all of (?:them|these)|sab|sab kuch|saare|sare|sabhi|the whole list)\b|"
    r"كل|الجميع|سب|سارے",
    re.IGNORECASE,
)
OFFER_REQUEST = re.compile(
    r"\b(?:send|give|prepare|make)\b.{0,20}\b(?:document|quote|quotation|proposal)\b|"
    r"\bi(?: do)? want\b.{0,20}\b(?:document|quote)\b|\b(?:document|quote)\b.{0,12}"
    r"\b(?:please|chahiye|bhej|bana)\b",
    re.IGNORECASE,
)
APPROVE = re.compile(
    r"^\W*(?:approve|approved|i approve|approve it|approve the quote|go ahead with the quote|"
    r"manzoor(?: hai)?|منظور(?: ہے)?|موافق|أوافق)\W*$",
    re.IGNORECASE,
)
CHANGES = re.compile(
    r"^\W*(?:ask for changes|changes|i want changes|change it|badlav|tabdeeli(?: chahiye)?|"
    r"changes chahiye|تبدیلی|تعديل|أريد تعديلات|طلب تعديلات)\W*$",
    re.IGNORECASE,
)
SAY_NO = re.compile(
    r"^\W*(?:say no|no(?: thanks| thank you)?|nope|nahi(?: shukriya)?|nahin(?: shukriya)?|لا|نہیں)\W*$",
    re.IGNORECASE,
)
# "I paid", "done", "transfer kar diya": a claim, never proof (R-PAY-06). Questions are not claims.
PAID = re.compile(
    r"\b(?:i(?:'ve| have)? (?:paid|sent|transferred)|(?:paid|sent|transferred)(?: it)?(?: already)?|"
    r"payment (?:done|made|sent)|done|transfer (?:kar|ho) (?:diya|gaya|di|gayi)|payment "
    r"(?:kar|ho) (?:di|gayi|diya)|paise (?:bhej|send) (?:diye|diya)|bhej diya|ho gaya)\b",
    re.IGNORECASE,
)

CANCEL = re.compile(
    r"\b(?:cancel|cancel it|call it off|i don'?t want it anymore|band karo|mujhe nahi chahiye|"
    r"mat banao)\b|ردّ|إلغاء|منسوخ",
    re.IGNORECASE,
)

OFFER_BUTTONS = {
    "en": ["Yes, please", "No thanks", "Not now"],
    "roman_ur": ["Haan, bana dein", "Nahi shukriya", "Abhi nahi"],
    "ar": ["نعم، من فضلك", "لا شكرًا", "ليس الآن"],
}
DECISION_BUTTONS = {
    "en": ["Approve", "Ask for changes", "Say no"],
    "roman_ur": ["Manzoor hai", "Tabdeeli chahiye", "Nahi"],
    "ar": ["أوافق", "طلب تعديلات", "لا"],
}
assert all(len(t) <= 20 for b in (*OFFER_BUTTONS.values(), *DECISION_BUTTONS.values()) for t in b)

TEXT: dict[str, dict[str, str]] = {
    "offer": {
        "en": (
            "Would you like a solution document and a quote for these? You can say no. "
            "The document sets out what Workzap would build, in plain words. The quote says "
            "what it would cost and how long it would take. It's an offer, not a charge."
        ),
        "roman_ur": (
            "Kya aap in sab ke liye solution document aur quote chahenge? Aap mana bhi kar "
            "sakte hain. Document mein likha hota hai ke Workzap kya banayega, aasan lafzon "
            "mein. Quote mein kharcha aur waqt hota hai. Ye ek offer hai, charge nahi."
        ),
    },
    "ask_all_or_some": {
        "en": "Should it cover all of these, or only some?",
        "roman_ur": "Kya ye sab ke liye ho, ya sirf kuch ke liye?",
    },
    "confirm_go": {
        "en": "Shall I go ahead and ask Workzap to prepare them?",
        "roman_ur": "Kya main Workzap se inhe tayyar karne ko keh dun?",
    },
    "preparing": {
        "en": (
            "Thanks. I've asked Workzap to prepare your solution document and quote. "
            "I'll send them here once they're ready."
        ),
        "roman_ur": (
            "Shukriya. Maine Workzap se aap ka solution document aur quote tayyar karne ko "
            "keh diya hai. Tayyar hote hi yahin bhej dunga."
        ),
    },
    "declined": {
        "en": "No problem. Everything you've told me is kept here if you change your mind.",
        "roman_ur": "Koi baat nahi. Jo aap ne bataya hai wo yahin mehfooz hai, agar ray badle.",
    },
    "later": {
        "en": "No rush. I'll keep what you've told me. Come back whenever.",
        "roman_ur": "Koi jaldi nahi. Jo aap ne bataya hai wo mehfooz hai. Jab marzi wapas aayein.",
    },
    "re_offer": {
        "en": "Sure. Shall I ask Workzap to prepare the solution document and quote for these?",
        "roman_ur": "Zaroor. Kya main Workzap se in ke liye solution document aur quote banwa dun?",
    },
    "member": {
        "en": (
            "I can note that you'd like one. The owner of {business} needs to say yes to a "
            "quote, and they can message me directly at workzap.ai/pi/talk-to-pi."
        ),
        "roman_ur": (
            "Main note kar leta hoon ke aap ye chahte hain. {business} ke owner ko quote par "
            "haan kehna hoga, wo mujhe seedha workzap.ai/pi/talk-to-pi par message kar sakte hain."
        ),
    },
    "member_ask": {
        "en": (
            "I can note that you'd like one. The owner of {business} needs to say yes to a "
            "quote, and they can message me directly at workzap.ai/pi/talk-to-pi, or I can "
            "give you that link to pass on. Should the decision-maker receive the document, "
            "and how would you like to involve them?"
        ),
        "roman_ur": (
            "Main note kar leta hoon ke aap ye chahte hain. {business} ke owner ko quote par "
            "haan kehna hoga, wo mujhe seedha workzap.ai/pi/talk-to-pi par message kar sakte "
            "hain, ya main wo link aap ko de dun. Kya document faisla karne wale ko bhejna "
            "chahiye, aur aap unhein kaise shamil karna chahenge?"
        ),
    },
    "confirm_approval": {
        "en": "Just to confirm: you approve quote {quote} for {total}. Is that right?",
        "roman_ur": "Bas confirm karne ke liye: aap quote {quote} {total} ke liye manzoor karte hain. Theek hai?",
    },
    "approved": {
        "en": (
            "Thanks. To start, payment is by bank transfer. The bank details are on your "
            "approved quote. Workzap will confirm here when the transfer arrives. Please "
            "don't send card details or payment in this chat."
        ),
        "roman_ur": (
            "Shukriya. Shuru karne ke liye payment bank transfer se hoti hai. Bank details "
            "aap ke approved quote par hain. Transfer aane par Workzap yahin confirm karega. "
            "Meherbani karke is chat mein card ki details ya payment na bhejein."
        ),
    },
    "approval_dropped": {
        "en": "Okay, I haven't approved anything. Would you like to approve, ask for changes, or say no?",
        "roman_ur": "Theek hai, maine kuch manzoor nahi kiya. Aap manzoor karna chahenge, tabdeeli maangenge, ya nahi kahenge?",
    },
    "changes": {
        "en": "What would you like changed?",
        "roman_ur": "Aap kya badalna chahte hain?",
    },
    "changes_noted": {
        "en": "Noted: {changes}. I've sent this to Workzap. They'll send a revised version here.",
        "roman_ur": "Note kar liya: {changes}. Maine ye Workzap ko bhej diya hai. Wo yahin nayi version bhejenge.",
    },
    "quote_declined": {
        "en": (
            "That's fine. Nothing is charged. Everything you told me stays here if you want "
            "to come back to it. If you'd like to say why, it helps Workzap, but you don't "
            "have to."
        ),
        "roman_ur": (
            "Koi baat nahi. Kuch charge nahi hoga. Jo aap ne bataya hai wo yahin rahega. "
            "Agar wajah batana chahein to Workzap ke liye madadgar hai, lekin zaroori nahi."
        ),
    },
    "payment_claimed": {
        "en": "Thanks. The Workzap team will confirm here when the transfer arrives.",
        "roman_ur": "Shukriya. Transfer aane par Workzap ki team yahin confirm karegi.",
    },
    "payment_confirmed": {
        "en": (
            "Workzap has confirmed your transfer. Thank you. To start, shall we book a kickoff "
            "call to agree the details?"
        ),
        "roman_ur": (
            "Workzap ne aap ka transfer confirm kar diya hai. Shukriya. Shuru karne ke liye kya "
            "hum tafseelat tay karne ke liye kickoff call book karein?"
        ),
    },
    "expired_quote": {
        "en": "That quote is past its valid-until date, so it can't be approved as it stands. I've asked Workzap to send a refreshed one.",
        "roman_ur": "Is quote ki valid-until tareekh guzar chuki hai, isliye ye is haal mein approve nahi ho sakta. Maine Workzap se naya quote bhejne ko kaha hai.",
    },
    "after_payment": {
        "en": "I'll pass this to the Workzap team now. They'll reply here.",
        "roman_ur": "Ye Workzap ki team ko bhej diya gaya hai. Wo yahin jawab dein ge.",
    },
    "cancelled": {
        "en": "That's fine. Nothing is charged. I've told Workzap.",
        "roman_ur": "Koi baat nahi. Kuch charge nahi hoga. Maine Workzap ko bata diya hai.",
    },
}


# The reminder permission question, word for word as service_conversation.CONSENT_QUESTION (a test
# keeps them equal): the document and paused follow-ups go out after the 24-hour window, which is
# only allowed with this yes (spec 3.9.1). Asked when the offer is accepted or the person says
# "later", the two moments a follow-up can start.
CONSENT_ASK = {
    "en": "Can I message you here when there's an update, or if we need anything from you?",
    "roman_ur": "Kya hum aap ko yahan message kar sakte hain jab koi update ho, ya hamein "
    "aap se kuch chahiye ho?",
}


def text(key: str, language: str | None, **values: str) -> str:
    options = TEXT[key]
    return options.get(language or "en", options["en"]).format(**values)


def with_consent(reply: str, language: str | None, facts: dict[str, Any]) -> str:
    """Add the reminder permission question to a fixed reply, once, when it is still unknown."""
    if not facts.get("ask_consent") or "?" in reply:
        return reply
    return f"{reply.rstrip()} {CONSENT_ASK.get(language or 'en', CONSENT_ASK['en'])}"


def buttons_for(body: str) -> list[str] | None:
    """The quick-reply buttons for pi's offer or decision message, from the text it ends with."""
    ending = body.rstrip()
    for language, label in ((lang, TEXT["offer"][lang]) for lang in TEXT["offer"]):
        if ending.endswith(label[-40:]):
            return OFFER_BUTTONS[language]
    for language in TEXT["confirm_go"]:
        if ending.endswith(TEXT["confirm_go"][language]) or ending.endswith(
            TEXT["re_offer"][language]
        ):
            return OFFER_BUTTONS[language]
    return None


def classify(message: str) -> tuple[Answer, float]:
    """An answer to a yes/no question, with how sure we are. Only a short, plain yes counts as an
    explicit yes: "ok", "hmm", "maybe", "let me think", questions and hedged answers do not."""
    said = " ".join((message or "").split())
    if not said:
        return Answer.UNCLEAR, 0.0
    if _LATER.search(said) and len(said.split()) <= 8:
        return Answer.LATER, 0.95
    if _NO.match(said):
        return Answer.NO, 0.97
    if _NO_LEAD.match(said) and len(said.split()) <= 6 and not HEDGE.search(said):
        return Answer.NO, 0.92
    core = re.sub(r"^\W*ok(?:ay)?\W+", "", said, flags=re.IGNORECASE)
    if core != said and _YES.match(core):
        return Answer.YES, 0.95  # "okay go ahead" is a yes; "ok" alone is not
    if HEDGE.search(said) and not _YES.match(said):
        return Answer.UNCLEAR, 0.5
    if _YES.match(said):
        return Answer.YES, 0.97
    if _YES_LEAD.match(said) and len(said.split()) <= 4:
        return Answer.YES, 0.92
    if _YES_LEAD.match(said) and len(said.split()) <= 10 and _YES_REQUEST.search(said):
        return (
            Answer.YES,
            0.92,
        )  # "haan document aur quote bana dein": a yes that asks for the offer
    return Answer.UNCLEAR, 0.4


@dataclass
class Decision:
    """What to do with an answer: pi's fixed reply (None = let the model answer), the move,
    changes to the conversation brief, and effects for the application to perform."""

    reply: str | None = None
    next_state: State | None = None
    brief: dict[str, Any] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)
    why: str = ""


def _ok(answer: tuple[Answer, float], wanted: Answer) -> bool:
    return answer[0] == wanted and answer[1] >= YES_AT


def decide(
    state: State,
    message: str,
    language: str | None,
    facts: dict[str, Any],
) -> Decision | None:
    """The fixed reply and move for the person's message in this state, or None.

    facts: message_id, can_approve, business, problem_count, group_count, problem_refs,
    chosen_refs (the model's pick when they answered "only some"), changed (the model
    changed or added problems this turn), brief, open_quote ({"id", "total"} or None).
    """
    brief = facts.get("brief") or {}
    can_approve = facts.get("can_approve", True)
    answer = classify(message)

    if (
        not can_approve
        and OFFER_REQUEST.search(message)
        and state
        in (State.S3_NOTED, State.S4_SORTED_SUMMARY, State.S5_READINESS, State.S5B_DECLINED)
    ):
        return _member(language, facts, brief)  # "send the quote" from a non-decider (R-OFFER-06)

    if state == State.S4_SORTED_SUMMARY:
        if facts.get("changed") or not facts.get("problem_count"):
            return None
        if summary_ok(message) or (_ok(answer, Answer.YES) and not CORRECTING.search(message)):
            return Decision(
                text("offer", language),
                State.S5_READINESS,
                {"offer_asked": True},
                why="R-OFFER-01",
            )
        return None

    if state == State.S5_READINESS:
        if facts.get("changed"):
            return None
        if brief.get("scope_asked") and not brief.get("scope_done"):
            refs = list(facts.get("chosen_refs") or [])
            if ALL.search(message) and not refs:
                refs = list(facts.get("problem_refs") or [])
            if refs:
                return _prepare(
                    language, facts, refs, {"scope_done": True}, brief.get("offer_yes_id")
                )
            if _ok(answer, Answer.NO):
                return _decline(language)
            return None
        if _ok(answer, Answer.NO):
            return _decline(language)
        if _ok(answer, Answer.LATER):
            return Decision(
                with_consent(text("later", language), language, facts),
                State.X_PAUSED,
                {"paused_from": State.S5_READINESS.value},
                why="later",
            )
        if _ok(answer, Answer.YES):
            if not can_approve:
                return _member(language, facts, brief)
            if int(facts.get("group_count") or 0) >= 2 and not brief.get("scope_asked"):
                return Decision(
                    text("ask_all_or_some", language),
                    None,
                    {"scope_asked": True, "offer_yes_id": facts.get("message_id")},
                    why="R-OFFER-04",
                )
            return _prepare(language, facts, list(facts.get("problem_refs") or []), {})
        stripped = " ".join(message.split())
        if (
            not brief.get("yes_asked")
            and HEDGE.search(stripped)
            and "?" not in stripped
            and "؟" not in stripped
            and not re.search(
                r"\b(?:how much|kitna|price|cost|qeemat|but|lekin|magar)\b", stripped, re.I
            )
        ):
            return Decision(
                text("confirm_go", language), None, {"yes_asked": True}, why="R-OFFER-03"
            )
        return None

    if state == State.S5B_DECLINED:
        if OFFER_REQUEST.search(message):
            return Decision(
                text("re_offer", language), State.S5_READINESS, {"yes_asked": True}, why="raised"
            )
        return None

    if state == State.S8B_CHANGES_REQUESTED and facts.get("change_requests"):
        changes = [str(x) for x in facts["change_requests"]]
        return Decision(
            text("changes_noted", language, changes="; ".join(changes)),
            None,
            {"revision_requested": {"changes": changes, "message_id": facts.get("message_id")}},
            ["request_revision"],
            why="R-DEC-03",
        )
    quote = facts.get("open_quote")
    if state == State.S8_REVIEW and quote:
        return _review(language, message, answer, facts, quote, brief, can_approve)

    if state in (State.S11_PAYMENT_CONFIRMED, State.S12_KICKOFF) and CANCEL.search(message):
        return Decision(
            text("after_payment", language),
            None,
            {"escalate": "cancel_after_payment"},
            ["escalate"],
            why="R-DEC-05",
        )
    if state == State.S9_APPROVED and CANCEL.search(message):
        return Decision(
            text("cancelled", language),
            State.S9B_DECLINED_QUOTE,
            {},
            ["cancel_before_payment"],
            why="R-DEC-05",
        )
    if state == State.S10_AWAITING_PAYMENT:
        if CANCEL.search(message):
            return Decision(
                text("cancelled", language),
                State.S9B_DECLINED_QUOTE,
                {},
                ["cancel_before_payment"],
                why="R-DEC-05",
            )
        pictured = facts.get("message_kind") in ("image", "document")
        asked = "?" in message or "؟" in message
        if pictured or (PAID.search(message) and not asked):
            return Decision(
                text("payment_claimed", language),
                None,
                {},
                ["payment_claimed"],
                why="R-PAY-06",
            )
    if state == State.S11_PAYMENT_CONFIRMED and brief.get("payment_notice_due"):
        return Decision(
            text("payment_confirmed", language),
            None,
            {"payment_notice_due": None},
            why="R-KICK-01",
        )
    return None


def _member(language: str | None, facts: dict[str, Any], brief: dict[str, Any]) -> Decision:
    """A person who is not the decision-maker asks for the document or says yes to it
    (R-OFFER-06, spec 4.9): pi notes it, says the owner must say yes, and asks once whether the
    decision-maker should receive the document and how they would like to involve them, without
    asking for that person's number."""
    business = facts.get("business") or "your business"
    key = "member" if brief.get("non_decider_asked") else "member_ask"
    return Decision(
        text(key, language, business=business),
        None,
        {"offer_wanted_by_member": True, "non_decider_asked": True},
        why="R-OFFER-06",
    )


# A person who is not the one who decides (spec 2.6, 4.9): "I work at ...", "my boss decides",
# "I'm not the owner". Conservative on purpose: an owner is never silently demoted.
NON_DECIDER = re.compile(
    r"\bi(?:'m| am)? (?:only |just )?work(?:ing)? (?:at|for|in)\b(?![^.?!\n]{0,20}\b(?:my own|my)\b)"
    r"|\b(?:my|our) (?:boss|manager|owner|director|ceo|md|supervisor|superior|principal)\b"
    r"[^.?!\n]{0,50}\b(?:decides?|decision|asked me|told me|sent me|wants|will decide|approves?|"
    r"has to approve|needs to approve|has to say yes)\b"
    r"|\b(?:boss|owner|manager|director|ceo) (?:decides|will decide|has to decide|approves)\b"
    r"|\bi(?:'m| am) not (?:the |an? )?(?:owner|decision[- ]?maker|boss|authori[sz]ed)\b"
    r"|\bnot (?:my|up to me)\b[^.?!\n]{0,12}\bdecision\b|\bit(?:'s| is) not my decision\b"
    r"|\bi(?:'m| am) (?:just )?(?:an? |the )?(?:employee|staff member|team member|intern|"
    r"receptionist|assistant|accountant)\b"
    r"|\b(?:mere|hamare|meri|hamari) (?:boss|malik|sahab|manager|owner)\b[^.?!\n]{0,50}"
    r"\b(?:decide|faisla|poochna|puchna|kehte|batayenge|manzoori)\b"
    r"|\b(?:malik|boss|sahab) se (?:poochna|puchna|pooch)\b"
    r"|مديري|رئيسي في العمل|صاحب الشركة هو من يقرر",
    re.IGNORECASE,
)


def non_decider(message: str) -> bool:
    """The person says they are not the one who decides (R-OFFER-06)."""
    return bool(NON_DECIDER.search(" ".join((message or "").split())))


def _decline(language: str | None) -> Decision:
    return Decision(
        text("declined", language), State.S5B_DECLINED, {"offer_declined": True}, why="R-SELL-05"
    )


def _prepare(
    language: str | None,
    facts: dict[str, Any],
    refs: list[str],
    extra: dict[str, Any],
    yes_id: str | None = None,
) -> Decision:
    return Decision(
        with_consent(text("preparing", language), language, facts),
        State.S6_PREPARING,
        {
            **extra,
            "offer": {
                "yes_message_id": yes_id or facts.get("message_id"),
                "confirm_message_id": facts.get("message_id"),
                "problem_refs": refs,
            },
        },
        ["request_solution"],
        why="R-OFFER-03",
    )


def _expired(quote: dict[str, Any]) -> bool:
    """The quote's own valid-until date has passed."""
    raw = quote.get("valid_until")
    try:
        return bool(raw) and date.fromisoformat(str(raw)[:10]) < date.today()
    except ValueError:
        return False


def _review(
    language: str | None,
    message: str,
    answer: tuple[Answer, float],
    facts: dict[str, Any],
    quote: dict[str, Any],
    brief: dict[str, Any],
    can_approve: bool,
) -> Decision | None:
    pending = brief.get("approval_pending")
    if pending and pending.get("quote") == quote.get("id"):
        if _ok(answer, Answer.YES) and can_approve:
            return Decision(
                text("approved", language),
                State.S10_AWAITING_PAYMENT,  # approved, and the bank-transfer step is explained
                {
                    "approval_pending": None,
                    "approval": {
                        "quote": quote.get("id"),
                        "confirm_message_ids": [pending.get("message_id"), facts.get("message_id")],
                    },
                },
                ["record_approval"],
                why="R-DEC-01",
            )
        return Decision(
            text("approval_dropped", language), None, {"approval_pending": None}, why="R-DEC-01"
        )
    stripped = " ".join(message.split())
    if (APPROVE.match(stripped) or _ok(answer, Answer.YES)) and _expired(quote):
        return Decision(
            text("expired_quote", language),
            None,
            {"escalate": "quote_expired"},
            ["escalate"],
            why="R-QUOTE-05",
        )
    if APPROVE.match(stripped):
        if not can_approve:
            return Decision(
                text("member", language, business=facts.get("business") or "your business"),
                None,
                {},
                why="R-DEC-02",
            )
        return Decision(
            text(
                "confirm_approval",
                language,
                quote=str(quote.get("id")),
                total=str(quote.get("total")),
            ),
            None,
            {"approval_pending": {"quote": quote.get("id"), "message_id": facts.get("message_id")}},
            why="R-DEC-01",
        )
    if CHANGES.match(stripped):
        return Decision(text("changes", language), State.S8B_CHANGES_REQUESTED, {}, why="R-DEC-03")
    if SAY_NO.match(stripped):
        return Decision(
            text("quote_declined", language), State.S9B_DECLINED_QUOTE, {}, why="R-DEC-04"
        )
    return None


# --- "how much would it cost?" before any offer (R-OFFER-05, golden G9) ---------------------------

COST_ASKED = re.compile(
    r"\b(?:how much|kitna|kitni|kharcha|kharch|qeemat|price|cost|charges?)\b",
    re.IGNORECASE,
)
COST_ANSWER = {
    "en": (
        "The cost depends on what would be built. It is written on the quote before you decide, "
        "and the quote is free, not a charge."
    ),
    "roman_ur": (
        "Kharcha is par depend karta hai ke kya banaya jaye. Woh quote par likha hota hai, aap ke "
        "faisle se pehle, aur quote muft hai, koi charge nahi."
    ),
}


def cost_asked(text: str) -> bool:
    return bool(COST_ASKED.search(text or ""))


def cost_answer(language: str | None) -> str:
    """An honest answer with no figure and no range, given before the summary or the offer."""
    return COST_ANSWER["roman_ur"] if language == "roman_ur" else COST_ANSWER["en"]
