"""Quick-reply buttons: one tap instead of typing.

WhatsApp allows up to three reply buttons (titles of at most 20 characters) on a
session message. A tap comes back as an ordinary message whose text is the button's
title, so pi reads it like anything the customer typed. Used on:
- the reminder permission question: [Yes, message me] [No thanks];
- pi's follow-ups (the ~20h nudge, the check-in): [Let's continue] [Remind me later]
  [Stop reminders].
"Remind me later" pauses follow-ups for two days; "Stop reminders" is an opt-out.
"""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi.models import PiConversation, PiMessage
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

CONSENT = {
    "en": ["Yes, message me", "No thanks"],
    "roman_ur": ["Haan, message karein", "Nahi shukriya"],
    "ur": ["جی ہاں", "نہیں شکریہ"],
    "ar": ["نعم، راسلني", "لا شكرًا"],
}
FOLLOW_UP = {
    "en": ["Let's continue", "Remind me later", "Stop reminders"],
    "roman_ur": ["Aage barhein", "Baad mein yaad dilao", "Reminders band karo"],
    "ar": ["لنكمل", "ذكرني لاحقًا", "أوقف التذكيرات"],
}
REMIND_LATER = {titles[1].casefold() for titles in FOLLOW_UP.values()}
PAUSE = timedelta(days=2)
assert all(len(t) <= 20 for v in (*CONSENT.values(), *FOLLOW_UP.values()) for t in v)


def follow_up_buttons(language: str | None) -> list[str]:
    return FOLLOW_UP.get(language or "en", FOLLOW_UP["en"])


def consent_buttons(body: str) -> list[str] | None:
    """The Yes/No buttons when a reply ends with pi's reminder permission question."""
    from app.modules.pi.service_conversation import CONSENT_QUESTION

    for language, question in CONSENT_QUESTION.items():
        if body.rstrip().endswith(question):
            return CONSENT.get(language, CONSENT["en"])
    return None


def is_remind_later(text: str | None) -> bool:
    return (text or "").strip().casefold() in REMIND_LATER or bool(
        re.fullmatch(r"\W*remind me later\W*", text or "", re.IGNORECASE)
    )


async def note_remind_later(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage
) -> bool:
    """The customer tapped "Remind me later": no follow-ups for two days (the check-in,
    the ladder and the reminder template all respect ``customer_waiting_until``)."""
    if message.direction != "inbound" or not is_remind_later(message.body):
        return False
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        message.conversation_id
    )
    brief = dict(conversation.service_brief or {})
    brief["customer_waiting_until"] = (datetime.now(UTC) + PAUSE).isoformat()
    conversation.service_brief = brief
    if conversation.followup_due_at is not None:
        conversation.followup_due_at = max(conversation.followup_due_at, datetime.now(UTC) + PAUSE)
    return True


async def add_consent_buttons(
    session: AsyncSession, scope: WorkspaceScope, message_ids: list[str]
) -> None:
    """Turn pi's queued reply that asks for reminder permission into a button message."""
    from uuid import UUID

    repo = WorkspaceRepository(session, PiMessage, scope)
    for message_id in message_ids:
        row = await repo.find(PiMessage.id == UUID(message_id))
        if row is None or row.sender_type != "ai" or row.status != "queued":
            continue
        buttons = consent_buttons(row.body or "")
        if buttons and not (row.media or {}).get("buttons"):
            media: dict[str, Any] = dict(row.media or {})
            media["buttons"] = buttons
            row.media = media


# Buttons on pi's picture cards (the Problem Map and the journey card).
CARD = {
    "map": {
        "en": ["Makes sense", "Not related", "Show solution"],
        "roman_ur": ["Theek hai", "Ye jure nahi", "Hal dikhao"],
        "ar": ["منطقي", "غير مرتبطين", "أرني الحل"],
    },
    "journey": {
        "en": ["See details", "Ask a question"],
        "roman_ur": ["Tafseel dikhao", "Sawal poochna hai"],
        "ar": ["التفاصيل", "لدي سؤال"],
    },
}
NOT_RELATED = {titles[1].casefold() for titles in CARD["map"].values()}
assert all(len(t) <= 20 for kind in CARD.values() for v in kind.values() for t in v)


def card_buttons(kind: str, language: str | None) -> list[str]:
    options = CARD.get(kind) or {}
    return options.get(language or "en") or options.get("en") or []


async def note_not_related(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage
) -> bool:
    """The customer tapped "Not related" under a map card: the connection pi announced
    last is removed and never drawn again (the same as the dashboard's button)."""
    from app.modules.pi_customer import service as portal

    if message.direction != "inbound" or (message.body or "").strip().casefold() not in (
        NOT_RELATED
    ):
        return False
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        message.conversation_id
    )
    # The connection the latest map card announced (kept on that card message), not
    # whatever was found since.
    card = await session.scalar(
        WorkspaceRepository(session, PiMessage, scope)
        .select()
        .where(
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "outbound",
            PiMessage.media["link_pair"].is_not(None),
        )
        .order_by(PiMessage.created_at.desc())
        .limit(1)
    )
    pair = (card.media or {}).get("link_pair") if card is not None else None
    if not isinstance(pair, list) or len(pair) != 2:
        return False
    brief = dict(conversation.service_brief or {})
    brief.update(portal.reject_link_patch(brief, str(pair[0]), str(pair[1])))
    conversation.service_brief = brief
    return True
