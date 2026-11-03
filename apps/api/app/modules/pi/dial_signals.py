"""The three dial signals that only the conversation can know (spec 2.2, audit X6).

`dials.read_signals` takes `gap_hours` (return after a gap: trust up), `unasked_problem` (a problem
nobody asked about: openness and trust up) and `repaired` (a correction was repaired well: trust
up), but `estimate(texts)` replayed the owner's words alone, so none of them ever fired. This module
reads them from the chat history the prompt already holds, aligned to the owner's messages exactly
as `think_prompt._customer_messages` lists them (the history's owner messages, then the latest
one when it is not already the last).

- gap: hours since the owner's previous message (the latest message uses the context's
  `hours_since_previous_message`).
- unasked problem: the owner reports a problem right after a pi message that was not a question.
- good repair: the owner's previous message was a correction, pi answered, and this message is
  not a correction again.

Pure. A history without times just has no gap signal.
"""

import re
from datetime import UTC, datetime
from typing import Any

from app.modules.pi import dials

PROBLEM = dials._words(
    "problem|problems|issue|issues|trouble|losing|loss|losses|late|delay|delays|complain|"
    "complaints|struggle|struggling|not working|stuck|wasting|mess",
    "masla|masle|mushkil|dikkat|nuksan|nuqsan|shikayat|der ho|late ho|phans|kharab|pareshani",
)
QUESTION_END = ("?", "؟")
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")


def _when(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not STAMP.match(raw):
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace(" ", "T")[:19])
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _hours(later: datetime | None, earlier: datetime | None) -> float | None:
    if later is None or earlier is None:
        return None
    return max(0.0, (later - earlier).total_seconds() / 3600)


def _extra(
    text: str, *, previous_ai: str | None, gap: float | None, corrected_before: bool
) -> dict[str, object]:
    out: dict[str, object] = {}
    if gap is not None and gap >= dials.RETURN_GAP_HOURS:
        out["gap_hours"] = gap
    if (
        previous_ai is not None
        and previous_ai.strip()
        and not previous_ai.rstrip().endswith(QUESTION_END)
        and PROBLEM.search(text)
    ):
        out["unasked_problem"] = True
    if corrected_before and not dials.CORRECTION.search(text):
        out["repaired"] = True
    return out


def extras(context: dict[str, Any], texts: list[str]) -> list[dict[str, object]]:
    """One dict of extra signals per owner message in `texts` (see the module docstring)."""
    history = context.get("history") or []
    out: list[dict[str, object]] = []
    previous_ai: str | None = None
    last_customer_at: datetime | None = None
    ai_since_correction = False
    corrected = False
    for item in history:
        role = item.get("role")
        if role == "ai":
            previous_ai = str(item.get("text") or "")
            ai_since_correction = ai_since_correction or corrected
        elif role == "customer":
            text = str(item.get("text") or "")
            at = _when(item.get("at"))
            out.append(
                _extra(
                    text,
                    previous_ai=previous_ai,
                    gap=_hours(at, last_customer_at),
                    corrected_before=corrected and ai_since_correction,
                )
            )
            last_customer_at = at or last_customer_at
            corrected = bool(dials.CORRECTION.search(text))
            ai_since_correction = False
            previous_ai = None
    latest = str(context.get("latest_customer_message") or "")
    if latest and len(out) == len(texts) - 1:
        hours = context.get("hours_since_previous_message")
        out.append(
            _extra(
                latest,
                previous_ai=previous_ai,
                gap=float(hours) if isinstance(hours, int | float) else None,
                corrected_before=corrected and ai_since_correction,
            )
        )
    return out[: len(texts)]


def estimate(context: dict[str, Any], texts: list[str]) -> dials.Dials:
    """The dials after the owner's messages with the conversation's own signals included."""
    return dials.estimate(texts, extras=extras(context, texts))


def latest_signals(context: dict[str, Any], texts: list[str]) -> dials.Signals:
    """The signals of the newest message, with the same extras the replay used."""
    more = extras(context, texts)
    last = more[len(texts) - 1] if len(more) >= len(texts) else {}
    return dials.read_signals(texts[-1], first_message=len(texts) == 1, **last)  # type: ignore[arg-type]
