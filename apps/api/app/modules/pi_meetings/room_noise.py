"""Words the speech-to-text makes up out of silence, music or a breath.

Found live: a model that turns audio into text writes "you", "." or "Thank you for watching" for a
moment of near silence. Nobody said them. They must not make pi answer, and they must not be written
into the transcript as something a person said.
"""

import re

WORD = re.compile(r"\w+", re.UNICODE)

# a whole phrase that is only ever an invention of the model
INVENTED = re.compile(
    r"thanks? for watching|thank you for watching|subscribe|like and share|see you (next|in the)",
    re.IGNORECASE,
)
# words that, alone, are what the model writes for silence (a real "bye" is not here: it ends a
# call)
NOISE_WORDS = frozenset({"you", "thank", "thanks", "watching"})


def is_noise(text: str) -> bool:
    """No words at all ("." or "..."), or nothing but the words the model writes for silence."""
    words = [w.lower() for w in WORD.findall(text)]
    return not words or all(w in NOISE_WORDS for w in words)


def is_invented(text: str) -> bool:
    """Text nobody said: a made-up phrase or silence written as words."""
    return bool(INVENTED.search(text)) or is_noise(text)
