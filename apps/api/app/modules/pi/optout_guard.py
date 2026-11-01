"""A person who said "stop" is never written to first, whatever the stored consent says.

Production showed three chats where the owner wrote "Stop" or "Stop reminders", pi confirmed it, and
the stored `reminder_consent` was nevertheless "unknown": the quiet-spell nudge then went out again.
The follow-up senders call `opted_out` before every unsolicited line: it reads the chat's own
inbound messages (the evidence), repairs the stored consent to "declined" and clears the due time.
Only the person's own words count; a later "start again" is handled by the normal flow, not here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import safety
from app.modules.pi.models import PiConversation, PiMessage

MAX_LEN = (
    80  # the same bound as note_opt_out: a long message that contains "stop" is not an opt-out
)


def said_stop(text: str | None) -> bool:
    from app.modules.pi_saas.campaigns import OPT_OUT

    body = (text or "").strip()
    if not body or len(body) > MAX_LEN:
        return False
    return bool(OPT_OUT.match(body) or safety.opt_out_asked(body))


async def opted_out(session: AsyncSession, conversation: PiConversation) -> bool:
    """True when the stored consent is "declined" or the person's own messages asked to stop;
    in the second case the stored consent is repaired."""
    brief: dict[str, Any] = dict(conversation.service_brief or {})
    if brief.get("reminder_consent") == "declined":
        return True
    bodies = await session.scalars(
        select(PiMessage.body)
        .where(
            PiMessage.conversation_id == conversation.id,
            PiMessage.direction == "inbound",
        )
        .order_by(PiMessage.created_at.desc())
        .limit(200)
    )
    if not any(said_stop(b) for b in bodies):
        return False
    brief["reminder_consent"] = "declined"
    conversation.service_brief = brief
    conversation.followup_due_at = None
    return True
