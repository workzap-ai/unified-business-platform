"""Reactions, stickers, edited and deleted messages (platform spec 6.10).

whatsapp.normalize marks these events with a `signal` and no text. This module gives them the
meaning the spec states, without ever sending a reply of its own (no reply storm):

- a thumbs-up (and the like) on any message is a soft acknowledgement: it is remembered on that
  message and answers nothing. It is never a yes to an offer: it never reaches the decision gate,
  because only a typed message does (decisions.py);
- a cross or thumbs-down on one of pi's lines asks "what should be corrected?": it becomes one
  ordinary inbound message holding the emoji, once per line, so the usual turn answers it;
- a sticker alone changes nothing and is not answered;
- an edited message replaces the earlier text (personal data removed first), so a turn that has not
  run yet answers the new words and later turns read them; it is not answered a second time;
- a deleted message is blanked, taken out of the evidence of any problem it was the source of, and
  its quarantined original is dropped; pi says nothing about it.
"""

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from app.modules.pi import safety
from app.modules.pi.models import PiMessage

KINDS = ("reaction", "sticker", "edit", "delete")

_TONE = re.compile("[\U0001f3fb-\U0001f3ff️‍]")
ACKNOWLEDGES = frozenset({"👍", "👌", "🙏", "✅"})
CORRECTS = frozenset({"❌", "👎"})
MAX_REACTIONS = 10


def meaning(emoji: str) -> str:
    """What a reaction emoji says: "ack" (soft acknowledgement), "correct" (ask what to fix) or
    "other" (kept, answers nothing). Skin tones and variation selectors do not change it."""
    plain = _TONE.sub("", emoji or "").strip()
    if plain in ACKNOWLEDGES:
        return "ack"
    if plain in CORRECTS:
        return "correct"
    return "other"


async def resolve(
    session: Any, service: Any, event: Any, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Apply one signal. Returns None when it is fully handled (nothing to process), or the payload
    of an ordinary text message to process in its place (a correction reaction)."""
    signal = payload.get("signal") or {}
    kind = signal.get("kind")
    result: dict[str, Any] | None = None
    if kind == "reaction":
        result = await _reaction(service, payload, signal)
    elif kind == "edit":
        await _edit(service, signal)
    elif kind == "delete":
        await _delete(session, service, signal)
    if result is None:
        event.status, event.processed_at = "processed", datetime.now(UTC)
    return result


async def _target(service: Any, signal: dict[str, Any]) -> PiMessage | None:
    wanted = str(signal.get("target") or "")
    if not wanted:
        return None
    found: PiMessage | None = await service.messages.find(PiMessage.provider_message_id == wanted)
    return found


async def _reaction(
    service: Any, payload: dict[str, Any], signal: dict[str, Any]
) -> dict[str, Any] | None:
    emoji = str(signal.get("emoji") or "")
    if not emoji:
        return None  # a reaction taken back
    target = await _target(service, signal)
    if target is None:
        return None
    said = meaning(emoji)
    media = dict(target.media or {})
    reactions = [r for r in media.get("reactions") or [] if isinstance(r, dict)]
    if said == "correct" and any(r.get("meaning") == "correct" for r in reactions):
        return None  # the correction was asked for this line already: no second message
    reactions.append({"emoji": emoji, "meaning": said, "at": datetime.now(UTC).isoformat()})
    media["reactions"] = reactions[-MAX_REACTIONS:]
    target.media = media
    if said == "correct" and target.direction == "outbound":
        return {
            **payload,
            "signal": None,
            "message_type": "text",
            "body": _TONE.sub("", emoji).strip(),
            "media_id": None,
        }
    return None


async def _edit(service: Any, signal: dict[str, Any]) -> None:
    target = await _target(service, signal)
    text = str(signal.get("text") or "").strip()
    if target is None or target.direction != "inbound" or not text:
        return
    target.body = safety.redact_pii(text).text
    media = dict(target.media or {})
    media["edited"] = True
    target.media = media


async def _delete(session: Any, service: Any, signal: dict[str, Any]) -> None:
    from app.modules.pi.problem_models import PiProblem
    from app.modules.pi.quarantine_models import PiQuarantine

    target = await _target(service, signal)
    if target is None or target.direction != "inbound":
        return
    target.body = ""
    target.media = {"deleted": True}
    mine = str(target.id)
    problems = await session.scalars(
        select(PiProblem).where(
            PiProblem.tenant_id == target.tenant_id,
            PiProblem.environment_id == target.environment_id,
            PiProblem.conversation_id == target.conversation_id,
            PiProblem.source_message_ids.contains([mine]),
        )
    )
    for problem in problems:
        left = [m for m in problem.source_message_ids or [] if m != mine]
        problem.source_message_ids = left
        if not left:
            problem.user_words = []  # it was the only source of these words
    await session.execute(
        delete(PiQuarantine).where(
            PiQuarantine.tenant_id == target.tenant_id,
            PiQuarantine.environment_id == target.environment_id,
            PiQuarantine.message_id == target.id,
        )
    )
