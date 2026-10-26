"""Small deterministic touches on pi's reply before the checks: no model call, no change of meaning.

The prompt gives the noted-it line in English ("Thanks. I've noted it: {title}"). A model often
keeps that English frame inside a Roman Urdu or Arabic reply, and repeats the same opening on every
turn, which the linter then sends back for a rewrite (seen live, 2026-10-24: a whole extra model
call per turn). The frame is fixed text, so the application translates it and rotates it itself.
"""

import re
from typing import Any

# Anywhere in the reply, not only first: the frame can follow the ideas (seen in a real Roman Urdu
# chat, 2026-10-26: "Pehle, ... Doosra, ... Thanks. I've noted it: ...").
NOTED_FRAME = re.compile(
    r"(?P<lead>(?:Thanks|Thank you)[.,!]?\s*)?I(?:'ve| have) noted it\s*:", re.IGNORECASE
)

# Every variant says "noted" in the person's language (the learning code recognises it).
FRAMES = {
    "en": ("Thanks. I've noted it:", "Got it, noted:", "Understood, I've noted:", "Noted:"),
    "roman_ur": (
        "Shukriya. Maine note kar liya:",
        "Theek hai, note kar liya:",
        "Samajh liya, note kar liya:",
        "Note kar liya:",
    ),
    "ar": ("شكرًا. سجلت ذلك:", "حسنًا، سجلت ذلك:", "فهمت، سجلت ذلك:", "سجلت:"),
}


def noted_before(context: dict[str, Any]) -> int:
    """How many of pi's earlier replies in this chat already said it noted something."""
    from app.modules.pi.experience_scorer import says_noted

    return sum(
        1
        for h in context.get("history") or []
        if h.get("role") == "ai" and says_noted(str(h.get("text", "")))
    )


def localise_noted(reply: str, language: str | None, seen: int = 0) -> str:
    """The noted-it frame in the person's language, a different variant each time (`seen` is how
    many earlier replies already noted something). Other languages and replies without the English
    frame are returned unchanged."""
    frames = FRAMES.get(language or "")
    if frames is None or not reply or not NOTED_FRAME.search(reply):
        return reply
    return NOTED_FRAME.sub(frames[seen % len(frames)], reply, count=1)
