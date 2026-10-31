# ruff: noqa: E501
"""Controlled execution (Q-8): the task record, its state machine, dependencies, bounded tool authority
and the pre-execution gate. Pure and dry-run: nothing here performs a business action or calls anything
outside the process; the "gate" only says yes or no with reasons. Design:
docs/pi-saas/pi-controlled-execution-design.md (sections 3 to 6, 11).

Held here:
- States: proposed, approved, running, verifying, done, failed, rolled_back; only the legal moves.
- 'done' is reachable only through `complete_task` with a verification record: evidence, an acceptance
  check, a named human verifier. A model statement is never evidence.
- A task cannot be approved without a rollback plan; a rolled-back task carries a recovery record.
- `check_can_execute` is fail-closed and never raises.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.modules.pi import execution_audit as audit
from app.modules.pi.execution_scope import (
    FORBIDDEN_APPROVERS,
    NEEDS_OWN_APPROVAL,
    NEVER_SCOPED,
    TOOL_CLASSES,
    ApprovalCue,
    ApprovedScope,
    classify_approval,
)

MAX_ID = 120
MAX_TEXT = 2000
MAX_STEPS = 50
MAX_EVIDENCE = 50
MAX_TASKS = 5000
MAX_DEPS = 50
MAX_PARAM_NODES = 500
MAX_PARAM_DEPTH = 4
MAX_PARAM_CHARS = 10_000
ACTION_APPROVAL_TTL = timedelta(minutes=15)


class TaskState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    VERIFYING = "verifying"
    DONE = "done"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


LEGAL_MOVES: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PROPOSED: frozenset({TaskState.APPROVED}),
    TaskState.APPROVED: frozenset({TaskState.RUNNING}),
    TaskState.RUNNING: frozenset({TaskState.VERIFYING, TaskState.FAILED}),
    TaskState.VERIFYING: frozenset({TaskState.DONE, TaskState.FAILED}),
    TaskState.FAILED: frozenset({TaskState.ROLLED_BACK}),
    TaskState.DONE: frozenset(),
    TaskState.ROLLED_BACK: frozenset(),
}
EVIDENCE_KINDS = frozenset(
    {"document", "order_status", "file", "customer_message", "staff_observation"}
)


def _named(v: Any) -> bool:
    return (
        isinstance(v, str)
        and bool(v.strip())
        and len(v) <= MAX_ID
        and v.strip().casefold() not in FORBIDDEN_APPROVERS
    )


def _text(v: Any, limit: int = MAX_TEXT) -> bool:
    return isinstance(v, str) and bool(v.strip()) and len(v) <= limit


@dataclass(frozen=True)
class RollbackPlan:
    steps: tuple[str, ...]
    reversible: bool
    owner: str
    check: str  # how anyone can see the rollback worked


@dataclass(frozen=True)
class Evidence:
    ref: str  # points to a record, never free-text claims
    kind: str
    recorded_by: str


@dataclass(frozen=True)
class Verification:
    acceptance_id: str
    acceptance_statement: str
    evidence: tuple[Evidence, ...]
    passed: bool
    verifier: str


@dataclass(frozen=True)
class RecoveryRecord:
    restored_state: str
    evidence: tuple[Evidence, ...]
    recorded_by: str


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    owner: str
    creator: str
    scope_sha: str
    depends_on: tuple[str, ...] = ()
    state: TaskState = TaskState.PROPOSED
    rollback: RollbackPlan | None = None
    verification: Verification | None = None
    recovery: RecoveryRecord | None = None
    failure_reason: str = ""


@dataclass(frozen=True)
class TaskResult:
    ok: bool
    task: Task | None
    reasons: tuple[str, ...]


def _no(task: Task | None, *reasons: str) -> TaskResult:
    return TaskResult(False, task, tuple(reasons))


def new_task(
    *,
    id: Any,
    title: Any,
    owner: Any,
    creator: Any,
    scope_sha: Any,
    depends_on: Any = (),
    rollback: Any = None,
) -> TaskResult:
    try:
        r: list[str] = []
        if not _named(id):
            r.append("task id is malformed")
        if not _text(title):
            r.append("title is empty or too long")
        if not _named(owner):
            r.append("owner must be a named person, never pi or a model")
        if not _named(creator):
            r.append("creator must be a named person")
        if not isinstance(scope_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", scope_sha):
            r.append("scope hash is malformed")
        deps = tuple(depends_on) if isinstance(depends_on, (list, tuple)) else None
        if deps is None or len(deps) > MAX_DEPS or not all(_named(d) for d in deps):
            r.append("dependencies are malformed")
            deps = ()
        elif id in deps:
            r.append("a task cannot depend on itself")
        if rollback is not None and rollback_issues(rollback):
            r.append("rollback plan is malformed")
        if r:
            return _no(None, *r)
        return TaskResult(
            True,
            Task(
                str(id),
                str(title),
                str(owner),
                str(creator),
                str(scope_sha),
                deps,
                TaskState.PROPOSED,
                rollback,
            ),
            (),
        )
    except Exception:  # noqa: BLE001
        return _no(None, "malformed input")


def rollback_issues(plan: Any) -> list[str]:
    """Empty list means the plan is acceptable. A plan that says it is not reversible blocks approval."""
    if not isinstance(plan, RollbackPlan):
        return ["no rollback plan"]
    out: list[str] = []
    if (
        not isinstance(plan.steps, tuple)
        or not plan.steps
        or len(plan.steps) > MAX_STEPS
        or not all(_text(s) for s in plan.steps)
    ):
        out.append("rollback steps are missing or malformed")
    if plan.reversible is not True:
        out.append("the action is not reversible, so it cannot be a task")
    if not _named(plan.owner):
        out.append("rollback owner must be a named person")
    if not _text(plan.check):
        out.append("rollback has no check")
    return out


def _move(task: Task, to: TaskState) -> str | None:
    if not isinstance(task, Task) or not isinstance(task.state, TaskState):
        return "not a task"
    if to not in LEGAL_MOVES.get(task.state, frozenset()):
        return f"illegal move {getattr(task.state, 'value', '?')} to {to.value}"
    return None


def _scope_issues(task: Task, scope: Any, now: Any) -> list[str]:
    if not isinstance(now, datetime) or now.tzinfo is None:
        return ["now must be a timezone-aware datetime"]
    if not isinstance(scope, ApprovedScope):
        return ["no approved scope"]
    out: list[str] = []
    if not scope.is_intact():
        out.append("scope record was altered")
    elif scope.scope_sha != task.scope_sha:
        out.append("scope changed since the task was written, a new approval is needed")
    if not scope.is_live(now):
        out.append("scope has expired")
    return out


def approve_task(task: Task, scope: Any, now: Any) -> TaskResult:
    try:
        bad = _move(task, TaskState.APPROVED)
        if bad:
            return _no(task, bad)
        r = _scope_issues(task, scope, now)
        r += rollback_issues(task.rollback)
        if not r and scope.approver.strip().casefold() in {
            task.owner.strip().casefold(),
            task.creator.strip().casefold(),
        }:
            r.append("approver must differ from the task owner and creator")
        if r:
            return _no(task, *r)
        return TaskResult(True, replace(task, state=TaskState.APPROVED), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


def start_task(task: Task, scope: Any, now: Any, dependency_states: Any = None) -> TaskResult:
    try:
        bad = _move(task, TaskState.RUNNING)
        if bad:
            return _no(task, bad)
        r = _scope_issues(task, scope, now) + _dependency_issues(task, dependency_states)
        if r:
            return _no(task, *r)
        return TaskResult(True, replace(task, state=TaskState.RUNNING), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


def mark_performed(task: Task, performed_note: Any) -> TaskResult:
    """running to verifying: the person who did the work says what was done. This is not 'done'."""
    bad = _move(task, TaskState.VERIFYING)
    if bad:
        return _no(task, bad)
    if not _text(performed_note):
        return _no(task, "a note of what was performed is required")
    return TaskResult(True, replace(task, state=TaskState.VERIFYING), ())


def verification_issues(task: Task, v: Any) -> list[str]:
    if not isinstance(v, Verification):
        return ["no verification record"]
    out: list[str] = []
    if not _named(v.acceptance_id) or not _text(v.acceptance_statement):
        out.append("acceptance check is missing")
    if v.passed is not True:
        out.append("the acceptance check did not pass")
    if not _named(v.verifier) or v.verifier.strip().casefold() == task.owner.strip().casefold():
        out.append("verifier must be a named person other than the task owner")
    if not isinstance(v.evidence, tuple) or not v.evidence or len(v.evidence) > MAX_EVIDENCE:
        out.append("evidence is missing")
    else:
        for e in v.evidence:
            if (
                not isinstance(e, Evidence)
                or e.kind not in EVIDENCE_KINDS
                or not _text(e.ref, MAX_ID)
                or not _named(e.recorded_by)
            ):
                out.append("evidence is malformed, from a model, or not a record")
                break
    return out


def complete_task(task: Task, verification: Any) -> TaskResult:
    """The only road to 'done'."""
    try:
        bad = _move(task, TaskState.DONE)
        if bad:
            return _no(task, bad)
        r = verification_issues(task, verification)
        if r:
            return _no(task, *r)
        return TaskResult(True, replace(task, state=TaskState.DONE, verification=verification), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


def fail_task(task: Task, reason: Any) -> TaskResult:
    bad = _move(task, TaskState.FAILED)
    if bad:
        return _no(task, bad)
    if not _text(reason):
        return _no(task, "a reason is required")
    return TaskResult(True, replace(task, state=TaskState.FAILED, failure_reason=str(reason)), ())


def rollback_task(task: Task, recovery: Any) -> TaskResult:
    """failed to rolled_back, only with a recovery record that has evidence."""
    try:
        bad = _move(task, TaskState.ROLLED_BACK)
        if bad:
            return _no(task, bad)
        r: list[str] = []
        if not isinstance(recovery, RecoveryRecord):
            r.append("no recovery record")
        else:
            if not _text(recovery.restored_state) or not _named(recovery.recorded_by):
                r.append("recovery record is incomplete")
            if (
                not isinstance(recovery.evidence, tuple)
                or not recovery.evidence
                or not all(
                    isinstance(e, Evidence)
                    and e.kind in EVIDENCE_KINDS
                    and _text(e.ref, MAX_ID)
                    and _named(e.recorded_by)
                    for e in recovery.evidence
                )
            ):
                r.append("recovery has no evidence")
        if r:
            return _no(task, *r)
        return TaskResult(True, replace(task, state=TaskState.ROLLED_BACK, recovery=recovery), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


# ---- dependencies (DAG) -------------------------------------------------------------------------


def validate_dag(deps: Any) -> tuple[str, ...]:
    """deps maps task id to the ids it depends on. Returns reasons; empty means a valid DAG.
    Rejects unknown ids, self-dependency, cycles and oversize input. Kahn's algorithm: linear time."""
    try:
        if not isinstance(deps, Mapping) or len(deps) > MAX_TASKS:
            return ("dependency map is malformed or too large",)
        indeg: dict[str, int] = {}
        out_edges: dict[str, list[str]] = {}
        for k, vs in deps.items():
            if not _named(k) or not isinstance(vs, (list, tuple)) or len(vs) > MAX_DEPS:
                return ("dependency map is malformed",)
            indeg.setdefault(k, 0)
        for k, vs in deps.items():
            for d in vs:
                if d == k:
                    return (f"{k[:40]} depends on itself",)
                if d not in indeg:
                    return (f"{k[:40]} depends on an unknown task",)
                indeg[k] += 1
                out_edges.setdefault(d, []).append(k)
        ready = [n for n, c in indeg.items() if c == 0]
        seen = 0
        while ready:
            n = ready.pop()
            seen += 1
            for m in out_edges.get(n, ()):
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
        return () if seen == len(indeg) else ("dependency cycle",)
    except Exception:  # noqa: BLE001
        return ("dependency map is malformed",)


def _dependency_issues(task: Task, states: Any) -> list[str]:
    if not task.depends_on:
        return []
    if not isinstance(states, Mapping):
        return ["dependency states are unknown"]
    for d in task.depends_on:
        s = states.get(d)
        if s not in (TaskState.DONE, "done"):
            return ["a dependency is not done"]
    return []


# ---- actions and bounded authority --------------------------------------------------------------

_SECRET_KEY = re.compile(
    r"card|cvv|cvc|passw|passcode|otp|pin_?code|iban|account_?n|cnic|national_?id|ssn|secret|token|expiry|routing|swift",
    re.IGNORECASE,
)
_CARD_DIGITS = re.compile(r"\d(?:[ -]?\d){12,18}")


@dataclass(frozen=True)
class ActionRequest:
    tool: str
    params: Mapping[str, Any]
    units: int = 1


@dataclass(frozen=True)
class ActionApproval:
    """A separate, explicit approval for ONE action (irreversible, destructive, outbound message)."""

    action_sha: str
    approver: str
    approval_text: str
    approved_at: datetime


def action_sha(action: ActionRequest) -> str:
    body = json.dumps(
        [action.tool, action.units, action.params],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _param_issue(obj: Any) -> str | None:
    """Bounded walk: no secrets, card numbers or oversize payloads in action parameters."""
    stack: list[tuple[Any, int]] = [(obj, 0)]
    nodes = chars = 0
    while stack:
        cur, depth = stack.pop()
        nodes += 1
        if nodes > MAX_PARAM_NODES or depth > MAX_PARAM_DEPTH:
            return "action parameters are too large or too deep"
        if isinstance(cur, Mapping):
            for k, v in cur.items():
                if not isinstance(k, str):
                    return "parameter names must be text"
                if _SECRET_KEY.search(k):
                    return "action parameters carry card, password or ID data"
                stack.append((v, depth + 1))
        elif isinstance(cur, (list, tuple)):
            stack.extend((v, depth + 1) for v in cur)
        elif isinstance(cur, str):
            chars += len(cur)
            if chars > MAX_PARAM_CHARS:
                return "action parameters are too large or too deep"
            if _CARD_DIGITS.search(cur):
                return "action parameters carry card, password or ID data"
        elif not isinstance(cur, (int, float, bool)) and cur is not None:
            return "action parameters must be plain data"
    return None


@dataclass(frozen=True)
class ExecDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...]


def _deny(code: str, *reasons: str) -> ExecDecision:
    return ExecDecision(False, code, tuple(reasons))


def check_can_execute(
    task: Any,
    scope: Any,
    now: Any,
    *,
    action: Any = None,
    action_approval: Any = None,
    dependency_states: Any = None,
    used: Any = None,
) -> ExecDecision:
    """Pre-execution gate (dry run: it never performs anything). Fail closed on anything unknown or
    malformed; never raises. With no `action` it answers "may this task proceed at all"; with an action
    it also checks tool authority, limits and the separate approval."""
    try:
        if not isinstance(task, Task) or not isinstance(task.state, TaskState):
            return _deny("malformed", "not a task")
        if task.state not in (TaskState.APPROVED, TaskState.RUNNING):
            return _deny("state", f"task is {task.state.value}, not approved or running")
        reasons = (
            _scope_issues(task, scope, now)
            + rollback_issues(task.rollback)
            + _dependency_issues(task, dependency_states)
        )
        if reasons:
            return _deny("scope_or_plan", *reasons)
        if action is None:
            return ExecDecision(True, "ok", ())
        assert isinstance(scope, ApprovedScope) and isinstance(now, datetime)
        if (
            not isinstance(action, ActionRequest)
            or not isinstance(action.tool, str)
            or not isinstance(action.params, Mapping)
        ):
            return _deny("malformed", "not an action request")
        cls = TOOL_CLASSES.get(action.tool)
        if cls is None:
            return _deny("unknown_tool", "tool is not known")
        if cls in NEVER_SCOPED:
            return _deny("forbidden_tool", "payment and credential handling is never allowed")
        if action.tool not in scope.tools:
            return _deny("outside_scope", f"tool {action.tool} is not in the approved scope")
        if isinstance(action.units, bool) or not isinstance(action.units, int) or action.units < 1:
            return _deny("malformed", "units must be a positive whole number")
        issue = _param_issue(action.params)
        if issue:
            return _deny("bad_params", issue)
        if used is not None and not isinstance(used, Mapping):
            return _deny("limits", "usage counters are malformed")
        used_map: Mapping[str, Any] = used or {}
        caps: list[tuple[str, str, int]] = [
            ("max_actions", "actions", 1),
            ("max_units", "units", action.units),
        ]
        if cls == "outbound_message":
            caps.append(("max_messages", "messages", action.units))
        if scope.limit("max_actions") is None:
            return _deny("limits", "the scope sets no max_actions limit")
        if cls == "outbound_message" and scope.limit("max_messages") is None:
            return _deny("limits", "the scope sets no max_messages limit")
        for lim_name, used_name, add in caps:
            cap = scope.limit(lim_name)
            if cap is None:
                continue
            so_far = used_map.get(used_name, 0)
            if isinstance(so_far, bool) or not isinstance(so_far, int) or so_far < 0:
                return _deny("limits", "usage counters are malformed")
            if so_far + add > cap:
                return _deny("limits", f"{lim_name} would be exceeded")
        if cls in NEEDS_OWN_APPROVAL:
            ap_issue = _action_approval_issue(action, action_approval, task, now)
            if ap_issue:
                return _deny("needs_approval", ap_issue)
        return ExecDecision(True, "ok", ())
    except Exception:  # noqa: BLE001 - fail closed, never raise
        return _deny("malformed", "unreadable input")


def _action_approval_issue(action: ActionRequest, ap: Any, task: Task, now: datetime) -> str | None:
    if not isinstance(ap, ActionApproval):
        return "this kind of action needs its own explicit approval"
    if classify_approval(ap.approval_text) is not ApprovalCue.EXPLICIT_YES:
        return "the action approval is not an explicit yes"
    if ap.action_sha != action_sha(action):
        return "the action approval refers to a different action"
    if not _named(ap.approver) or ap.approver.strip().casefold() == task.owner.strip().casefold():
        return "the action approver must be a named person other than the task owner"
    if not isinstance(ap.approved_at, datetime) or ap.approved_at.tzinfo is None:
        return "the action approval has no valid time"
    if not (timedelta(0) <= now - ap.approved_at <= ACTION_APPROVAL_TTL):
        return "the action approval is stale or from the future"
    return None


def record_decision(
    log: audit.AuditLog, task: Task, decision: ExecDecision, at: datetime, actor: str
) -> audit.AuditEntry | None:
    """Every gate answer is written to the trail: a refusal as 'refusal', a yes as 'decision'."""
    kind = "decision" if decision.allowed else "refusal"
    detail = (
        f"{decision.code}: {'; '.join(decision.reasons)}" if decision.reasons else decision.code
    )
    return log.append(
        at=at, kind=kind, actor=actor, task_id=getattr(task, "id", "?"), detail=detail
    )
