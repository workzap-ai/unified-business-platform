"""What pi already knows about the customer a meeting is linked to, for use inside the meeting job.

The same single door the WhatsApp chat uses (`pi/shared_memory.brief`), so pi in a meeting knows the
client as it does in chat: their name, language, open problems, what an earlier chat or meeting
already settled, and what they said no to. Three cases are handled, none of them guessed:

* **No memory** (a meeting with no customer, a new customer, nothing recorded, or a customer who was
  erased): `load` returns `{}` and pi behaves exactly as it did before: it asks, it does not pretend
  to remember.
* **Someone else opens the link**: the link is tied to a customer, but the person who opens it may
  not be them. `voice.py` asks "Am I speaking with <first name>?" first and the memory is used only
  after a clear yes; any no, or any unclear answer, leaves it unused for the rest of the
  conversation (see `voice.confirm_state`).
* **Never recited**: the block is data below every rule. pi uses it so the person does not repeat
  themselves; it does not read it out, does not state a pi guess as something they said, and a
  reply that breaks a rule is replaced by the safe line as for any other reply.

Reading memory never writes it: what pi learns in a meeting returns to memory only through the
reviewer-approved `brain_bridge`.
"""

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import shared_memory
from app.modules.pi.context_memory_types import OWNER_STATUSES
from app.modules.pi_meetings.models import PiMeeting
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

NAME_KIND = "name"
# what the person said or confirmed (the chat's own allowlist), and what the ledger remembers of
# it; a pi guess (pi_inferred), a page read or a staff-record copy is never spoken as something
# they said
SAID = frozenset({*OWNER_STATUSES, "remembered"})
FIRST_NAME = re.compile(r"[^\W\d_]{2,30}", re.UNICODE)
PROPER = re.compile(r"\b[A-Z][a-z]{2,}\b")
NUMBER = re.compile(r"\d[\d,.]*")
COMMON = frozenset({"the", "and", "for", "they", "this", "that", "with", "have", "last", "name"})


def language_of(meeting: PiMeeting) -> str:
    return meeting.language if re.fullmatch(r"[a-z]{2,3}", meeting.language or "") else "en"


async def load(session: AsyncSession, scope: WorkspaceScope, meeting: PiMeeting) -> dict[str, Any]:
    """The `what_i_know` block for this meeting's customer, or {}. Never raises: a memory that
    cannot be read must not stop a conversation."""
    if meeting.customer_id is None:
        return {}
    try:
        return await shared_memory.brief(
            session, scope, meeting.customer_id, language=language_of(meeting)
        )
    except Exception:  # memory is context, never a reason for a turn to fail
        logger.warning("pi_meeting_memory_unavailable")
        return {}


def speakable(block: dict[str, Any]) -> dict[str, Any]:
    """The part of the block pi may let shape what it SAYS: records the person said or confirmed,
    and the ideas they said no to. A pi guess, and the free-text summaries (which can blend guesses
    in), stay out. {} when nothing is left."""
    records = [r for r in block.get("records") or [] if r.get("status") in SAID]
    if not records:
        return {}
    out: dict[str, Any] = {"records": records}
    if block.get("ideas_they_said_no_to"):
        out["ideas_they_said_no_to"] = block["ideas_they_said_no_to"]
    return out


def leaks(text: str, seen: str, block: dict[str, Any]) -> bool:
    """Would this spoken line put something from memory into the air that the person never said
    in this conversation? A number (money, a phone, a count) or a proper name that is in the memory
    but not in `seen` (the conversation so far). Code, not the prompt, stops pi reciting a file."""
    if not block:
        return False
    heard = seen.lower()
    for number in NUMBER.findall(text):
        digits = re.escape(number.rstrip(".,"))
        if not re.search(rf"(?<![\d]){digits}(?![\d])", heard):  # the whole number, not a part
            return True
    private = {
        word.lower()
        for record in block.get("records") or []
        for word in PROPER.findall(str(record.get("text") or ""))
    } - COMMON
    return any(
        re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) and term not in heard
        for term in private
    )


def first_name(block: dict[str, Any]) -> str:
    """The first name the person gave pi themselves, or "". Only a name the person said or
    confirmed, from the facts, counts: a pi guess or a staff-record copy never greets someone."""
    for record in block.get("records") or []:
        if (
            record.get("kind") != NAME_KIND
            or record.get("source") != "facts"
            or record.get("status") not in OWNER_STATUSES
        ):
            continue
        value = str(record.get("text") or "").split(":", 1)[-1].strip()
        match = FIRST_NAME.match(value)
        if match:
            return match.group(0)
    return ""
