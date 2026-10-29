"""The readiness signals the Solution Box offer rule reads (pi platform spec Book 5, 5.4: B3, B4,
B5, B7), derived from what the conversation really holds. Behind `response_rules.pi_mode = "brain"`
and `response_rules.brain.box_offer`: nothing here is called otherwise.

B3 (map reviewed) and B4 (ranked) persist in the conversation brief as `map_reviewed` and `ranked`,
set by the portal map edits and by the owner's reply right after a map picture; B5 comes from the
noted problems' `raised_voluntarily`; B7 from the dials when `brain.thinking` is on. Pure functions
except `previous_ai_asked`.
"""

import re
from typing import Any

from app.modules.pi import dials

RANK_PREFIX = "rank:"
MAX_RANK = 9

# "Start here" in WhatsApp: the owner says where to begin (spec 5.4 B4).
START_HERE = re.compile(
    r"\b(?:start (?:with|from|at) (?:the )?(?:first|1st|one|this|that|p\s?\d+|#?\d+)"
    r"|(?:this|that|the first) one (?:first|pehle)"
    r"|begin with (?:the )?(?:first|this|that|p\s?\d+)"
    r"|pehle (?:ye|yeh|ise|isay|is ko|pehla|p\s?\d+)|sab se pehle|sabse pehle"
    r"|(?:ye|yeh|ise|isay|pehla|pehli|p\s?\d+) (?:pehle|sab se pehle|sabse pehle)"
    r"|shuru (?:isi|is se|pehle ?se|p\s?\d+)|isi se shuru|pehle se shuru)\b",
    re.IGNORECASE,
)


def rank_of(tags: list[str] | None) -> int | None:
    """The owner's rank of a problem (1 first) from its tags, or None."""
    for tag in tags or []:
        if tag.startswith(RANK_PREFIX) and tag[len(RANK_PREFIX) :].isdigit():
            value = int(tag[len(RANK_PREFIX) :])
            if 1 <= value <= MAX_RANK:
                return value
    return None


def with_rank(tags: list[str] | None, priority: int | None) -> list[str]:
    """The tags with any rank replaced by `priority` (None clears it)."""
    kept = [t for t in tags or [] if not t.startswith(RANK_PREFIX)]
    return [*kept, f"{RANK_PREFIX}{priority}"] if priority else kept


def says_start_here(message: str) -> bool:
    return bool(START_HERE.search(" ".join((message or "").split())))


def confirms_or_changes_map(message: str) -> bool:
    """Right after a map picture: the owner confirmed it ("sahi hai", "yes that is right", "ok") or
    changed it (a correction, "P2 is wrong"). A bare question, or silence, is neither."""
    from app.modules.pi import decisions, problems

    said = " ".join((message or "").split())
    if not said:
        return False
    from app.modules.pi import map_share

    if said.casefold() in map_share.CONFIRM_TITLES:
        return True
    if decisions.summary_ok(said):
        return True
    answer, sure = decisions.classify(said)
    if answer == decisions.Answer.YES and sure >= decisions.YES_AT:
        return True
    if problems.says_wrong(said):
        return True
    # a correction ("but ...", "wrong", "reh gaya") is a change to the map
    return bool(decisions.CORRECTING.search(said)) and "?" not in said and len(said.split()) >= 3


def voluntary_count(context: dict[str, Any]) -> int:
    """Problems the owner raised on their own (B5): `raised_voluntarily` on the noted problems. A
    `voluntary_problems` number in the brief, when present, overrides."""
    brief = context.get("brief") or {}
    if brief.get("voluntary_problems") is not None:
        return int(brief["voluntary_problems"] or 0)
    return sum(1 for p in context.get("noted_problems") or [] if p.get("raised_voluntarily"))


def customer_texts(context: dict[str, Any]) -> list[str]:
    said = [
        str(h.get("text", "")) for h in context.get("history") or [] if h.get("role") == "customer"
    ]
    latest = context.get("latest_customer_message")
    if latest and (not said or said[-1] != str(latest)):
        said.append(str(latest))
    return said


# Spec v1.5, 18.3: these phrases mean trust is falling, and the offer is blocked for the next eight
# messages.
REPEAT_COMPLAINT = re.compile(
    r"i\s+already\s+(?:told|said|gave|mentioned)|already\s+told\s+you|i\s+told\s+you|"
    r"maine\s+(?:to\s+)?(?:bataya|bata\s+diya|keh\s+diya)|phir\s+se\s+(?:puch|pooch)|"
    r"bataya\s+to\s+hai|میں\s+نے\s+بتایا",
    re.IGNORECASE,
)
FALLING_QUIET_MESSAGES = 8


def repeat_complaint_recent(context: dict[str, Any]) -> bool:
    """The owner said "I already told you" (or similar) within the last eight messages."""
    history = [h for h in context.get("history") or [] if h.get("role") in ("customer", "ai")][
        -FALLING_QUIET_MESSAGES:
    ]
    texts = [str(h.get("text", "")) for h in history if h.get("role") == "customer"]
    texts.append(str(context.get("latest_customer_message") or ""))
    return any(REPEAT_COMPLAINT.search(t) for t in texts)


def trust_and_upset(context: dict[str, Any]) -> tuple[str, bool]:
    """(trust trend, upset) for B7. From the dials when `brain.thinking` is on and the owner's
    words are available; otherwise "steady" and not upset. A brief key, when present, overrides."""
    brief = context.get("brief") or {}
    trend, upset = "steady", False
    texts = customer_texts(context)
    if context.get("thinking") and texts:
        state = dials.estimate(texts)
        trend = {
            dials.Trust.FALLING: "falling",
            dials.Trust.RISING: "rising",
        }.get(state.trust_trend, "steady")
        upset = "feeling" in dials.read_signals(texts[-1], first_message=len(texts) == 1).reasons
    if repeat_complaint_recent(context):
        trend = "falling"
    if brief.get("trust_trend") is not None:
        trend = str(brief["trust_trend"])
    if brief.get("upset") is not None:
        upset = bool(brief["upset"])
    return trend, upset


async def previous_ai_asked(session: Any, conversation: Any, before: Any) -> bool:
    """Whether pi's last message before `before` (a datetime) ended in a question."""
    from sqlalchemy import select

    from app.modules.pi.models import PiMessage

    body = await session.scalar(
        select(PiMessage.body)
        .where(
            PiMessage.tenant_id == conversation.tenant_id,
            PiMessage.environment_id == conversation.environment_id,
            PiMessage.conversation_id == conversation.id,
            PiMessage.sender_type == "ai",
            PiMessage.created_at < before,
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    return (body or "").rstrip().endswith(("?", "؟"))
