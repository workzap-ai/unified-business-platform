"""S4 (B6 root cause 1): what an owner's earlier chat hands to a new one.

A new conversation starts with an empty brief, so a questions pi was answered in the last chat was
asked again. This copies, once, into the new conversation only:

* `closed_slots`: pi's own questions the owner answered (the question text, never the answer);
* `asked_facts`: the facts pi asked for and got no answer to, for a short while only.

The owner's open items (a question or request still open, redacted, up to 30 days old) are moved
into the new chat by `open_items.carry_into`, called from here; see that function for the rules.

Never copied: anything else the owner wrote, the summary, requirements, the profile, the open
question, the generic "anything else?" slot, a question that holds personal data, anything older
than the window, anything from an erased chat, anything from another workspace or another
customer. A copy is marked `carried`. `brain_erase.erase_customer` finds every conversation of the
customer, so it erases the copies with the rest.
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import memory_block, safety, slots
from app.modules.pi.models import PiConversation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

CARRY_SLOTS_DAYS = 30  # an answered question is not asked again for this long
CARRY_ASKED_DAYS = 2  # a fact asked and left unanswered is asked again after this
MAX_SLOTS = slots.KEEP
LOOK_BACK = 3  # how many earlier chats are read, newest first
MARK = "slot_carry_done"  # set once the copy was made (or found empty): it is made once
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ASKED_KEYS = frozenset(key for key, _, _ in memory_block.FACTS)


def _clean(question: str) -> bool:
    """True when the question holds no personal data (a number, an address, a card, an ID)."""
    return not (
        PHONE.search(question) or EMAIL.search(question) or safety.redact_pii(question).kinds
    )


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _entry(raw: Any) -> tuple[str, str] | None:
    if not isinstance(raw, dict):
        return None
    slot, question = raw.get("slot"), raw.get("q")
    if not isinstance(slot, str) or not isinstance(question, str) or not question.strip():
        return None
    return slot, question


def carried(
    previous: list[tuple[dict[str, Any], datetime | None]], now: datetime
) -> dict[str, Any]:
    """What earlier chats hand over: (brief, last message time) pairs, newest first."""
    closed: list[dict[str, Any]] = []
    asked: list[str] = []
    for brief, at in previous:
        if not isinstance(brief, dict) or brief.get("erased") or at is None:
            continue
        age = now - _aware(at)
        if age <= timedelta(days=CARRY_SLOTS_DAYS):
            for raw in brief.get("closed_slots") or []:
                parts = _entry(raw)
                if parts is None:
                    continue
                slot, question = parts
                if slot == slots.ANYTHING_ELSE_SLOT or slots.ANYTHING_ELSE.search(question):
                    continue  # the generic closer is asked again in a new chat
                if not _clean(question):
                    continue
                if any(
                    (slot and c["slot"] == slot) or slots.same_question(c["q"], question)
                    for c in closed
                ):
                    continue  # the newest chat's entry stands
                closed.append({"slot": slot[:60], "q": question[:160], "carried": True})
        if age <= timedelta(days=CARRY_ASKED_DAYS):
            for key in brief.get("asked_facts") or []:
                if isinstance(key, str) and key in ASKED_KEYS and key not in asked:
                    asked.append(key)
    found: dict[str, Any] = {}
    if closed:
        found["closed_slots"] = closed[:MAX_SLOTS]
    if asked:
        found["asked_facts"] = asked
    return found


async def carry_into(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    now: datetime | None = None,
) -> bool:
    """Copy, once, what the owner's earlier chats hand over into this conversation's brief. Only
    chats of the same customer in the same workspace are read. True when something was copied."""
    brief = dict(conversation.service_brief or {})
    if brief.get(MARK) or conversation.customer_id is None:
        return False
    rows = (
        await session.execute(
            select(PiConversation.service_brief, PiConversation.last_message_at)
            .where(
                PiConversation.tenant_id == scope.tenant_id,
                PiConversation.environment_id == scope.environment_id,
                PiConversation.customer_id == conversation.customer_id,
                PiConversation.id != conversation.id,
            )
            .order_by(PiConversation.last_message_at.desc())
            .limit(LOOK_BACK)
        )
    ).all()
    found = carried([(earlier or {}, at) for earlier, at in rows], now or datetime.now(UTC))
    for key, value in found.items():
        brief.setdefault(key, value)  # what this chat already holds is never replaced
    conversation.service_brief = brief
    # The mark is set only once the open items came along too, so a failure there is tried again
    # on the next turn (the slot copy above is safe to repeat: it never replaces anything).
    if await _carry_open_items(session, scope, conversation, now):
        conversation.service_brief = {**(conversation.service_brief or {}), MARK: True}
    return bool(found)


async def _carry_open_items(
    session: AsyncSession,
    scope: WorkspaceScope,
    conversation: PiConversation,
    now: datetime | None,
) -> bool:
    """Q6-1: the open items of the owner's earlier chats come along (`open_items.carry_into`).
    True when it ran to the end. A failure never costs the owner their reply or the slot copy; it is
    logged with ids and the error type only (never message text) and tried again next turn."""
    from app.modules.pi import open_items

    try:
        async with session.begin_nested():
            await open_items.carry_into(session, scope, conversation, now=now)
    except Exception as error:  # noqa: BLE001
        logger.warning(
            "open items carry failed: tenant=%s conversation=%s customer=%s error=%s",
            scope.tenant_id,
            conversation.id,
            conversation.customer_id,
            type(error).__name__,
        )
        return False
    return True
