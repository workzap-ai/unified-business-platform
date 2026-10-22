"""Matching the person, and mending a reply that did not land (pi Brain spec 8.4.1 and 8.4.2).

`profile` reads the person's own messages: how long they write, how formal they are, whether they
use emoji or send voice notes. pi answers at about one and a half times their length, never more
familiar than they are. `repair_step` is what to do when they look confused: rephrase simpler, give
choices, give an example, offer another language once, then drop the question. Both are plain code
over the text: no model, no learning, nothing here can override a rule.
"""

import re
import statistics
from collections.abc import Iterable
from typing import Any

LENGTH_FACTOR = 1.5  # replies stay at or under this many times their usual length
MIN_REPLY_WORDS = 25  # but never so short that a noted line and a question cannot fit
MAX_REPLY_WORDS = 60
SHORT_ENOUGH = 12  # at or under this a person is writing "short" (and may be on voice notes)

FORMAL = re.compile(
    r"\b(?:sir|madam|ma'?am|please|kindly|thank you|regards|aap|janab|mohtaram|shukriya|"
    r"assalam(?:u|o)? ?alaikum|dear)\b|آپ|جناب",
    re.IGNORECASE,
)
CASUAL = re.compile(
    r"\b(?:yaar|yar|bhai|bro|dude|tum|tu|abe|oye|lol|haha|bhaijaan|bro)\b", re.IGNORECASE
)
EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⭐⭕]")

CONFUSED = re.compile(
    r"^\W*(?:what|huh|\?+|kya|kya matlab|matlab|samajh nahi(?: aaya| aya| aa raha)?|"
    r"samjha nahi|i don'?t (?:get|understand)|not sure what you mean|what do you mean|"
    r"what\?|sorry\?|come again|pardon)\W*$"
    r"|\b(?:samajh nahi|samjh nahi|samajh nahin|don'?t understand|do not understand|"
    r"what do you mean|kya matlab|confus(?:ed|ing))\b"
    r"|سمجھ نہیں|لا أفهم",
    re.IGNORECASE,
)

REPAIR = {
    1: "Rephrase it simpler: fewer words, everyday terms, one short sentence.",
    2: 'Give choices instead of an open question, e.g. "Is it more like stock, cash or staff?".',
    3: 'Give a small example of what you mean, e.g. "For example, does stock run out, or is '
    'there too much?".',
    4: 'Offer once to continue in another language (e.g. "Urdu mein baat karein?") and ask '
    "nothing else.",
    5: "Drop the question: treat the detail as unknown, say so in a few words and move on to "
    "what they said.",
}
LAST_STEP = max(REPAIR)


def _words(text: str) -> int:
    return len(text.split())


def profile(said: Iterable[str], *, voice_notes: int = 0, total: int = 0) -> dict[str, Any]:
    """What the person's own messages say about how to answer them."""
    messages = [m for m in said if m and m.strip()]
    if not messages:
        return {}
    median = statistics.median(_words(m) for m in messages)
    longest = max(_words(m) for m in messages)
    joined = " ".join(messages)
    formal = len(FORMAL.findall(joined))
    casual = len(CASUAL.findall(joined))
    formality = "formal" if formal > casual else "casual" if casual > formal else "neutral"
    reply_up_to = int(max(MIN_REPLY_WORDS, min(MAX_REPLY_WORDS, round(median * LENGTH_FACTOR))))
    return {
        "median_words": median,
        "reply_up_to_words": reply_up_to,
        "writes_short": median <= SHORT_ENOUGH and longest <= SHORT_ENOUGH * 3,
        "formality": formality,
        "uses_emoji": bool(EMOJI.search(joined)),
        "voice_notes": voice_notes > 0 and (not total or voice_notes / total >= 0.25),
    }


def confused(text: str) -> bool:
    """The person looks lost: a lone "what?", "samajh nahi aaya", "I don't understand"."""
    return bool(CONFUSED.search(" ".join((text or "").split())))


def repair_step(previous: int, text: str) -> int:
    """0 when they are following; otherwise the next strategy, one step further each time."""
    if not confused(text):
        return 0
    return min(previous + 1, LAST_STEP)
