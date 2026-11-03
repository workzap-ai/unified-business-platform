# ruff: noqa: E501
"""Controlled execution (Level 3): the whole flow, in memory and testable without a database.

Owner approval of the exact scope -> tasks with dependencies -> approved allow-listed internal tool
actions only -> an execution record (effect) per action -> an acceptance check per task -> a rollback
record -> a verified outcome only when the acceptance checks carry evidence -> a hash-chained audit log.

'Done' is never a model statement: a task is done only through `execution_task.complete_task`, which
needs a named human verifier (not the task owner), a passed acceptance check and evidence refs that
resolve to real execution records of that task. The run is persisted as one sealed snapshot
(`execution_store`); every seal and the audit chain are re-verified on load.

Behind `response_rules.brain.level3_exec` (default off) and brain mode. Owner approval is part of the
product: no flag skips it. Without PI_EXECUTION_SEAL_KEY in production the feature is inert.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.modules.pi import execution_audit as audit
from app.modules.pi import execution_screen as screen
from app.modules.pi import execution_task as et
from app.modules.pi import execution_tools as tools_mod
from app.modules.pi.execution_scope import (
    ApprovalCue,
    ApprovedScope,
    classify_approval,
    create_scope,
    name_parts,
    scope_sha,
    seal_key_configured,
)

MAX_TASKS = 50
MAX_EFFECTS = 500
DEFAULT_LIMITS = {"max_actions": 20, "max_units": 20}


def availability(rules: Mapping[str, Any] | None, app_env: str = "development") -> tuple[bool, str]:
    """(on, reason when off). Exactly true only; brain mode only; inert in production without a key."""
    r = rules or {}
    if r.get("pi_mode") != "brain":
        return False, "brain mode is off"
    if (r.get("brain") or {}).get("level3_exec") is not True:
        return False, "level3_exec is off"
    if app_env == "production" and not seal_key_configured():
        return False, "PI_EXECUTION_SEAL_KEY is not set, controlled execution is inert"
    return True, ""


@dataclass(frozen=True)
class Step:
    ok: bool
    reasons: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)


def _no(*reasons: str) -> Step:
    return Step(False, tuple(reasons))


@dataclass
class Pending:
    scope_text: str
    tools: tuple[str, ...]
    limits: dict[str, int]
    expires_at: datetime
    owner: str
    creator: str
    sha: str
    shown: bool = False  # staff marked it as sent to the owner; chat approval needs this


@dataclass
class ExecutionRun:
    run_id: str
    pending: Pending | None = None
    scope: ApprovedScope | None = None
    tasks: dict[str, et.Task] = field(default_factory=dict)
    acceptance: dict[str, tuple[str, str]] = field(default_factory=dict)
    effects: list[dict[str, Any]] = field(default_factory=list)
    consumed: set[str] = field(default_factory=set)
    used: dict[str, int] = field(default_factory=lambda: {"actions": 0, "units": 0, "messages": 0})
    log: audit.AuditLog = field(default_factory=audit.AuditLog)

    # ---- helpers ----
    def _audit(self, now: datetime, kind: str, actor: str, task_id: str, detail: str) -> None:
        self.log.append(at=now, kind=kind, actor=actor, task_id=task_id or "-", detail=detail)

    def _states(self) -> dict[str, str]:
        return {k: t.state.value for k, t in self.tasks.items()}

    # ---- 1. the exact scope, shown to the owner ----
    def propose(
        self,
        *,
        scope_text: str,
        tools: list[str],
        limits: Mapping[str, int] | None,
        expires_at: datetime,
        owner: str,
        creator: str,
        now: datetime,
    ) -> Step:
        if self.scope is not None:
            return _no("a scope is already approved; a changed scope is a new run")
        bad = tools_mod_issues(tools) or screen.text_issue(scope_text)
        if bad:
            return _no(f"scope refused: {bad}")
        lim = dict(DEFAULT_LIMITS if limits is None else limits)
        sha = scope_sha(scope_text, frozenset(tools), lim)
        self.pending = Pending(
            scope_text, tuple(sorted(set(tools))), lim, expires_at, owner, creator, sha
        )
        self._audit(
            now,
            "scope",
            creator,
            "-",
            f"proposed scope {sha[:12]} tools {','.join(self.pending.tools)}",
        )
        return Step(True, (), {"scope_sha": sha, "text": render_proposal(self.pending)})

    def mark_shown(self, now: datetime, actor: str) -> Step:
        if self.pending is None or self.scope is not None:
            return _no("there is no proposal waiting")
        self.pending.shown = True
        self._audit(now, "scope", actor, "-", f"scope {self.pending.sha[:12]} shown to the owner")
        return Step(True)

    # ---- 2. owner approval: closed grammar, exact scope, independent person ----
    def approve_scope(
        self, *, approver: str, approval_text: str, source: str, now: datetime
    ) -> Step:
        p = self.pending
        if p is None:
            return _no("there is no proposed scope to approve")
        if self.scope is not None:
            return _no("the scope is already approved")
        res = create_scope(
            scope_text=p.scope_text,
            tools=list(p.tools),
            limits=p.limits,
            expires_at=p.expires_at,
            approver=approver,
            approval_source=source,
            approval_text=approval_text,
            referenced_sha=p.sha,
            task_owner=p.owner,
            task_creator=p.creator,
            now=now,
        )
        if not res.ok or res.scope is None:
            self._audit(
                now,
                "refusal",
                str(approver),
                "-",
                "scope approval refused: " + "; ".join(res.reasons),
            )
            return _no(*res.reasons)
        self.scope = res.scope
        self._audit(now, "approval", res.scope.approver, "-", f"scope {p.sha[:12]} approved")
        return Step(True)

    # ---- 3. tasks and dependencies ----
    def add_task(
        self,
        *,
        id: str,
        title: str,
        owner: str,
        depends_on: list[str],
        rollback_steps: list[str],
        rollback_owner: str,
        rollback_check: str,
        acceptance_id: str,
        acceptance_statement: str,
        now: datetime,
    ) -> Step:
        if self.scope is None:
            return _no("no approved scope")
        if len(self.tasks) >= MAX_TASKS:
            return _no("too many tasks")
        if id in self.tasks:
            return _no("task id already exists")
        for t in (title, acceptance_statement, rollback_check, *rollback_steps):
            bad = screen.text_issue(t)
            if bad:
                return _no(f"task text refused: {bad}")
        if not acceptance_id or not acceptance_statement.strip():
            return _no("every task needs an acceptance check")
        deps = {k: list(t.depends_on) for k, t in self.tasks.items()}
        deps[id] = list(depends_on)
        dag = et.validate_dag(deps)
        if dag:
            return _no(*dag)
        plan = et.RollbackPlan(tuple(rollback_steps), True, rollback_owner, rollback_check)
        res = et.new_task(
            id=id,
            title=title,
            owner=owner,
            creator=self.scope.task_creator,
            scope_sha=self.scope.scope_sha,
            depends_on=depends_on,
            rollback=plan,
        )
        if not res.ok or res.task is None:
            return _no(*res.reasons)
        self.tasks[id] = res.task
        self.acceptance[id] = (acceptance_id, acceptance_statement)
        self._audit(now, "transition", res.task.creator, id, "task proposed")
        return Step(True)

    def _apply(self, id: str, res: et.TaskResult, now: datetime, actor: str, detail: str) -> Step:
        if not res.ok or res.task is None:
            self._audit(now, "refusal", actor, id, "; ".join(res.reasons))
            return _no(*res.reasons)
        self.tasks[id] = res.task
        self._audit(now, "transition", actor, id, detail)
        return Step(True)

    def approve_task(self, id: str, now: datetime) -> Step:
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        res = et.approve_task(t, self.scope, now)
        return self._apply(id, res, now, getattr(self.scope, "approver", "-"), "task approved")

    def start(self, id: str, now: datetime, actor: str) -> Step:
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        res = et.start_task(t, self.scope, now, self._states())
        return self._apply(id, res, now, actor, "task started")

    # ---- 4/5. one approved, allow-listed internal action and its execution record ----
    def execute_action(
        self,
        id: str,
        tool: str,
        params: Mapping[str, Any],
        now: datetime,
        actor: str,
        units: int = 1,
    ) -> Step:
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        why = tools_mod.validate(tool, params)
        if why:
            self._audit(now, "refusal", actor, id, f"{tool}: {why}")
            return _no(why)
        action = et.ActionRequest(tool, dict(params), units)
        dec = et.check_can_execute(
            t,
            self.scope,
            now,
            action=action,
            dependency_states=self._states(),
            used=self.used,
            consumed_approvals=self.consumed,
        )
        et.record_decision(self.log, t, dec, now, actor)
        if not dec.allowed:
            return _no(*dec.reasons)
        if t.state is not et.TaskState.RUNNING:
            return _no("the task must be started first")
        if len(self.effects) >= MAX_EFFECTS:
            return _no("too many execution records")
        out = tools_mod.run_tool(tool, params)
        if isinstance(out, str):
            self._audit(now, "refusal", actor, id, f"{tool}: {out}")
            return _no(out)
        eid = "fx_" + secrets.token_hex(8)
        self.effects.append(
            {
                "id": eid,
                "task_id": id,
                "tool": tool,
                "kind": out.kind,
                "summary": out.summary,
                "record": dict(out.record),
                "undo": dict(out.undo),
                "at": now.isoformat(),
                "actor": actor,
                "rolled_back": False,
            }
        )
        self.used["actions"] += 1
        self.used["units"] += units
        self._audit(now, "action", actor, id, f"{tool} recorded as {eid}")
        return Step(True, (), {"effect_id": eid, "summary": out.summary})

    def finish_work(self, id: str, now: datetime, actor: str) -> Step:
        """running -> verifying: work is performed, NOT done. Needs at least one execution record."""
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        if not any(e["task_id"] == id for e in self.effects):
            return _no("nothing was recorded for this task")
        res = et.mark_performed(
            t, f"{sum(1 for e in self.effects if e['task_id'] == id)} action(s) recorded"
        )
        return self._apply(id, res, now, actor, "work performed, awaiting acceptance check")

    # ---- 6. acceptance check with evidence (a named human, never the model) ----
    def verify(
        self,
        id: str,
        *,
        verifier: str,
        passed: bool,
        evidence_refs: list[str],
        now: datetime,
    ) -> Step:
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        mine = {e["id"]: e for e in self.effects if e["task_id"] == id and not e["rolled_back"]}
        refs = list(dict.fromkeys(evidence_refs))
        if not refs or any(r not in mine for r in refs):
            self._audit(
                now,
                "refusal",
                str(verifier),
                id,
                "evidence does not resolve to execution records of this task",
            )
            return _no("evidence must be execution records of this task")
        aid, stmt = self.acceptance.get(id, ("", ""))
        ev = tuple(et.Evidence(r, mine[r]["kind"], verifier) for r in refs)
        v = et.Verification(aid, stmt, ev, bool(passed), verifier)
        if not passed:
            f = et.fail_task(t, "the acceptance check did not pass")
            self._audit(now, "verification", str(verifier), id, "acceptance check failed")
            return self._apply(id, f, now, verifier, "task failed acceptance")
        res = et.complete_task(t, v)
        if res.ok:
            self._audit(
                now,
                "verification",
                verifier,
                id,
                f"acceptance {aid} passed with {len(refs)} record(s)",
            )
        return self._apply(id, res, now, verifier, "task done (verified)")

    # ---- 7. failure and rollback record ----
    def fail(self, id: str, reason: str, now: datetime, actor: str) -> Step:
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        bad = screen.text_issue(reason)
        if bad:
            return _no(f"reason refused: {bad}")
        return self._apply(id, et.fail_task(t, reason), now, actor, "task failed")

    def rollback(self, id: str, *, recorder: str, now: datetime) -> Step:
        """failed -> rolled_back. Undoes every execution record of the task and cites them as evidence."""
        t = self.tasks.get(id)
        if t is None:
            return _no("unknown task")
        if t.state is not et.TaskState.FAILED:
            return _no("only a failed task can be rolled back")
        mine = [e for e in self.effects if e["task_id"] == id]
        if not mine:
            return _no("there is nothing recorded to roll back")
        ev = tuple(et.Evidence(e["id"], e["kind"], recorder) for e in mine)
        rec = et.RecoveryRecord(
            "internal records reversed: " + ", ".join(e["id"] for e in mine), ev, recorder
        )
        res = et.rollback_task(t, rec)
        if not res.ok:
            return self._apply(id, res, now, recorder, "")
        for e in mine:
            e["rolled_back"] = True
        self._audit(now, "rollback", recorder, id, f"{len(mine)} record(s) reversed")
        return self._apply(id, res, now, recorder, "task rolled back")

    # ---- 8. the outcome: only verified tasks count ----
    def outcome(self) -> dict[str, Any]:
        verified = [
            k for k, t in self.tasks.items() if t.state is et.TaskState.DONE and verified_ok(t)
        ]
        running = [
            k
            for k, t in self.tasks.items()
            if t.state in (et.TaskState.APPROVED, et.TaskState.RUNNING, et.TaskState.VERIFYING)
        ]
        n = len(self.tasks)
        if n and len(verified) == n:
            status = "implemented"
        elif verified or running:
            status = "approved"
        else:
            status = "proposed"
        return {
            "implementation_status": status,
            "verified": verified,
            "in_progress": running,
            "failed": [
                k
                for k, t in self.tasks.items()
                if t.state in (et.TaskState.FAILED, et.TaskState.ROLLED_BACK)
            ],
            "chain_ok": audit.verify_chain(self.log.entries).ok,
        }


def verified_ok(t: et.Task) -> bool:
    """A done task whose own seal is intact and whose verification still passes every check."""
    return (
        et.task_is_genuine(t)
        and t.state is et.TaskState.DONE
        and not et.verification_issues(t, t.verification)
    )


def tools_mod_issues(tools: Any) -> str | None:
    if not isinstance(tools, (list, tuple)) or not tools:
        return "tools must be a non-empty list"
    for x in tools:
        if not tools_mod.is_allowed(x):
            return "only internal allow-listed tools may be in a scope"
    return None


def render_proposal(p: Pending) -> str:
    """What the owner is shown. The approval must name this exact scope (the short code)."""
    return (
        f"Scope {p.sha[:12]}: {p.scope_text.strip()}\n"
        f"Actions allowed (internal only): {', '.join(p.tools)}. "
        f"Limits: {', '.join(f'{k} {v}' for k, v in sorted(p.limits.items()))}. "
        f"Valid until {p.expires_at.isoformat()}.\n"
        "Nothing is sent to anyone outside and no payment is taken. Reply with an explicit yes to approve exactly this."
    )


def short_code(sha: str) -> str:
    return sha[:12]


def owner_reply_is_yes(text: str, owner_name: str = "") -> bool:
    """Used by the chat hook: only the closed grammar counts, never 'ok', 'hmm' or 'maybe'."""
    return classify_approval(text, name_parts(owner_name)) is ApprovalCue.EXPLICIT_YES


# ---- (de)serialisation: every seal and the audit chain are re-verified on load -------------------


class TamperedRun(Exception):
    pass


def _ev(e: et.Evidence) -> dict[str, str]:
    return {"ref": e.ref, "kind": e.kind, "by": e.recorded_by}


def _task_json(t: et.Task) -> dict[str, Any]:
    return {
        "id": t.id, "title": t.title, "owner": t.owner, "creator": t.creator, "scope_sha": t.scope_sha,
        "depends_on": list(t.depends_on), "state": t.state.value,
        "rollback": None if t.rollback is None else {
            "steps": list(t.rollback.steps), "reversible": t.rollback.reversible,
            "owner": t.rollback.owner, "check": t.rollback.check},
        "verification": None if t.verification is None else {
            "aid": t.verification.acceptance_id, "stmt": t.verification.acceptance_statement,
            "evidence": [_ev(e) for e in t.verification.evidence], "passed": t.verification.passed,
            "verifier": t.verification.verifier},
        "recovery": None if t.recovery is None else {
            "restored": t.recovery.restored_state, "evidence": [_ev(e) for e in t.recovery.evidence],
            "by": t.recovery.recorded_by},
        "failure_reason": t.failure_reason, "approved_by": t.approved_by, "seal": t.seal,
    }  # fmt: skip


def _task_from(d: Mapping[str, Any]) -> et.Task:
    def evs(xs: Any) -> tuple[et.Evidence, ...]:
        return tuple(et.Evidence(x["ref"], x["kind"], x["by"]) for x in xs)

    rb, vf, rc = d.get("rollback"), d.get("verification"), d.get("recovery")
    return et.Task(
        id=d["id"], title=d["title"], owner=d["owner"], creator=d["creator"], scope_sha=d["scope_sha"],
        depends_on=tuple(d["depends_on"]), state=et.TaskState(d["state"]),
        rollback=None if rb is None else et.RollbackPlan(tuple(rb["steps"]), rb["reversible"], rb["owner"], rb["check"]),
        verification=None if vf is None else et.Verification(vf["aid"], vf["stmt"], evs(vf["evidence"]), vf["passed"], vf["verifier"]),
        recovery=None if rc is None else et.RecoveryRecord(rc["restored"], evs(rc["evidence"]), rc["by"]),
        failure_reason=d["failure_reason"], approved_by=d["approved_by"], seal=d["seal"],
    )  # fmt: skip


def to_json(run: ExecutionRun) -> dict[str, Any]:
    s, p = run.scope, run.pending
    return {
        "run_id": run.run_id,
        "pending": None if p is None else {
            "scope_text": p.scope_text, "tools": list(p.tools), "limits": p.limits,
            "expires_at": p.expires_at.isoformat(), "owner": p.owner, "creator": p.creator, "sha": p.sha, "shown": p.shown},
        "scope": None if s is None else {
            "scope_text": s.scope_text, "tools": sorted(s.tools), "limits": [list(x) for x in s.limits],
            "expires_at": s.expires_at.isoformat(), "approver": s.approver,
            "approval_source": s.approval_source, "approved_at": s.approved_at.isoformat(),
            "scope_sha": s.scope_sha, "cue_sha": s.cue_sha, "task_owner": s.task_owner,
            "task_creator": s.task_creator, "seal": s.seal},
        "tasks": {k: _task_json(t) for k, t in run.tasks.items()},
        "acceptance": {k: list(v) for k, v in run.acceptance.items()},
        "effects": run.effects,
        "consumed": sorted(run.consumed),
        "used": run.used,
        "audit": [e.__dict__ for e in run.log.entries],
    }  # fmt: skip


def from_json(d: Mapping[str, Any]) -> ExecutionRun:
    """Rebuild a run. Raises TamperedRun when a seal, the hash chain or a verified outcome does not hold."""
    try:
        log = audit.AuditLog.restore(audit.AuditEntry(**e) for e in d["audit"])
        if log is None:
            raise TamperedRun("audit chain broken")
        run = ExecutionRun(str(d["run_id"]), log=log)
        if d.get("pending"):
            p = d["pending"]
            run.pending = Pending(p["scope_text"], tuple(p["tools"]), dict(p["limits"]),
                                  datetime.fromisoformat(p["expires_at"]), p["owner"], p["creator"], p["sha"], bool(p.get("shown")))  # fmt: skip
        if d.get("scope"):
            s = d["scope"]
            run.scope = ApprovedScope(
                scope_text=s["scope_text"], tools=frozenset(s["tools"]),
                limits=tuple((k, v) for k, v in s["limits"]),
                expires_at=datetime.fromisoformat(s["expires_at"]), approver=s["approver"],
                approval_source=s["approval_source"], approved_at=datetime.fromisoformat(s["approved_at"]),
                scope_sha=s["scope_sha"], cue_sha=s["cue_sha"], task_owner=s["task_owner"],
                task_creator=s["task_creator"], seal=s["seal"],
            )  # fmt: skip
            if run.scope.issues():
                raise TamperedRun("scope seal does not verify")
        for k, td in d["tasks"].items():
            t = _task_from(td)
            if not et.task_is_genuine(t):
                raise TamperedRun("task seal does not verify")
            run.tasks[k] = t
        run.acceptance = {k: (v[0], v[1]) for k, v in d["acceptance"].items()}
        run.effects = [dict(e) for e in d["effects"]]
        run.consumed = set(d["consumed"])
        run.used = {k: int(v) for k, v in d["used"].items()}
        return run
    except TamperedRun:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TamperedRun("stored run is unreadable") from exc


def report_text(run: ExecutionRun) -> str:
    """The only wording about progress. 'Done' appears only for tasks with verified evidence."""
    o = run.outcome()
    if o["implementation_status"] == "implemented":
        return f"All {len(o['verified'])} task(s) are done and verified against their acceptance checks."
    parts = []
    if o["verified"]:
        parts.append(f"{len(o['verified'])} task(s) verified")
    if o["in_progress"]:
        parts.append(f"{len(o['in_progress'])} in progress, not yet verified")
    if o["failed"]:
        parts.append(f"{len(o['failed'])} failed or rolled back")
    return ("Progress: " + "; ".join(parts) + ".") if parts else "Nothing has been done yet."


def new_run() -> ExecutionRun:
    return ExecutionRun("run_" + secrets.token_hex(8))


__all__ = [
    "ExecutionRun", "Step", "TamperedRun", "availability", "from_json", "new_run",
    "owner_reply_is_yes", "report_text", "short_code", "to_json", "verified_ok",
]  # fmt: skip
