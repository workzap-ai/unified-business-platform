# ruff: noqa: E501
"""Scripted multi-turn replay for the problem-solving cases (PS-0). No model call.

What runs is the CURRENT code path, turn by turn: `problem_extract.wants_extraction` (the live gate),
`problem_extract.extract` (caps, per-note checks, known-title filter) fed by the case's hand-written
reference notes through `replay.ScriptedManager`, and `figure_correction.numeric_correction` (the live
correction finder). What is scripted: the extractor's output (reference notes, not model output) and
pi's replies (reference replies). What is NOT run: the reply model, the flow state machine, the
database, the idea engines.

`live` records hold only what the live extractor shape (`SimpleNote`) can carry: a field the
reference note has but `SimpleNote` lacks (constraints, tried, cause, expected outcome) is dropped by
the real path, exactly as it would be live. `reference` records add those fields back from the note;
they exist only to check the scorers and show the ceiling if the extractor were extended.

A Held-out case is refused unless the caller holds an `access_log.Pass`.
"""

import asyncio
from typing import Any

from app.modules.pi import figure_correction as fc
from app.modules.pi import problem_extract as pe
from app.modules.pi.evalkit import access_log, replay, splits

REFERENCE_FIELDS = ("constraints", "tried", "cause", "cause_status", "expected_outcome")
LIVE_FIELDS = ("where", "since_text", "money_text", "of_total", "frequency_text")


def owner_turns(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in case["turns"] if t["role"] == "owner"]


def _fix_text(text: str, wrong: str, right: str) -> str:
    return fc.replace_figure(text, wrong, right) if fc.has_figure(text, wrong) else text


def apply_correction(record: dict[str, Any], wrong: str, right: str) -> dict[str, Any]:
    out = dict(record)
    for key in ("title", "summary", "money_text", "of_total"):
        if isinstance(out.get(key), str):
            out[key] = _fix_text(out[key], wrong, right)
    out["user_words"] = [_fix_text(str(w), wrong, right) for w in out.get("user_words") or []]
    return out


def replay_case(
    case: dict[str, Any], *, held_out_ok: access_log.Pass | None = None
) -> dict[str, Any]:
    if splits.split_of(case) == splits.HELD_OUT and not isinstance(held_out_ok, access_log.Pass):
        raise PermissionError("replaying a Held-out case needs an access log")
    turns = owner_turns(case)
    by_turn = (case.get("recorded") or {}).get("notes_by_turn") or {}
    live: list[dict[str, Any]] = []
    reference: list[dict[str, Any]] = []
    noted: list[dict[str, Any]] = []
    corrections: list[dict[str, Any]] = []
    gate: list[bool] = []
    said: list[str] = []
    for index, turn in enumerate(turns):
        text = turn["text"]
        context: dict[str, Any] = {
            "pi_mode": "brain",
            "flow": {"state": "S1_LISTENING" if index == 0 else "S2_CLARIFYING"},
            "latest_customer_message": text,
            "history": [{"role": "customer", "text": t} for t in said],
            "noted_problems": noted,
            "reply_language": case.get("language", "en"),
            "solution_asked": bool(turn.get("asks_idea")),
        }
        said.append(text)
        fix = fc.numeric_correction(text, said[:-1]) if index else None
        if fix:
            wrong, right = fix
            corrections.append({"turn": index, "wrong": wrong, "right": right})
            live = [apply_correction(r, wrong, right) for r in live]
            reference = [apply_correction(r, wrong, right) for r in reference]
        allowed = pe.wants_extraction(context, "", [])
        gate.append(allowed)
        notes = by_turn.get(str(index)) or []
        if not allowed or not notes:
            continue
        ops = asyncio.run(pe.extract(replay.ScriptedManager(notes), None, context))
        extra = {str(n.get("title", "")).lower(): n for n in notes}
        for op in ops:
            if op.note is None:
                continue
            note = op.note
            noted.append({"ref": f"p{len(noted) + 1}", "title": note.title})
            record = {
                "title": note.title,
                "user_words": list(note.user_words),
                "summary": note.summary,
                **{k: getattr(note, k) for k in LIVE_FIELDS},
                "turn": index,
            }
            source = extra.get(note.title.lower(), {})
            live.append(dict(record))
            reference.append({**record, **{k: source[k] for k in REFERENCE_FIELDS if k in source}})
    return {"live": live, "reference": reference, "corrections": corrections, "gate": gate}
