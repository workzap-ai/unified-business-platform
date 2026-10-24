"""Small deterministic touches on pi's reply before the checks: no model call, no change of meaning.

The prompt gives the noted-it line in English ("Thanks. I've noted it: {title}"); a model often
keeps that English frame inside a Roman Urdu or Arabic reply (seen live, 2026-10-24). The frame is
fixed text, so the application translates it itself instead of spending a rewrite call on it.
"""

import re

NOTED_FRAME = re.compile(
    r"^(?P<lead>\s*(?:Thanks|Thank you)[.,!]?\s*)?I(?:'ve| have) noted it\s*:", re.IGNORECASE
)

LOCALISED = {
    "roman_ur": "Shukriya. Maine note kar liya:",
    "ar": "شكرًا. سجلت ذلك:",
}


def localise_noted(reply: str, language: str | None) -> str:
    """The English noted-it frame in the person's language (Roman Urdu or Arabic); other
    languages and replies without the frame are returned unchanged."""
    frame = LOCALISED.get(language or "")
    if frame is None or not reply:
        return reply
    return NOTED_FRAME.sub(frame, reply, count=1)
