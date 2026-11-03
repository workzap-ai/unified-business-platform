"""Platform spec v1.4, 17.3: the active topic, parking, and a second business (TS1-TS3, A44, G53).

The chat keeps ONE active topic. A second, different business is engaged with one real thought,
kept apart from the first, and the owner steers: "Pehle kis se shuru karein?". The state lives in
the conversation brief (`brief["topics"]`), so nothing is migrated; it is a pointer, never a label
on the person. Everything here is pure: `observe` takes the stored state and the owner's message and
returns the new state and what happened; the caller stores it and tells the model (`note`).

What this wave does NOT do (needs a migration, a later wave): a separate business profile, a
separate map and a separate industry pack for the second business, and the dashboard switcher
(17.3 steps 2 and 4). Until then the two businesses are kept apart in the conversation only: ideas
wait until the owner has said which business to start with.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# A different kind of work, a different place, "mera ek aur karobar" (17.3 signals).
SECOND_BUSINESS = re.compile(
    r"\b(?:mera|meri|mere)\s+(?:ek\s+)?(?:aur|dusra|doosra|dusri|doosri|dusre|doosre)\s+"
    r"(?:karobar|karobaar|business|dukan|shop|kaam|farm)\b|"
    r"\b(?:ek\s+aur|ek\s+dusra|ek\s+doosra)\s+(?:karobar|karobaar|business|dukan|shop|farm)\b|"
    r"\b(?:another|a second|second|my other|one more|different)\s+(?:business|company|shop|"
    r"venture|farm|firm)\b|"
    r"\bi\s+(?:also|additionally)\s+(?:run|own|have|started|manage)\s+(?:a|an|another)\b|"
    r"\b(?:also|aur)\s+(?:ek\s+)?(?:run|own|chalata|chalati|chalaata)\b",
    re.IGNORECASE,
)
# "By the way, another thing": a new topic inside the same business.
SWITCH = re.compile(
    r"\b(?:by the way|btw|another thing|different topic|something else|on another note|"
    r"ek aur baat|ek dusri baat|ek doosri baat|waise|aur ek cheez|alag baat)\b",
    re.IGNORECASE,
)
# The owner asks to go back to the earlier business or thread.
GO_BACK = re.compile(
    r"\b(?:wapas|waapis|back to|go back|return to|pehle wale|pehle wala|previous|earlier one|"
    r"old business|pehle karobar|purane karobar|pehle (?:par|pe|ki|ka) )\b",
    re.IGNORECASE,
)
FIRST_ONE = re.compile(
    r"\b(?:pehle wale|pehle wala|pehla|first one|the first|first business|old one|purana|"
    r"purane|original|pehle (?:karobar|business)|shuru wala)\b",
    re.IGNORECASE,
)
SECOND_ONE = re.compile(
    r"\b(?:dusra|doosra|dusre|doosre|second one|the second|second business|new one|naya|nayi|"
    r"naye|dusre wale|doosre wale|dusra wala|doosra wala)\b",
    re.IGNORECASE,
)
STOP = frozenset(
    "this that with have from they them their there about what when where which your mera meri "
    "mere hain hai hota karobar business shop kaam aur bhi toh woh yeh bohat bahut abhi".split()
)
WORD = re.compile(r"\w{4,}", re.UNICODE)
LABEL_WORDS = 8


def _stems(text: str) -> set[str]:
    return {w.casefold()[:5] for w in WORD.findall(text or "") if w.casefold() not in STOP}


def _label(text: str) -> str:
    """A short plain label for a business: the first words of the message that named it."""
    return " ".join((text or "").split()[:LABEL_WORDS])[:80]


@dataclass
class Topics:
    """`items`: the businesses (or threads) in this chat, oldest first, each {"id","label"}.
    `active`: the id pi is working on. `pending`: pi has asked which to start with."""

    items: list[dict[str, str]] = field(default_factory=list)
    active: str | None = None
    pending: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"items": self.items, "active": self.active, "pending": self.pending}

    @classmethod
    def from_dict(cls, raw: Any) -> "Topics":
        if not isinstance(raw, dict):
            return cls()
        items = [
            {"id": str(i.get("id") or ""), "label": str(i.get("label") or "")[:80]}
            for i in raw.get("items") or []
            if isinstance(i, dict) and i.get("id")
        ][:5]
        active = raw.get("active")
        return cls(items, str(active) if active else None, bool(raw.get("pending")))

    def parked(self) -> list[dict[str, str]]:
        return [i for i in self.items if i["id"] != self.active]

    def label_of(self, topic_id: str | None) -> str:
        return next((i["label"] for i in self.items if i["id"] == topic_id), "")


@dataclass(frozen=True)
class Event:
    """What this message did to the pointer: second_business, steered, returned, switch or none."""

    kind: str = "none"
    topic: str | None = None  # the topic the reply must address (its id)
    parked: str | None = None  # the topic put aside by this message (its id)


NONE = Event()


def from_brief(brief: dict[str, Any] | None) -> Topics:
    return Topics.from_dict((brief or {}).get("topics"))


def _chosen(topics: Topics, said: str) -> str | None:
    """Which business the owner picked when asked "which first?", or None when unclear."""
    if len(topics.items) < 2:
        return None
    first, second = topics.items[0], topics.items[-1]
    if FIRST_ONE.search(said) and not SECOND_ONE.search(said):
        return first["id"]
    if SECOND_ONE.search(said) and not FIRST_ONE.search(said):
        return second["id"]
    mine = _stems(said)
    a, b = len(mine & _stems(first["label"])), len(mine & _stems(second["label"]))
    if a > b:
        return first["id"]
    if b > a:
        return second["id"]
    return None


def observe(
    topics: Topics, said: str, history_before: list[str] | None = None
) -> tuple[Topics, Event]:
    """The pointer after the owner's message. `history_before`: the owner's earlier messages, used
    to label the first business. Never raises, never invents a business without the signal."""
    said = said or ""
    if topics.pending and topics.items:
        if SECOND_BUSINESS.search(said):
            pass  # a third business, or the same one again: handled below as a second business
        else:
            picked = _chosen(topics, said)
            if picked is not None:
                other = next((i["id"] for i in topics.items if i["id"] != picked), None)
                return Topics(topics.items, picked, False), Event("steered", picked, other)
            # not a clear pick: the owner talks on about the active (first) business
            return Topics(topics.items, topics.active or topics.items[0]["id"], False), NONE
    if SECOND_BUSINESS.search(said):
        items = list(topics.items)
        if not items:
            first = _label((history_before or [""])[0])
            items.append({"id": "b1", "label": first})
        if len(items) > 1 and items[-1]["label"] == _label(said):
            return topics, Event(
                "second_business", items[-1]["id"], topics.active
            )  # same message again
        if len(items) < 5:
            items.append({"id": f"b{len(items) + 1}", "label": _label(said)})
        active = topics.active or items[0]["id"]
        return Topics(items, active, True), Event("second_business", items[-1]["id"], active)
    if topics.items and len(topics.items) > 1 and GO_BACK.search(said):
        back = next((i["id"] for i in topics.items if i["id"] != topics.active), None)
        if back is not None:
            return Topics(topics.items, back, False), Event("returned", back, topics.active)
    if SWITCH.search(said):
        return topics, Event("switch", topics.active)
    return topics, NONE


NOTES = {
    "second_business": (
        "The owner has just told you about a second, different business. Engage it with one real "
        "thought in their own words (a reframe, a link to what they said, or a number worked out "
        "from their words); never just 'noted' or 'noted separately'. Give no ideas for either "
        "business in this message and make no offer. Keep the two businesses apart and end with "
        "exactly one question, last: which business to start with (for example 'Dono karobar ke "
        "naqshe alag rakhte hain. Pehle kis se shuru karein?', in their language)."
    ),
    "steered": (
        "The owner chose which business to start with. Work on that business only, with its own "
        "words; park the other with one short clause and promise to come back to it. No ideas "
        "about "
        "the parked business unless they ask."
    ),
    "returned": (
        "The owner asked to go back to the earlier business. Resume it where the map left off, in "
        "one short clause say the other is parked, and give no ideas about the parked one unless "
        "asked."
    ),
    "switch": (
        "The owner moved to a new topic. Answer the new topic first. Park the old thread in at "
        "most "
        "one clause. No new ideas about the old thread unless they ask."
    ),
}


def note(event: Event, topics: Topics) -> str:
    """The instruction for the model for this message ("" when nothing changed)."""
    text = NOTES.get(event.kind, "")
    if not text:
        return ""
    if event.kind in ("steered", "returned") and topics.label_of(event.topic):
        text += f" The business to work on: {topics.label_of(event.topic)}."
    return text


def reply_problem(
    event: Event, reply: str, ideas_in_reply: int, asked_for_ideas: bool = False
) -> str | None:
    """Why the reply breaks 17.3 for this message, or None. After a second business is named the
    reply carries no ideas, ends in the one "which first?" question, and never announces a note;
    after a switch of topic the reply gives no ideas for the parked thread unless the owner asked
    for ideas in this same message."""
    if event.kind == "second_business":
        if ideas_in_reply and not asked_for_ideas:
            return (
                "the owner named a second business: give no ideas for either business yet; "
                "engage it with one thought and ask which to start with"
            )
        if not reply.rstrip().endswith(("?", "؟")):
            return (
                "the owner named a second business: end with one question asking which business to "
                "start with"
            )
    elif event.kind == "switch" and ideas_in_reply and not asked_for_ideas:
        return (
            "the owner changed topic: give no new ideas about the thread you parked; answer the "
            "topic they moved to"
        )
    return None
