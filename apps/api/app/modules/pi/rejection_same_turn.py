# ruff: noqa: E501  (long regexes read better on one line)
"""An idea the owner turns down is written to the rejection ledger in the SAME turn.

Until now `pi_rejections` was filled only by the nightly scoring run, so the idea filter could offer
a rejected idea again the next day, or in the next message. This module reads the owner's message
against pi's previous reply and, when the message clearly rejects or withdraws ONE specific idea
pi offered there (rule G7), writes it through `memory_ledger.record_rejection` (the single writer)
with the owner's own words as evidence. A later take-back ("actually yes", "chalo wahi karte
hain") reverses it through `memory_ledger.reverse_rejections` (the row is kept).

Conservative by design:
* a bare "ok", "hmm" or "no" with no target is not a rejection;
* pi's previous reply must have listed ideas (`solution_rules.idea_items`); with two listed ideas
  the owner must point at one (first, second, number 2); otherwise nothing is recorded;
* only brain mode writes (`memory_ledger.brain_on`); the ledger never stops a reply.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi import memory_ledger, solution_rules, solution_score
from app.modules.pi.memory_models import PiRejection

logger = logging.getLogger(__name__)

KEY_PREFIX = "said:"  # target_key of a rejection written in chat (the nightly writer uses arm keys)
_SIGNALS = frozenset({"idea_not_possible", "idea_generic", "idea_no_help", "idea_already_doing"})

_REJECT = re.compile(
    r"(?:\bno\b[\s,.!-]+not (?:that|this)\b|\bnot (?:that|this) (?:one|idea)\b|\bnot that\b|"
    r"\b(?:that|this|it) (?:won'?t|will not|wouldn'?t|doesn'?t|does not) work\b|"
    r"\b(?:that|this) (?:is not|isn'?t) (?:for us|possible|going to work|right for us)\b|"
    r"\bnot (?:for us|going to work)\b|\bwe can'?t do (?:that|this)\b|\bi don'?t want (?:to do )?(?:that|this)\b|"
    r"\b(?:another|different|other) (?:one|idea)\b|\bgive me (?:another|a different)\b|"
    r"\b(?:du+sra|do+sra|koi aur|aur koi) (?:batao|bataiye|btao|dein|do|idea)\b|\bye wala nahi\b|"
    r"\b(?:ye|yeh|wo|woh) (?:wala )?(?:nahi|nahin|nhi)\b|\b(?:ye|yeh) (?:nahi|nahin|nhi) (?:hoga|chalega|chal sakta)\b|"
    r"\bye (?:hum|humare|hamare) (?:se|liye) nahi\b|"
    r"یہ نہیں|یہ نہیں ہو سکتا|ہم سے نہیں ہوگا|کوئی اور (?:بتائیں|بتاؤ|آئیڈیا)|دوسرا (?:بتائیں|بتاؤ|آئیڈیا)|"
    r"لا يناسبنا|هذا لا يناسب|لا يصلح لنا|غير مناسب|ما بيناسب|مش مناسب|هذا لا|فكرة (?:ثانية|أخرى|اخرى)|غير هذا)",
    re.IGNORECASE,
)
_TAKE_BACK = re.compile(
    r"(?:\bactually[, ]+(?:yes|ok|okay|that'?s (?:fine|good|ok)|let'?s)\b|\bi (?:changed|change) my mind\b|"
    r"\blet'?s (?:do|try) (?:that|it|the (?:first|second))\b|\bokay? (?:let'?s )?(?:do|try) (?:that|it)\b|"
    r"\b(?:chalo|acha|achha|theek hai)[, ]+(?:wahi|wohi|ye|yeh|wo) (?:karte|try|kar)\b|"
    r"\bwahi (?:theek|sahi) (?:hai|tha)\b|\bmain (?:ye|wo|wahi) (?:try )?karunga\b|"
    r"\bi(?:'ll| will) (?:try|do) (?:that|it)\b|بدلت رأيي|خلينا نجرب|ٹھیک ہے وہی|چلو وہی)",
    re.IGNORECASE,
)
_ORDINALS = (
    (
        re.compile(
            r"\b(?:the )?(?:first|1st|pehla|pehli|pahla|pahli)(?: (?:one|idea|wala|wali))?\b", re.I
        ),
        0,
    ),
    (
        re.compile(
            r"\b(?:the )?(?:second|2nd)(?: (?:one|idea))?\b|\b(?:doosra|dusra) (?:wala|wali)\b",
            re.I,
        ),
        1,
    ),
    (re.compile(r"\b(?:number|no\.?|idea|#) ?1\b", re.I), 0),
    (re.compile(r"\b(?:number|no\.?|idea|#) ?2\b", re.I), 1),
)


@dataclass(frozen=True)
class Detected:
    idea_text: str
    owner_words: str
    reason: str


def rejects(text: str) -> bool:
    """True when the words clearly turn an idea down (never a bare ok, hmm or no)."""
    said = " ".join((text or "").split())
    if not said or _TAKE_BACK.search(said):
        return False
    reaction = solution_score.classify(said)
    if reaction is not None and reaction.signal in _SIGNALS:
        return True
    return bool(_REJECT.search(said))


def takes_back(text: str) -> bool:
    return bool(_TAKE_BACK.search(" ".join((text or "").split())))


def detect(owner_text: str, previous_reply: str) -> Detected | None:
    """The one idea of `previous_reply` that `owner_text` rejects, or None (nothing, or unclear)."""
    if not rejects(owner_text):
        return None
    items = [
        " ".join(i.split()) for i in solution_rules.idea_items(previous_reply or "") if i.strip()
    ]
    if not items:
        return None
    if len(items) == 1:
        return Detected(items[0], owner_text, "owner rejected the idea in chat")
    picked = {n for pattern, n in _ORDINALS if pattern.search(owner_text) and n < len(items)}
    if len(picked) != 1:
        return None  # which idea is unclear: record nothing
    return Detected(items[picked.pop()], owner_text, "owner rejected the idea in chat")


def key_of(idea_text: str) -> str:
    return KEY_PREFIX + memory_ledger.idea_hash(idea_text)[:24]


async def record_same_turn(
    session: Any,
    scope: Any,
    *,
    customer_id: UUID | None,
    message: Any,
    previous_reply: str,
    response_rules: dict[str, Any] | None,
) -> str:
    """Write or reverse a rejection for this turn. Returns "rejected", "reversed" or "". Never
    raises; brain mode only."""
    if customer_id is None or message is None or not memory_ledger.brain_on(response_rules):
        return ""
    text = str(getattr(message, "body", "") or "")
    if not text.strip():
        return ""
    try:
        if takes_back(text):
            live = list(
                await session.scalars(
                    select(PiRejection).where(
                        PiRejection.tenant_id == scope.tenant_id,
                        PiRejection.environment_id == scope.environment_id,
                        PiRejection.customer_id == customer_id,
                        PiRejection.target_kind == "idea",
                        PiRejection.status == "active",
                        PiRejection.target_key.like(KEY_PREFIX + "%"),
                    )
                )
            )
            said_again = [
                r
                for r in live
                if r.idea_text and r.idea_text.lower() in (previous_reply or "").lower()
            ]
            target = said_again or (live if len(live) == 1 else [])
            done = 0
            for row in target:
                done += await memory_ledger.reverse_rejections(
                    session,
                    scope,
                    customer_id=customer_id,
                    target_kind="idea",
                    target_key=row.target_key,
                )
            return "reversed" if done else ""
        found = detect(text, previous_reply)
        if found is None:
            return ""
        row = await memory_ledger.record_rejection(
            session,
            scope,
            customer_id=customer_id,
            target_kind="idea",
            target_key=key_of(found.idea_text),
            idea_text=found.idea_text,
            owner_words=found.owner_words,
            reason=found.reason,
            source_message_id=getattr(message, "id", None),
        )
        return "rejected" if row is not None else ""
    except Exception:  # noqa: BLE001 - the ledger never stops a reply
        logger.warning("pi_same_turn_rejection_failed", exc_info=True)
        return ""
