"""What an insight may say, enforced in code (never only in the prompt).

The model proposes; this module decides what is kept. An insight reaches a reviewer only if:

* its kind and basis are known, and its text is non-empty after redaction;
* a `stated` insight cites at least one real transcript segment (an ordinal that exists), and it
  only keeps an owner or a due date when the cited words really contain them;
* an inferred, estimated or recommended insight never carries an owner or a due date, and never
  carries a price: pi does not price (a reviewer does, in the quote);
* nothing is kept twice (same kind and text).

Redaction (card, ID, account, e-mail, phone, a third party's name) goes through
`memory_ledger.redacted`, the single path the rest of the brain uses.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings.models import INSIGHT_BASES, INSIGHT_KINDS

MAX_INSIGHTS = 60
TEXT_CAP = 600
MAX_REFS = 12

# a currency sign or code next to a number, in the forms owners write them (Rs 5,000, PKR 5000, $20)
PRICE = re.compile(
    r"(?:\b(?:rs|pkr|usd|aed|gbp|eur|inr)\.?\s*\d|[$£€₨]\s*\d"
    r"|\d[\d,.]*\s*(?:k|rs|pkr|usd|aed|gbp|eur|rupees?|rupay[ae]?|dollars?|dirhams?"
    r"|hazaar|hazar|lakhs?|lacs?)\b"
    r"|\b(?:hazaar|hazar|lakhs?|lacs?)\b)",
    re.IGNORECASE,
)
# who may own a stated action: a role, never a name
ROLES = frozenset({"customer", "staff"})


@dataclass(frozen=True)
class Segment:
    ordinal: int
    text: str
    speaker: str = ""


@dataclass
class Insight:
    kind: str
    basis: str
    text: str
    confidence: int = 0
    segment_refs: list[int] = field(default_factory=list)
    owner_label: str = ""
    due_text: str = ""


def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _refs(raw: Iterable[object], known: set[int]) -> list[int]:
    out: list[int] = []
    for item in raw or []:
        try:
            ordinal = int(item)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            continue
        if ordinal in known and ordinal not in out:
            out.append(ordinal)
    return out[:MAX_REFS]


def validate(
    raw: Sequence[object],
    segments: Sequence[Segment],
    speakers: Iterable[str] = (),
) -> tuple[list[Insight], list[str]]:
    """The insights that may be shown to a reviewer, and why each dropped one was dropped.

    `raw` is what the model returned (objects with the insight fields, or dicts). Never raises on a
    malformed item: it is dropped and named in the second list."""
    by_ordinal = {s.ordinal: s for s in segments}
    known = set(by_ordinal)
    # only a role may own an action: a name from a transcript is never written out as the owner
    owners = {r: r.capitalize() for r in ROLES}
    kept: list[Insight] = []
    dropped: list[str] = []
    seen: set[tuple[str, str]] = set()

    def get(item: object, key: str, default: object = "") -> object:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    for item in raw:
        if len(kept) >= MAX_INSIGHTS:
            dropped.append("too_many")
            break
        kind = str(get(item, "kind")).strip()
        basis = str(get(item, "basis")).strip()
        if kind not in INSIGHT_KINDS or basis not in INSIGHT_BASES:
            dropped.append("unknown_kind_or_basis")
            continue
        text = redacted(get(item, "text"), TEXT_CAP)
        if not text:
            dropped.append("empty_text")
            continue
        refs = _refs(get(item, "segment_refs", []) or [], known)  # type: ignore[arg-type]
        if basis == "stated" and not refs:
            if kind != "summary":
                dropped.append("stated_without_source")
                continue
            basis = "inferred"  # a summary is the model's own wording: never "stated"
        owner = _norm(str(get(item, "owner_label")))
        due = " ".join(str(get(item, "due_text")).split())[:80]
        if basis != "stated":
            if PRICE.search(text):
                dropped.append("price_in_ai_conclusion")
                continue
            owner = due = ""
        else:
            cited = _norm(" ".join(by_ordinal[r].text for r in refs))
            owner = owners.get(owner, "")  # a name nobody labelled is a guess: never the owner
            if due and _norm(due) not in cited:
                due = ""  # a deadline the cited words do not contain was not stated
        key = (kind, _norm(text))
        if key in seen:
            dropped.append("duplicate")
            continue
        seen.add(key)
        try:
            confidence = max(0, min(100, int(get(item, "confidence", 0) or 0)))  # type: ignore[call-overload]
        except (TypeError, ValueError):
            confidence = 0
        kept.append(
            Insight(
                kind=kind,
                basis=basis,
                text=text,
                confidence=confidence,
                segment_refs=refs,
                owner_label=owner if basis == "stated" else "",
                due_text=due,
            )
        )
    return kept, dropped
