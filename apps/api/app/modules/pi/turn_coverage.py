"""Platform spec v1.4, 17.2: the turnCoverage guard.

An owner turn is every owner message since pi's last reply. A reply that skips the longest or the
most heartfelt message of the turn is rejected and rewritten ("never again: replying to messages 3
and 4 of a burst and dropping message 1").

The check is deliberately cautious: it only flags a reply that shares not a single content word
(first five letters count as a match, so plurals and endings do not matter) with the biggest
earlier message, and only when that message is long enough to be a real topic. A false alarm costs
one rewrite; a missed one costs a heartfelt message left unanswered.
"""

import re

# Strain words (spec 17.2 "Feeling first": 'tang kar raha hai', 'thak gaya'), weighted as extra
# words when the biggest topic is chosen.
STRAIN = re.compile(
    r"\b(?:tang|thak\w*|pareshan\w*|tired|exhausted|fed up|frustrat\w*|stress\w*|worried|worry|"
    r"overwhelm\w*|disappear\w*|excuse\w*|gussa|ukta\w*|helpless|desperate|sick of)\b|"
    r"\b(?:very|bohat|bahut)\s+(?:upset|sad|angry)\b",
    re.IGNORECASE,
)
STRAIN_WEIGHT = 12
MIN_WORDS = 6  # a shorter message is an aside, not a topic that must be answered
MIN_CONTENT_WORDS = 3
STEM = 5
# Scripts written without spaces: words cannot be compared here, so the guard stays out of it.
UNSPACED = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿]")
STOPWORDS = frozenset(
    """about after again also because been before being could does doing from have having here
    just like make more much only other over really should some such than that their them then
    there these they this those very want what when where which while will with would your
    aap apni apna apne bhi hai hain hota hote hoti kar karna karne karta karte karti kaise kia
    kya kyun kyunke lekin mera meri mere mujhe nahi phir sab thi thha unka unki unke wala wali
    wale yeh woh aur bas bohat bahut abhi jab tak toh agar""".split()
)
WORD = re.compile(r"\w+", re.UNICODE)


def _content_words(text: str) -> set[str]:
    return {
        w[:STEM]
        for w in (m.group(0).casefold() for m in WORD.finditer(text))
        if len(w) >= 4 and not w.isdigit() and w not in STOPWORDS
    }


def _weight(text: str) -> int:
    return len(text.split()) + STRAIN_WEIGHT * len(STRAIN.findall(text))


def biggest(texts: list[str]) -> int:
    """The index of the message the owner spent the most words or feeling on (the earliest wins a
    tie, so a heartfelt first message is not lost to a later one of the same size)."""
    best, best_weight = 0, -1
    for i, text in enumerate(texts):
        if (w := _weight(text)) > best_weight:
            best, best_weight = i, w
    return best


def skipped_topic(reply: str, texts: list[str]) -> str | None:
    """The biggest message of the turn when the reply does not touch it, else None. `texts` are
    the owner messages of the turn, oldest first (the newest is the last)."""
    texts = [t for t in texts if t and t.strip()]
    if len(texts) < 2 or not reply.strip():
        return None
    index = biggest(texts)
    if index == len(texts) - 1:
        return None  # the newest message is what a reply addresses by default
    topic = texts[index]
    if len(topic.split()) < MIN_WORDS or UNSPACED.search(topic) or UNSPACED.search(reply):
        return None
    words = _content_words(topic)
    if len(words) < MIN_CONTENT_WORDS:
        return None
    if words & _content_words(reply):
        return None
    return topic


def rewrite_reason(topic: str) -> str:
    """The reason given to the model for the one rewrite (never sent to the owner)."""
    shown = " ".join(topic.split())[:160]
    return (
        "the reply skips the owner's longest or most heartfelt message of this turn "
        f'("{shown}"). Answer that message first, in their own terms (a feeling first, in one '
        "plain sentence, if they showed strain), then the newest one. Never answer only the last "
        "message of a burst"
    )


def turn_note(queued: bool) -> str:
    """Said to the model in the context of a turn made of several messages (spec 17.8, OWNER
    TURN). After an outage the earliest queued message is named first (spec 17.7 step 3)."""
    note = (
        "The owner sent several messages since your last reply (the earlier ones are the last "
        "customer entries of history). Cover them all, in this order: any strain or feeling in "
        "one plain sentence, their direct questions and requests, the topic they spent the most "
        "words or feeling on even if it is not the last message, then the newest one. Never "
        "answer only the last message."
    )
    if queued:
        note += (
            " They wrote the earliest of these while pi was down and it was kept: answer that "
            "first and name it plainly, in their language (for example 'Subah ka sawal: ...')."
        )
    return note
