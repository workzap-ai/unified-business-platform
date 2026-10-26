"""R-ANS-03: a request pi has not answered is answered first next time (platform spec Book 2 10.4).

Every request for a timeline or for a person is logged in the brief (`open_requests`) when the reply
did not address it. The next reply is sent back if it still does not (a request left open for one
pi turn must be dealt with before anything else). A solution request and a price question are not
tracked here: a solution request has its own carry-over (`solution_unanswered`, the application adds
the ideas), and the price answer is a fixed line the application writes.

The check is on words, not meaning: a reply addresses a timeline question when it says where the
timeline lives (the quote, the plan, the document, the team) and a request for a person when it
mentions the team or a person. That is enough to catch a reply that ignores the request completely,
which is what the guard is for.
"""

import re
from typing import Any

MAX_OPEN_TURNS = 3  # a request nobody could answer is dropped after this many replies
TIMELINE = re.compile(
    r"\b(?:kitne\s+din|kitna\s+waqt|kab\s+tak|kab\s+milega|kab\s+tayyar|how\s+long|how\s+many\s+days"
    r"|how\s+soon|when\s+(?:will|can)\s+(?:it|we|you)|by\s+when|delivery\s+date|timeline"
    r"|turnaround)\b",
    re.IGNORECASE,
)
HUMAN = re.compile(
    r"\b(?:insaan\s+se|kisi\s+insaan|real\s+person|a\s+human|talk\s+to\s+(?:a\s+)?(?:person|human|"
    r"someone)|speak\s+to\s+(?:a\s+)?(?:person|human|someone)|manager\s+se\s+baat|team\s+se\s+baat"
    r"|connect\s+me\s+(?:to|with))\b",
    re.IGNORECASE,
)
ADDRESSES: dict[str, re.Pattern[str]] = {
    "timeline": re.compile(
        r"\b(?:quote|solution\s+document|document|plan|estimate|schedule|team|workzap\s+will"
        r"|samay|waqt|din)\b",
        re.IGNORECASE,
    ),
    "human": re.compile(
        r"\b(?:team|person|human|colleague|someone|insaan|banda|manager)\b", re.IGNORECASE
    ),
}


def kinds(said: str) -> list[str]:
    """The tracked requests in a message: "timeline", "human"."""
    text = said or ""
    return [k for k, pattern in (("timeline", TIMELINE), ("human", HUMAN)) if pattern.search(text)]


def addressed(kind: str, reply: str, *, request_human: bool = False) -> bool:
    if kind == "human" and request_human:
        return True
    pattern = ADDRESSES.get(kind)
    return bool(pattern and pattern.search(reply or ""))


def update(
    previous: list[dict[str, Any]] | None,
    said: str,
    reply: str,
    *,
    request_human: bool = False,
) -> list[dict[str, Any]]:
    """The open requests after this turn: the earlier ones and the ones in this message that the
    reply did not address (each kept for at most `MAX_OPEN_TURNS` replies)."""
    carried = {str(e.get("kind")): int(e.get("turns") or 0) for e in previous or []}
    wanted = [*carried, *[k for k in kinds(said) if k not in carried]]
    still: list[dict[str, Any]] = []
    for kind in wanted:
        if addressed(kind, reply, request_human=request_human):
            continue
        turns = carried.get(kind, -1) + 1 if kind in carried else 1
        if turns <= MAX_OPEN_TURNS:
            still.append({"kind": kind, "turns": turns})
    return still


def unanswered(
    open_requests: list[dict[str, Any]] | None, reply: str, *, request_human: bool = False
) -> list[str]:
    """The requests left open last turn that this reply still does not address."""
    return [
        str(e["kind"])
        for e in open_requests or []
        if not addressed(str(e["kind"]), reply, request_human=request_human)
    ]
