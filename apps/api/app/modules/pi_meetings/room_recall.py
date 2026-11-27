"""What pi remembers of ONE call, and how it survives an agent restart.

Inside a call pi keeps short notes of what the person told it (`Session.facts`), the language the
person asked for, how many free suggestions it gave and the last few lines said. They live in the
agent's memory, so a restart (a deploy, a crash) used to make pi forget everything and ask "what
does your business do?" again. `pack` turns them into a small JSON note kept on the room row after
every turn; `restore` puts them back when the next agent takes the room.

Only redacted, short text is kept (the same text the transcript and the model already see), at most
`NOTES_CHARS` of it, and it goes with the room when the meeting is erased. `merge_fact` keeps the
notes clean: a correction replaces the old fact, a near-duplicate is not added twice.
"""

import re
from typing import TYPE_CHECKING, Any

from app.modules.pi_meetings import voice

if TYPE_CHECKING:
    from app.modules.pi_meetings.room_speech import Session

KEEP_FACTS = voice.FACTS_KEPT * 2
RECENT_LINES = 8  # the last lines said, so pi knows what it just asked
LINE_CHARS = 220
NOTES_CHARS = 6000  # a hard ceiling on what is stored per room
SAME = 0.8  # share of words two facts must have in common to be the same fact
CORRECTS = 0.5  # share of words a correction must have in common with what it replaces
WORD = re.compile(r"\w{2,}", re.UNICODE)


def _words(text: str) -> set[str]:
    return {w.lower() for w in WORD.findall(text)}


def _overlap(a: str, b: str) -> float:
    left, right = _words(a), _words(b)
    return len(left & right) / min(len(left), len(right)) if left and right else 0.0


def merge_fact(facts: list[str], new: str, replaces: str = "") -> None:
    """Add what pi just learned. A fact that corrects an earlier one takes its place; the same
    fact in new words replaces the old wording; nothing is added twice."""
    new = new.strip()
    if not new:
        return
    if replaces.strip():
        scored = [(_overlap(f, replaces), i) for i, f in enumerate(facts)]
        best = max(scored, default=(0.0, -1))
        if best[0] >= CORRECTS:
            facts.pop(best[1])
    for i, fact in enumerate(facts):
        if _overlap(fact, new) >= SAME:
            facts[i] = new
            return
    facts.append(new)
    del facts[:-KEEP_FACTS]


def pack(session: "Session") -> dict[str, Any]:
    """The notes to keep on the room row (small, redacted)."""
    own = session.history[1:] if session.history and session.history[0].pi else session.history
    # (the opening line is rebuilt on a restart, not stored)
    notes: dict[str, Any] = {
        "facts": [f[: voice.FACT_CHARS] for f in session.facts[-KEEP_FACTS:]],
        "language": session.language_pref,
        "ideas": session.ideas,
        "solution": session.wants_solution,
        "recent": [[int(h.pi), h.text[:LINE_CHARS]] for h in own[-RECENT_LINES:]],
    }
    while len(repr(notes)) > NOTES_CHARS and notes["recent"]:
        notes["recent"].pop(0)
    while len(repr(notes)) > NOTES_CHARS and notes["facts"]:
        notes["facts"].pop(0)
    return notes


def restore(session: "Session", notes: dict[str, Any] | None) -> None:
    """Put the notes back into a session that a restarted agent has just made."""
    if not isinstance(notes, dict) or not notes:
        return
    facts = notes.get("facts")
    if isinstance(facts, list):
        session.facts = [str(f)[: voice.FACT_CHARS] for f in facts if str(f).strip()][-KEEP_FACTS:]
    language = notes.get("language")
    if language in ("en", "ur"):
        session.language_pref = str(language)
    ideas = notes.get("ideas")
    if isinstance(ideas, int) and 0 <= ideas <= 50:
        session.ideas = max(session.ideas, ideas)
    session.wants_solution = bool(notes.get("solution")) or session.wants_solution
    recent = notes.get("recent")
    if isinstance(recent, list):
        for item in recent[-RECENT_LINES:]:
            if isinstance(item, (list, tuple)) and len(item) == 2 and str(item[1]).strip():
                session.history.append(voice.Said(bool(item[0]), str(item[1])[:LINE_CHARS]))
