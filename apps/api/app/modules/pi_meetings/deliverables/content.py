"""What goes into a designed meeting document, and what must never.

Both documents (the summary PDF and the deck) are drawn from one `Content`. It is built ONLY from
insights a person has approved or edited (never from the raw transcript or from a pending
suggestion), so a document says what the team decided to keep. Every line is redacted again, and a
line that carries a price is left out and counted: pi does not price, the quote does.

An action's owner and deadline appear only when they were stated in the meeting (the insight has
`basis == 'stated'`; the database already guarantees it holds them only then). A conclusion pi drew
itself is labelled with its basis, so a reader can tell what was said from what was inferred.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.insight_rules import PRICE

LINE_CHARS = 320
SUMMARY_CHARS = 900
MAX_PER_SECTION = 12
ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

# section order and the heading of each (British spelling)
SECTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("problems", ("problem", "root_cause", "impact"), "What is going wrong"),
    ("needs", ("requirement_explicit", "requirement_implicit"), "What is needed"),
    ("decisions", ("decision", "commitment"), "Decisions and commitments"),
    ("actions", ("action", "next_step"), "Actions and next steps"),
    ("open", ("question", "risk"), "Open questions and risks"),
)
BASIS = {
    "stated": "said in the meeting",
    "inferred": "pi's reading",
    "estimate": "estimate",
    "recommendation": "recommendation",
}


@dataclass(frozen=True)
class Line:
    text: str
    basis: str  # the label shown beside the line, from BASIS
    owner: str = ""
    due: str = ""
    refs: tuple[int, ...] = ()


@dataclass
class Content:
    title: str
    when: str
    language: str  # 'ur' when the words are mostly Urdu script, else 'en'
    people: list[tuple[str, str]] = field(default_factory=list)  # (label, role)
    summary: str = ""
    sections: list[tuple[str, list[Line]]] = field(default_factory=list)
    dropped: int = 0  # lines left out (a price, or empty after redaction)
    used: int = 0  # approved insights the document is built from

    @property
    def empty(self) -> bool:
        return not self.summary and not any(lines for _, lines in self.sections)


def is_rtl(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ARABIC.match(c)) * 2 > len(letters)


def _clean(text: str, cap: int) -> str:
    return " ".join(redacted(text, cap).split())


def build(
    *,
    title: str,
    held_at: datetime | None,
    created_at: datetime | None,
    participants: list[tuple[str, str]],
    insights: list[Any],
) -> Content:
    """`insights` are rows with kind, basis, text, edited_text, review_status, owner_label, due_text
    and segment_refs. Pending and rejected ones are ignored here as a second check."""
    kept = [i for i in insights if i.review_status in ("approved", "edited")]
    stamp = held_at or created_at
    content = Content(
        title=_clean(title, 120) or "Meeting summary",
        when=stamp.strftime("%d %B %Y") if stamp else "",
        language="en",
        people=[(_clean(label, 60), role) for label, role in participants if label][:12],
        used=len(kept),
    )
    by_kind: dict[str, list[Line]] = {}
    for item in kept:
        words = _clean(
            item.edited_text or item.text, SUMMARY_CHARS if item.kind == "summary" else LINE_CHARS
        )
        if not words or PRICE.search(words):
            content.dropped += 1
            continue
        if item.kind == "summary":
            content.summary = content.summary or words
            continue
        stated = item.basis == "stated"
        by_kind.setdefault(item.kind, []).append(
            Line(
                text=words,
                basis=BASIS.get(item.basis, item.basis),
                owner=_clean(item.owner_label, 60) if stated else "",
                due=_clean(item.due_text, 80) if stated else "",
                refs=tuple(sorted(set(item.segment_refs or ())))[:6],
            )
        )
    for _key, kinds, heading in SECTIONS:
        lines = [line for kind in kinds for line in by_kind.get(kind, [])][:MAX_PER_SECTION]
        if lines:
            content.sections.append((heading, lines))
    sample = " ".join([content.summary] + [ln.text for _, ls in content.sections for ln in ls])
    content.language = "ur" if is_rtl(sample) else "en"
    return content
