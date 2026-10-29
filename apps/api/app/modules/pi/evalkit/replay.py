"""Scripted replay: runs a case's recorded model output through the REAL extraction path
(`problem_extract.extract`: caps, per-note checks, known-title filter) with no model call, and turns
the surviving problem notes into records for the scorers. It tests the code around the model, not
the model. A real-model run swaps `Manager` for the real one (owner approval and budget needed)."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from app.modules.pi import problem_extract as pe

EXTRA_FIELDS = ("cause", "cause_status", "money_text")


class ScriptedManager:
    """Answers the extractor with the case's recorded notes, as a model would."""

    def __init__(self, notes: list[dict[str, Any]]) -> None:
        self.notes = notes

    async def complete_structured(self, scope: Any, model: Any, **kwargs: Any) -> Any:
        fields = pe.SimpleNote.model_fields
        found = [pe.SimpleNote(**{k: v for k, v in n.items() if k in fields}) for n in self.notes]
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
        record = {
            "title": note.title,
            "user_words": list(note.user_words),
            "summary": note.summary,
        }
        for key in EXTRA_FIELDS:
            if key in extra.get(note.title.lower(), {}):
                record[key] = extra[note.title.lower()][key]
        records.append(record)
    return records


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        loaded: list[dict[str, Any]] = json.load(handle)
    return loaded
