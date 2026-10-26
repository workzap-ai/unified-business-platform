# ruff: noqa: E501
"""A language-independent check of "is this a request for a solution or an idea?".

The phrase banks in solution_ask.py cover English, Roman Urdu, Arabic, Urdu, Chinese and a handful of
other languages, and they miss new wordings. A person who asks in any other language, or in a way no
phrase lists, still has to get ideas (platform spec Book 2 Part 5). So when the phrase banks say
"not an ask" and the message could still be one, a small fast model is asked once, and the answer is
remembered for that exact message (solution_ask.remember_ask), so every place that decides whether
the person asked reads the same verdict. A model that is down, slow or unsure changes nothing: the
phrase banks stay the answer.
"""

import json
import re
from typing import Any
from uuid import UUID

from app.ai.types import Message
from app.modules.pi import language, solution_ask
from app.shared.scope import WorkspaceScope

SYSTEM = """You decide whether a message from a business owner to a business assistant is a request for
a solution, an idea, advice, or for what the assistant can do about their problem. The message may be in
any language. Answer with a JSON object only: {"asks": true} or {"asks": false}.
true: "give me a solution", "any idea?", "what can you do for this?", "how do I fix it?", "tell me what to
do", "can you help with this?", the same in any language or wording.
false: describing a problem, a greeting, a yes or no, a thanks, an answer to a question, a question about
price or cost, a question about who the assistant is, anything else."""

MIN_WORDS = 3
MAX_WORDS = 60
VERDICT = re.compile(r'"asks"\s*:\s*(true|false)', re.IGNORECASE)


def parse(text: str) -> bool | None:
    """True or False from the model's answer, or None when it is not the expected JSON."""
    found = VERDICT.search(text or "")
    if found:
        return found.group(1).lower() == "true"
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    value = data.get("asks") if isinstance(data, dict) else None
    return value if isinstance(value, bool) else None


def needed(said: str, flow_state: str) -> bool:
    """Whether the model should be asked: where an ask is answered, a real message, not already
    decided by the phrase banks, and one that could be an ask the banks do not know (a language they
    do not cover, or a question)."""
    if flow_state not in solution_ask.ASKABLE:
        return False
    words = (said or "").split()
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        return False
    if solution_ask.known_ask(said) is not None or solution_ask.asked_for_ideas(said):
        return False
    return language.detect_language(said) not in ("en", "roman_ur") or "?" in said or "؟" in said


async def prefetch(
    manager: Any,
    scope: WorkspaceScope,
    *,
    said: str,
    flow_state: str,
    conversation_id: UUID | None,
    alias: str = "fast",
) -> bool | None:
    """Ask the model when it is needed and remember its verdict. Never raises."""
    if not needed(said, flow_state):
        return None
    try:
        response = await manager.complete(
            scope,
            alias=alias,
            purpose="pi_ask_classify",
            messages=[Message.system(SYSTEM), Message.user(said[:600])],
            temperature=0.0,
            max_tokens=30,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001 - the phrase banks stay the answer
        return None
    verdict = parse(str(getattr(response, "text", "") or ""))
    if verdict is not None:
        solution_ask.remember_ask(said, verdict)
    return verdict
