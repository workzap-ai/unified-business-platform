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
- Seals are keyed HMACs: PRODUCTION MUST set PI_EXECUTION_SEAL_KEY (see execution_scope). Callers MUST record
  the id of every per-action approval as consumed after the action and pass `consumed_approvals` and `used`
  to the gate; the gate itself keeps no state, so without them there is no replay or limit protection.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.modules.pi import execution_audit as audit
from app.modules.pi.execution_scope import (
    NEEDS_OWN_APPROVAL,
    NEVER_SCOPED,
    TOOL_CLASSES,
    ApprovalCue,
    ApprovedScope,
    classify_approval,
    ident,
    name_parts,
    named_person,
    seal_mac,
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
    return named_person(v)


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
    approved_by: str = ""
    seal: str = ""  # keyed HMAC set by the task functions only; a hand-built Task fails the gate


def _task_mac(t: Task) -> str:
    return seal_mac(
        [
            "task",
            t.id,
            t.title,
            t.owner,
            t.creator,
            t.scope_sha,
            list(t.depends_on),
            str(getattr(t.state, "value", t.state)),
            repr(t.rollback),
            repr(t.verification),
            repr(t.recovery),
            t.failure_reason,
            t.approved_by,
        ]
    )


def _sealed(t: Task) -> Task:
    return replace(t, seal=_task_mac(t))


def _next(t: Task, **changes: Any) -> Task:
    return _sealed(replace(t, **changes))


def task_is_genuine(t: Any) -> bool:
    """True only for a Task made by new_task or moved by the transition functions, with its fields untouched."""
    try:
        return (
            isinstance(t, Task)
            and isinstance(t.state, TaskState)
            and hmac.compare_digest(t.seal, _task_mac(t))
        )
    except Exception:  # noqa: BLE001
        return False


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
            _sealed(
                Task(
                    str(id),
                    str(title),
                    str(owner),
                    str(creator),
                    str(scope_sha),
                    deps,
                    TaskState.PROPOSED,
                    rollback,
                )
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
    if not task_is_genuine(task):
        return "not a genuine task record (not issued by the task functions, or altered)"
    if to not in LEGAL_MOVES.get(task.state, frozenset()):
        return f"illegal move {getattr(task.state, 'value', '?')} to {to.value}"
    return None


def _scope_issues(task: Task, scope: Any, now: Any) -> list[str]:
    if not isinstance(now, datetime) or now.tzinfo is None:
        return ["now must be a timezone-aware datetime"]
    if not isinstance(scope, ApprovedScope):
        return ["no approved scope"]
    bad = scope.issues()
    if bad:
        return bad
    out: list[str] = []
    if scope.scope_sha != task.scope_sha:
        out.append("scope changed since the task was written, a new approval is needed")
    if ident(scope.task_owner) != ident(task.owner) or ident(scope.task_creator) != ident(
        task.creator
    ):
        out.append("scope was approved for a different owner or creator")
    if ident(scope.approver) in {ident(task.owner), ident(task.creator)}:
        out.append("approver must differ from the task owner and creator")
    if not scope.is_live(now):
        out.append("scope has expired or is not yet valid")
    return out


def approve_task(task: Task, scope: Any, now: Any) -> TaskResult:
    try:
        bad = _move(task, TaskState.APPROVED)
        if bad:
            return _no(task, bad)
        r = _scope_issues(task, scope, now)
        r += rollback_issues(task.rollback)
        if r:
            return _no(task, *r)
        return TaskResult(
            True, _next(task, state=TaskState.APPROVED, approved_by=scope.approver), ()
        )
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
        return TaskResult(True, _next(task, state=TaskState.RUNNING), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


def mark_performed(task: Task, performed_note: Any) -> TaskResult:
    """running to verifying: the person who did the work says what was done. This is not 'done'."""
    bad = _move(task, TaskState.VERIFYING)
    if bad:
        return _no(task, bad)
    if not _text(performed_note):
        return _no(task, "a note of what was performed is required")
    return TaskResult(True, _next(task, state=TaskState.VERIFYING), ())


def verification_issues(task: Task, v: Any) -> list[str]:
    if not isinstance(v, Verification):
        return ["no verification record"]
    out: list[str] = []
    if not _named(v.acceptance_id) or not _text(v.acceptance_statement):
        out.append("acceptance check is missing")
    if v.passed is not True:
        out.append("the acceptance check did not pass")
    if not _named(v.verifier) or ident(v.verifier) == ident(task.owner):
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
        return TaskResult(True, _next(task, state=TaskState.DONE, verification=verification), ())
    except Exception:  # noqa: BLE001
        return _no(task, "malformed input")


def fail_task(task: Task, reason: Any) -> TaskResult:
    bad = _move(task, TaskState.FAILED)
    if bad:
        return _no(task, bad)
    if not _text(reason):
        return _no(task, "a reason is required")
    return TaskResult(True, _next(task, state=TaskState.FAILED, failure_reason=str(reason)), ())


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
        return TaskResult(True, _next(task, state=TaskState.ROLLED_BACK, recovery=recovery), ())
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
    approval_id: str = (
        ""  # unique per approval; the caller records it as consumed (see check_can_execute)
    )


def action_sha(action: ActionRequest) -> str:
    body = json.dumps(
        [action.tool, action.units, action.params],
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_shaped(d: str) -> bool:
    """13 to 19 digits that look like a payment card: a known network prefix with its length, or a valid Luhn sum."""
    n = len(d)
    if not 13 <= n <= 19 or not d.isascii() or not d.isdigit():
        return False
    p2, p4 = int(d[:2]), int(d[:4])
    if d[0] == "4" and n in (13, 16, 19):
        return True
    if (51 <= p2 <= 55 or 2221 <= p4 <= 2720) and n == 16:
        return True
    if p2 in (34, 37) and n == 15:
        return True
    if (
        d.startswith("6011")
        or p2 == 65
        or 644 <= int(d[:3]) <= 649
        or p2 == 62
        or 3528 <= p4 <= 3589
    ) and n >= 16:
        return True
    return _luhn(d)


def _split_card(chunks: list[str]) -> bool:
    """A card number spread over adjacent numeric values: windows of up to 6 neighbouring chunks of 4 or
    more digits whose joined digits are 13 to 19 long and card-shaped. Unrelated small numbers do not count."""
    for i in range(len(chunks)):
        joined = ""
        for j in range(i, min(i + 6, len(chunks))):
            if len(chunks[j]) < 4:
                break
            joined += chunks[j]
            if len(joined) > 19:
                break
            if 13 <= len(joined) and _card_shaped(joined):
                return True
    return False


def _param_issue(obj: Any) -> str | None:
    """Bounded walk: no secrets, card numbers or oversize payloads in action parameters. Leaves are
    collected in document order. String leaves are screened one by one for card digit runs (any separators)
    and, joined, for secret disclosures that straddle values; mostly-numeric leaves (text or numbers) are
    checked for a card number split across neighbours. A sibling of a value that is itself a secret word
    ({'label': 'password', 'value': 'x'}) is treated as secret."""
    stack: list[tuple[Any, int]] = [(obj, 0)]
    nodes = chars = 0
    strings: list[str] = []
    numeric: list[str] = []
    while stack:
        cur, depth = stack.pop()
        nodes += 1
        if nodes > MAX_PARAM_NODES or depth > MAX_PARAM_DEPTH:
            return "action parameters are too large or too deep"
        if isinstance(cur, Mapping):
            pairs = list(cur.items())
            for k, v in pairs:
                if not isinstance(k, str):
                    return "parameter names must be text"
                if audit.secret_key_name(k, v):
                    return "action parameters carry card, password or ID data"
            scalars = [
                v
                for _k, v in pairs
                if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip()
            ]
            for _k, v in pairs:
                if (
                    isinstance(v, str)
                    and len(v) <= 40
                    and audit.secret_key_name(v)
                    and len(scalars) > 1
                ):
                    return "action parameters carry card, password or ID data"
            for k, v in reversed(pairs):
                stack.append((v, depth + 1))
                stack.append((k, depth + 1))
        elif isinstance(cur, (list, tuple)):
            stack.extend((v, depth + 1) for v in reversed(cur))
        elif isinstance(cur, str):
            chars += len(cur)
            if chars > MAX_PARAM_CHARS:
                return "action parameters are too large or too deep"
            if audit.has_card_like(cur, 13) and not audit.is_uuid(cur):
                return "action parameters carry card, password or ID data"
            strings.append(cur)
            digits = "".join(c for c in cur if c.isdigit())
            if digits and len(digits) * 5 >= len(cur) * 4:
                numeric.append(digits)
        elif isinstance(cur, (int, float)) and not isinstance(cur, bool):
            numeric.append("".join(c for c in str(abs(cur)) if c.isdigit()))
        elif not isinstance(cur, bool) and cur is not None:
            return "action parameters must be plain data"
    if audit.looks_secret(" ".join(strings)):
        return "action parameters carry card, password or ID data"
    if _split_card(numeric):
        return "action parameters carry card, password or ID data"
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
    consumed_approvals: Any = None,
) -> ExecDecision:
    """Pre-execution gate (dry run: it never performs anything). Fail closed on anything unknown or
    malformed; never raises. With no `action` it answers "may this task proceed at all"; with an action
    it also checks tool authority, limits and the separate approval.

    The gate is pure: it consumes nothing. Callers own the state and must pass it in: `used` (counters of
    actions, units and messages already done) and `consumed_approvals` (ids of per-action approvals
    already spent). After an action is really performed the caller records its approval id as consumed;
    a replayed approval id is then refused. A caller that passes nothing gets no replay protection."""
    try:
        if not task_is_genuine(task):
            return _deny(
                "malformed",
                "not a genuine task record (not issued by the task functions, or altered)",
            )
        if task.state not in (TaskState.APPROVED, TaskState.RUNNING):
            return _deny("state", f"task is {task.state.value}, not approved or running")
        if isinstance(scope, ApprovedScope) and ident(task.approved_by) != ident(scope.approver):
            return _deny("scope_or_plan", "the task was approved under a different scope approval")
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
            ap_issue = _action_approval_issue(
                action, action_approval, task, now, consumed_approvals
            )
            if ap_issue:
                return _deny("needs_approval", ap_issue)
        return ExecDecision(True, "ok", ())
    except Exception:  # noqa: BLE001 - fail closed, never raise
        return _deny("malformed", "unreadable input")


def _action_approval_issue(
    action: ActionRequest, ap: Any, task: Task, now: datetime, consumed: Any
) -> str | None:
    if not isinstance(ap, ActionApproval):
        return "this kind of action needs its own explicit approval"
    if (
        not isinstance(ap.approval_id, str)
        or not ap.approval_id.strip()
        or len(ap.approval_id) > MAX_ID
    ):
        return "the action approval has no id"
    if consumed is not None:
        try:
            if ap.approval_id in consumed:
                return "this action approval was already used"
        except TypeError:
            return "consumed approvals are malformed"
    if classify_approval(ap.approval_text, name_parts(ap.approver)) is not ApprovalCue.EXPLICIT_YES:
        return "the action approval is not an explicit yes"
    if ap.action_sha != action_sha(action):
        return "the action approval refers to a different action"
    if not _named(ap.approver) or ident(ap.approver) in {ident(task.owner), ident(task.creator)}:
        return "the action approver must be a named person other than the task owner and creator"
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
