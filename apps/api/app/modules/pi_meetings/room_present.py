"""What pi presents in a room: slides, and which one is on show.

A person on the team starts it, so someone is always choosing what the room sees. pi shows ONE
thing today: a recap, made from what the team already APPROVED from this customer's earlier calls
(the same points pi remembers, `meeting_memory.earlier_calls`) and the notes taken in this call.
The slides are plain text, cleaned like every other thing pi shows: a line with a price, an amount,
a discount or a contact detail is left out, and nothing is shown that the redactor would have had
to hide. When there is nothing approved and nothing noted there is nothing to present.

The state is one small JSON value on the room row, written only by the people's requests and read
by the room agent on every beat (`Orders.present`): `{"on", "index", "slides", "v"}`. The agent
draws the slide (`slide_render`) and publishes it as pi's video; `v` rises on every start so a
restarted agent starts from the current slide.
"""

from datetime import date
from typing import Any

from app.modules.pi_meetings import chapters

MAX_SLIDES = 8
MAX_BULLETS = 5
BULLET_CHARS = 150
HEADING_CHARS = 60
TITLE = "Where we left off"
CLOSING = "Is this right?"
KIND_LABELS = {
    "next_step": "Next step",
    "commitment": "Agreed",
    "action": "To do",
    "decision": "Decided",
    "problem": "Problem",
    "requirement_explicit": "Need",
    "summary": "Summary",
}


def _bullet(point: str) -> str:
    """'next_step: Send the layout (by Friday)' as 'Next step: Send the layout (by Friday)'."""
    kind, _, words = point.partition(":")
    label = KIND_LABELS.get(kind.strip())
    text = words.strip() if label and words else point.strip()
    cleaned = chapters.safe(text, BULLET_CHARS)
    return f"{label}: {cleaned}" if label and cleaned else cleaned


def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d %B %Y").lstrip("0")
    except ValueError:
        return ""


def build(earlier: list[dict[str, Any]], notes: list[str]) -> list[dict[str, Any]]:
    """The recap slides, or [] when there is nothing approved or noted to show."""
    content: list[dict[str, Any]] = []
    for call in earlier[:3]:
        bullets = [b for b in (_bullet(str(p)) for p in call.get("points") or []) if b]
        when = _day(str(call.get("when") or ""))
        if bullets:
            heading = f"Our call on {when}" if when else "Our earlier call"
            content.append(
                {"kind": "content", "heading": heading, "bullets": bullets[:MAX_BULLETS]}
            )
    today = [b for b in (chapters.safe(n, BULLET_CHARS) for n in notes) if b]
    if today:
        content.append(
            {"kind": "content", "heading": "Noted in today's call", "bullets": today[:MAX_BULLETS]}
        )
    if not content:
        return []
    slides = [
        {"kind": "title", "heading": TITLE, "bullets": ["What we agreed, and what we noted today"]},
        *content,
        {"kind": "title", "heading": CLOSING, "bullets": ["Tell us what to add or change"]},
    ]
    return slides[:MAX_SLIDES]


def start(slides: list[dict[str, Any]], previous: Any) -> dict[str, Any]:
    """A new presentation at its first slide (`v` rises, so an agent that restarted can tell)."""
    old = int(previous.get("v") or 0) if isinstance(previous, dict) else 0
    return {"on": True, "index": 0, "slides": slides, "v": old + 1}


def go(state: Any, *, step: int | None = None, index: int | None = None) -> dict[str, Any]:
    """Move to another slide, never past the ends. Nothing changes when nothing is presented."""
    value = dict(state) if isinstance(state, dict) else {}
    slides = value.get("slides") or []
    if not value.get("on") or not slides:
        return value
    here = int(value.get("index") or 0)
    target = index if index is not None else here + (step or 0)
    value["index"] = max(0, min(len(slides) - 1, target))
    return value


def stop(state: Any) -> dict[str, Any]:
    """The presentation is over (the slides are dropped: they hold what customers said)."""
    old = int(state.get("v") or 0) if isinstance(state, dict) else 0
    return {"on": False, "index": 0, "slides": [], "v": old}


def summary(state: Any) -> dict[str, Any]:
    """What the room page needs: whether something is on show, where, and its heading."""
    value = state if isinstance(state, dict) else {}
    slides = value.get("slides") or []
    index = int(value.get("index") or 0)
    on = bool(value.get("on")) and bool(slides)
    return {
        "on": on,
        "index": index,
        "total": len(slides),
        "heading": str(slides[index].get("heading", "")) if on and index < len(slides) else "",
    }
