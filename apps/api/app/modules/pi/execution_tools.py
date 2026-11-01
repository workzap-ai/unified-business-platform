# ruff: noqa: E501
"""Controlled execution (Level 3): the allow-list of INTERNAL tools. Pure.

Exactly five tools exist: create a staff task, draft a document, schedule a follow-up, record a note,
update a problem's status. All are internal (they write records inside this workspace and nothing else),
reversible, and none sends anything to a third party, takes a payment, handles a credential or runs
code. A tool outside this list is refused even if an older scope names it. Every argument is screened
(`execution_screen`) and shape-checked here; a handler returns an `Effect` (a plain record the caller
stores) and never reaches outside the process. Results are screened too.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.modules.pi import execution_screen as screen
from app.modules.pi import taxonomy
from app.modules.pi.execution_scope import TOOL_CLASSES

# the tool name -> the evidence kind its effect counts as (EVIDENCE_KINDS in execution_task)
ALLOW_LIST: dict[str, str] = {
    "create_staff_task": "staff_observation",
    "create_draft_document": "document",
    "schedule_followup": "staff_observation",
    "write_note": "staff_observation",
    "update_problem_status": "staff_observation",
}
PROBLEM_STATUSES = frozenset(
    {"confirmed", "in_build", "parked"}
)  # never "resolved": that is an outcome
MAX_FIELD = 2000


@dataclass(frozen=True)
class Effect:
    tool: str
    kind: str  # evidence kind
    summary: str
    record: Mapping[str, Any]  # the internal record the caller stores (plain, already screened)
    undo: Mapping[str, Any]  # what reverses it (an internal record the caller applies on rollback)


def is_allowed(tool: Any) -> bool:
    return (
        isinstance(tool, str)
        and tool in ALLOW_LIST
        and TOOL_CLASSES.get(tool) == "write_reversible"
    )


def _text(p: Mapping[str, Any], key: str, required: bool = True) -> str | None:
    v = p.get(key)
    if v is None and not required:
        return ""
    if not isinstance(v, str) or (required and not v.strip()) or len(v) > MAX_FIELD:
        return None
    return v.strip()


def _only(p: Mapping[str, Any], keys: set[str]) -> bool:
    return set(p) <= keys


def _staff_task(p: Mapping[str, Any]) -> Effect | str:
    title, detail = _text(p, "title"), _text(p, "detail", False)
    if not _only(p, {"title", "detail", "assignee_role"}) or title is None or detail is None:
        return "create_staff_task needs a title (and optionally detail, assignee_role)"
    role = _text(p, "assignee_role", False)
    if role is None:
        return "assignee_role must be text"
    rec = {
        "type": "staff_task",
        "title": title,
        "detail": detail,
        "assignee_role": role,
        "status": "open",
    }
    return Effect(
        "create_staff_task",
        "staff_observation",
        f"staff task: {title[:80]}",
        rec,
        {"set": "cancelled"},
    )


def _draft_doc(p: Mapping[str, Any]) -> Effect | str:
    title, body = _text(p, "title"), _text(p, "body")
    if not _only(p, {"title", "body"}) or title is None or body is None:
        return "create_draft_document needs title and body"
    rec = {
        "type": "draft_document",
        "title": title,
        "body": body,
        "status": "draft",
        "reviewed": False,
    }
    return Effect(
        "create_draft_document",
        "document",
        f"draft document: {title[:80]}",
        rec,
        {"set": "withdrawn"},
    )


def _followup(p: Mapping[str, Any]) -> Effect | str:
    note, days = _text(p, "note"), p.get("due_in_days")
    if not _only(p, {"note", "due_in_days"}) or note is None:
        return "schedule_followup needs note and due_in_days"
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
        return "due_in_days must be a whole number from 1 to 30"
    rec = {
        "type": "followup",
        "note": note,
        "due_in_days": days,
        "status": "scheduled",
        "audience": "staff",
    }
    return Effect(
        "schedule_followup",
        "staff_observation",
        f"follow-up in {days} days",
        rec,
        {"set": "cancelled"},
    )


def _note(p: Mapping[str, Any]) -> Effect | str:
    text = _text(p, "text")
    if not _only(p, {"text"}) or text is None:
        return "write_note needs text"
    rec = {"type": "note", "text": text, "audience": "staff"}
    return Effect("write_note", "staff_observation", "note recorded", rec, {"set": "withdrawn"})


def _problem_status(p: Mapping[str, Any]) -> Effect | str:
    ref, status = _text(p, "problem_ref"), p.get("status")
    prior = _text(p, "prior_status")
    if not _only(p, {"problem_ref", "status", "prior_status"}) or ref is None or prior is None:
        return "update_problem_status needs problem_ref, status and prior_status (for rollback)"
    try:
        UUID(ref)
    except ValueError:
        return "problem_ref must be the problem's id"
    if prior not in taxonomy.STATUSES:
        return "prior_status must be a known problem status"
    if status not in PROBLEM_STATUSES:
        return "status must be confirmed, in_build or parked"
    rec = {"type": "problem_status", "problem_ref": ref, "status": status, "prior_status": prior}
    return Effect(
        "update_problem_status",
        "staff_observation",
        f"problem {ref[:40]} to {status}",
        rec,
        {"set_status": prior},
    )


_HANDLERS: dict[str, Callable[[Mapping[str, Any]], Effect | str]] = {
    "create_staff_task": _staff_task,
    "create_draft_document": _draft_doc,
    "schedule_followup": _followup,
    "write_note": _note,
    "update_problem_status": _problem_status,
}


def validate(tool: Any, params: Any) -> str | None:
    """None when the call is acceptable; otherwise the reason. Never raises."""
    try:
        if not is_allowed(tool):
            return "tool is not on the internal allow-list"
        if not isinstance(params, Mapping):
            return "arguments must be a mapping"
        bad = screen.value_issue(dict(params))
        if bad:
            return f"arguments refused: {bad}"
        out = _HANDLERS[tool](params)
        return out if isinstance(out, str) else None
    except Exception:  # noqa: BLE001
        return "unreadable arguments"


def run_tool(tool: Any, params: Any) -> Effect | str:
    """The effect of an allow-listed call, or the refusal reason. Results are screened as well."""
    try:
        why = validate(tool, params)
        if why:
            return why
        out = _HANDLERS[str(tool)](params)
        if isinstance(out, str):
            return out
        bad = screen.value_issue({"summary": out.summary, "record": dict(out.record)})
        if bad:
            return f"result refused: {bad}"
        return out
    except Exception:  # noqa: BLE001
        return "tool failed"
