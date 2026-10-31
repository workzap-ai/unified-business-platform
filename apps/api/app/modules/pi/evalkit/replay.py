"""Scripted replay: runs a case's recorded model output through the REAL extraction path
(`problem_extract.extract`: caps, per-note checks, known-title filter) with no model call, and turns
the surviving problem notes into records for the scorers. It tests the code around the model, not
the model. A real-model run swaps `Manager` for the real one (owner approval and budget needed)."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from app.modules.pi import problem_extract as pe
from app.modules.pi.problems import ProblemBook


def constraint_list(stored: dict[str, Any]) -> list[str]:
    """The stored constraints (budget, staff, deadline, cannot_change) as the scorers read them."""
    out = [str(stored[k]["text"]) for k in ("budget", "staff", "deadline") if stored.get(k)]
    out += [str(c["text"]) for c in stored.get("cannot_change") or []]
    return out


EXTRA_FIELDS = ("money_text",)
STATUS_OUT = {"owner_said": "owner_said", "confirmed": "confirmed", "pi_inferred": "hypothesis"}


def to_b2a(note: dict[str, Any]) -> dict[str, Any]:
    """A recorded note in the older shape (`cause`, `cause_status`, `constraints` as strings) as
    the B2a fields the extractor now writes, so the real save logic decides what the cause is."""
    out = dict(note)
    if "cause" in note and "cause_text" not in note:
        said = note.get("cause_status") in ("owner_said", "confirmed")
        words = [w for w in str(note["cause"]).split() if len(w) >= 3][:3]
        out.update(cause_text=note["cause"], cause_said=said, cause_words=words if said else [])
    if "constraints" in note and "cannot_change" not in note:
        out["cannot_change"] = [str(c) for c in note["constraints"]]
    return out


class ScriptedManager:
    """Answers the extractor with the case's recorded notes, as a model would."""

    def __init__(self, notes: list[dict[str, Any]]) -> None:
        self.notes = notes

    async def complete_structured(self, scope: Any, model: Any, **kwargs: Any) -> Any:
        fields = pe.SimpleNote.model_fields
        found = [
            pe.SimpleNote(**{k: v for k, v in to_b2a(n).items() if k in fields}) for n in self.notes
        ]
        return SimpleNamespace(value=pe.Extracted(found=found[: pe.MAX_NOTES]))


def context_for(case: dict[str, Any]) -> dict[str, Any]:
    *earlier, latest = case["messages"]
    return {
        "pi_mode": "brain",
        "latest_customer_message": latest,
        "history": [{"role": "customer", "text": t} for t in earlier],
        "noted_problems": [],
        "reply_language": case.get("language", "en"),
    }


def replay(case: dict[str, Any]) -> list[dict[str, Any]]:
    notes = (case.get("recorded") or {}).get("notes") or []
    ops = asyncio.run(pe.extract(ScriptedManager(notes), None, context_for(case)))
    extra = {str(n.get("title", "")).lower(): n for n in notes}
    records = []
    for op in ops:
        note = op.note
        if note is None:
            continue
        record: dict[str, Any] = {
            "title": note.title,
            "user_words": list(note.user_words),
            "summary": note.summary,
        }
        # the real save logic (problems.ProblemBook.requirement_values) over the owner's own words
        values, _ = ProblemBook.requirement_values(note, None, None, " ".join(case["messages"]))
        if values.get("constraints"):
            record["constraints"] = constraint_list(values["constraints"])
        if values.get("tried"):
            record["tried"] = [dict(t) for t in values["tried"]]
        if values.get("cause"):
            record["cause"] = values["cause"]["text"]
            record["cause_status"] = STATUS_OUT.get(values["cause"]["status"], "hypothesis")
        # the real save logic (problems.ProblemBook.requirement_values) over the owner's own words
        values, _ = ProblemBook.requirement_values(note, None, None, " ".join(case["messages"]))
        if values.get("constraints"):
            record["constraints"] = constraint_list(values["constraints"])
        if values.get("tried"):
            record["tried"] = [dict(t) for t in values["tried"]]
        if values.get("cause"):
            record["cause"] = values["cause"]["text"]
            record["cause_status"] = STATUS_OUT.get(values["cause"]["status"], "hypothesis")
        for key in EXTRA_FIELDS:
            if key in extra.get(note.title.lower(), {}):
                record[key] = extra[note.title.lower()][key]
        records.append(record)
    return records


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        loaded: list[dict[str, Any]] = json.load(handle)
    return loaded
