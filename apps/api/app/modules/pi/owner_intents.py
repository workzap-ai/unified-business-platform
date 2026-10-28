# ruff: noqa: E501
"""What an owner asks of pi, in any language: one small model call, kept on the message.

owner_asks.py holds the rules (no records, no questions, plan, recall, suggest, repeat complaint) and
its phrase banks recognise English and Roman Urdu. A furniture maker in Lagos, a clinic owner in Cairo
or a shop in Jakarta writes in none of those, and an eight-language check found 9 of 40 wordings.
So for every other language one fast model reads the message once and answers all six questions
together; the verdict is stored on the message (media["intents"]) so a later turn reads what an
earlier message said ("we keep no records", three messages ago) without asking again.

The phrase banks stay the answer for English and Roman Urdu (no model, no delay), and a model that is
down, slow or unsure changes nothing. Pure functions plus one never-raising async call.
"""

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from app.ai.types import Message
from app.modules.pi import owner_asks
from app.shared.scope import WorkspaceScope

FLAGS = (
    "no_questions",
    "no_records",
    "asks_plan",
    "repeat_complaint",
    "asks_recall",
    "asks_suggest",
)
MIN_WORDS = 3
MAX_WORDS = 80

SYSTEM = """You read one message from a business owner to a business assistant. The message may be in any
language or script. Answer with a JSON object only, six booleans:
{"no_questions": false, "no_records": false, "asks_plan": false, "repeat_complaint": false, "asks_recall": false, "asks_suggest": false}
no_questions: asks the assistant to stop asking questions, or not to ask more for now.
no_records: says they do not have, keep or know some facts (no records, no register, "I don't know exactly", no figures).
asks_plan: asks the assistant to explain the plan, the system or how it would work, in simple words.
repeat_complaint: complains that the assistant keeps asking the same or too many things.
asks_recall: asks what was said, discussed or decided earlier, or asks to be reminded.
asks_suggest: asks the assistant to suggest, recommend or list something concrete itself.
Set a flag true only when the message clearly says it. A greeting, a thanks, a yes or no, a description
of a problem or an answer to a question sets every flag to false."""

_JSON = re.compile(r"\{.*?\}", re.DOTALL)


def parse(text: str) -> dict[str, bool] | None:
    """The six flags from the model's answer, or None when it is not the expected JSON."""
    found = _JSON.search(text or "")
    if not found:
        return None
    try:
        data = json.loads(found.group(0))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    flags = {k: data.get(k) is True for k in FLAGS}
    return flags if any(isinstance(data.get(k), bool) for k in FLAGS) else None


ENGLISH_WORDS = frozenset(
    "the is are a an to of and you we i do does not no my me it for what how please with this that "
    "have has don't can will be in on at your our they them but if so now more any".split()
)


def looks_english(said: str) -> bool:
    """Plain English, by its small words. Latin script alone says nothing: Spanish, French and
    Indonesian are written in it too, and the language detector calls all of them English."""
    words = re.findall(r"[a-z']+", (said or "").lower())
    return bool(words) and sum(w in ENGLISH_WORDS for w in words) >= max(2, len(words) // 4)


ROMAN_URDU_WORDS = frozenset(
    "hai hain nahi nhi nahin kya aap ap hum humein hamare mujhe mujh mera meri ke ki ka ko se mein "
    "main kar karein karo kro kijiye aur par ho hoga tha thi the bhi jo ye yeh wo woh abhi sirf "
    "paas pata kitne kaise batayein samjha dein den".split()
)


def looks_roman_urdu(said: str) -> bool:
    """Roman Urdu by its small words: the language detector also calls French and others Roman Urdu."""
    words = re.findall(r"[a-z']+", (said or "").lower())
    return sum(w in ROMAN_URDU_WORDS for w in words) >= 2


def needed(said: str) -> bool:
    """Whether the model should read this message: a real message in a language the phrase banks do
    not cover. English and Roman Urdu are decided by owner_asks."""
    words = (said or "").split()
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        return False
    return not (looks_english(said) or looks_roman_urdu(said))


def stored(media: Mapping[str, Any] | None) -> dict[str, bool]:
    """The flags a message carries (those that are true), empty when none were stored."""
    raw = (media or {}).get("intents")
    if not isinstance(raw, Mapping):
        return {}
    return {k: True for k in FLAGS if raw.get(k) is True}


def merged(said: str, media: Mapping[str, Any] | None) -> dict[str, bool]:
    """The phrase banks and the stored model verdict for one message, together."""
    flags = stored(media)
    if owner_asks.asked_no_questions(said):
        flags["no_questions"] = True
    if owner_asks.count_unknowns([said]):
        flags["no_records"] = True
    if owner_asks.asks_for_plan(said):
        flags["asks_plan"] = True
    if owner_asks.complains_of_repeats(said):
        flags["repeat_complaint"] = True
    if owner_asks.asks_for_recall(said):
        flags["asks_recall"] = True
    if owner_asks.asks_to_suggest(said):
        flags["asks_suggest"] = True
    return flags


def read(messages: Iterable[tuple[str, Mapping[str, Any] | None]]) -> dict[str, list[int]]:
    """For (text, media) pairs oldest first: the positions at which each flag was said."""
    seen: dict[str, list[int]] = {k: [] for k in FLAGS}
    for index, (text, media) in enumerate(messages):
        for key in merged(text or "", media):
            seen[key].append(index)
    return seen


async def classify(
    manager: Any,
    scope: WorkspaceScope,
    *,
    said: str,
    conversation_id: UUID | None,
    alias: str = "fast",
) -> dict[str, bool] | None:
    """Ask the model when it is needed. Never raises; None means the phrase banks stay the answer."""
    if not needed(said):
        return None
    try:
        response = await manager.complete(
            scope,
            alias=alias,
            purpose="pi_owner_intents",
            messages=[Message.system(SYSTEM), Message.user(said[:800])],
            temperature=0.0,
            max_tokens=80,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 - the phrase banks stay the answer
        return None
    return parse(str(getattr(response, "text", "") or ""))
