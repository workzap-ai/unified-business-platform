# ruff: noqa: E501
"""Level 3 controlled execution: the staff and owner console (Owner OS).

Every route needs `pi.handoffs.manage`, the PI product, brain mode and `response_rules.brain.level3_exec`
exactly true (otherwise 404, no behaviour change). The approver is the signed-in person, never a model;
the scope approval still has to pass the closed grammar and name the exact scope. The seal key must be
configured in production. All logic lives in `execution_flow`; this file only loads, calls and saves.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import get_settings
from app.modules.access.dependencies import Scope, Session
from app.modules.pi import execution_flow as ef
from app.modules.pi import execution_store as store
from app.modules.pi.configuration import settings_row
from app.modules.pi.execution_models import PiExecutionRun
from app.modules.pi.service import require_pi
from app.shared.errors import BusinessRuleViolation

router = APIRouter(prefix="/pi/execution", tags=["pi-execution"])
PERMISSION = "pi.handoffs.manage"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposeIn(_In):
    scope_text: str = Field(max_length=5000)
    tools: list[str] = Field(max_length=10)
    owner: str = Field(max_length=120)  # the named person who will do the work
    limits: dict[str, int] | None = None
    expires_in_days: int = Field(7, ge=1, le=30)
    customer_id: UUID | None = None
    conversation_id: UUID | None = None


class ApproveIn(_In):
    approval_text: str = Field(max_length=200)


class TaskIn(_In):
    id: str = Field(max_length=120)
    title: str = Field(max_length=500)
    owner: str = Field(max_length=120)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    rollback_steps: list[str] = Field(max_length=20)
    rollback_owner: str = Field(max_length=120)
    rollback_check: str = Field(max_length=500)
    acceptance_id: str = Field(max_length=120)
    acceptance_statement: str = Field(max_length=500)


class ActionIn(_In):
    tool: str = Field(max_length=60)
    params: dict[str, Any] = Field(default_factory=dict)
    units: int = Field(1, ge=1, le=1000)


class VerifyIn(_In):
    passed: bool
    evidence_refs: list[str] = Field(max_length=50)


class ReasonIn(_In):
    reason: str = Field(max_length=500)


async def _gate(session: Session, scope: Scope) -> None:
    await require_pi(session, scope, PERMISSION)
    rules = (await settings_row(session, scope)).response_rules
    on, _why = ef.availability(rules, get_settings().app_env)
    if not on:
        raise BusinessRuleViolation("NOT_FOUND", "Not found", status=404)


def _now() -> datetime:
    return datetime.now(UTC)


def _fail(step: ef.Step) -> None:
    if not step.ok:
        raise BusinessRuleViolation("EXECUTION_REFUSED", "; ".join(step.reasons)[:500], status=409)


async def _run(session: Session, scope: Scope, ref: str) -> tuple[PiExecutionRun, ef.ExecutionRun]:
    try:
        found = await store.get(session, scope, ref)
    except ef.TamperedRun as exc:
        raise BusinessRuleViolation("RUN_TAMPERED", str(exc), status=409) from exc
    if found is None:
        raise BusinessRuleViolation("NOT_FOUND", "Not found", status=404)
    return found


def _view(run: ef.ExecutionRun) -> dict[str, Any]:
    return {
        "run_ref": run.run_id,
        "pending_scope": run.pending.sha[:12] if run.pending and not run.scope else None,
        "scope_approved": run.scope is not None,
        "tasks": {k: t.state.value for k, t in run.tasks.items()},
        "effects": [
            {k: e[k] for k in ("id", "task_id", "tool", "summary", "rolled_back")}
            for e in run.effects
        ],
        "outcome": run.outcome(),
        "report": ef.report_text(run),
        "audit_head": run.log.head,
    }


@router.post("/runs", status_code=201)
async def propose(body: ProposeIn, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope)
    run, now = ef.new_run(), _now()
    step = run.propose(
        scope_text=body.scope_text,
        tools=body.tools,
        limits=body.limits,
        expires_at=now + timedelta(days=body.expires_in_days),
        owner=body.owner,
        creator=scope.actor_label,
        now=now,
    )
    _fail(step)
    await store.save(
        session, scope, run, customer_id=body.customer_id, conversation_id=body.conversation_id
    )
    return {"owner_message": step.data["text"], **_view(run)}


@router.get("/runs/{ref}")
async def read(ref: str, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope)
    _row, run = await _run(session, scope, ref)
    return _view(run)


@router.post("/runs/{ref}/shown")
async def shown(ref: str, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope)
    row, run = await _run(session, scope, ref)
    _fail(run.mark_shown(_now(), scope.actor_label))
    await store.save(session, scope, run, row)
    return _view(run)


@router.post("/runs/{ref}/approve")
async def approve(ref: str, body: ApproveIn, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope)
    row, run = await _run(session, scope, ref)
    step = run.approve_scope(
        approver=scope.actor_label,
        approval_text=body.approval_text,
        source="staff_console",
        now=_now(),
    )
    await store.save(session, scope, run, row)  # a refusal is audited too
    _fail(step)
    return _view(run)


@router.post("/runs/{ref}/tasks", status_code=201)
async def add_task(ref: str, body: TaskIn, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope)
    row, run = await _run(session, scope, ref)
    _fail(run.add_task(**body.model_dump(), now=_now()))
    await store.save(session, scope, run, row)
    return _view(run)


async def _task_call(
    ref: str, scope: Scope, session: Session, fn: Callable[[ef.ExecutionRun, datetime], ef.Step]
) -> tuple[PiExecutionRun, ef.ExecutionRun, ef.Step]:
    await _gate(session, scope)
    row, run = await _run(session, scope, ref)
    step = fn(run, _now())
    await store.save(session, scope, run, row)  # refusals are in the audit log
    _fail(step)
    return row, run, step


@router.post("/runs/{ref}/tasks/{task}/approve")
async def approve_task(ref: str, task: str, scope: Scope, session: Session) -> dict[str, Any]:
    _r, run, _s = await _task_call(ref, scope, session, lambda r, n: r.approve_task(task, n))
    return _view(run)


@router.post("/runs/{ref}/tasks/{task}/start")
async def start(ref: str, task: str, scope: Scope, session: Session) -> dict[str, Any]:
    _r, run, _s = await _task_call(
        ref, scope, session, lambda r, n: r.start(task, n, scope.actor_label)
    )
    return _view(run)


@router.post("/runs/{ref}/tasks/{task}/actions")
async def action(
    ref: str, task: str, body: ActionIn, scope: Scope, session: Session
) -> dict[str, Any]:
    row, run, step = await _task_call(
        ref,
        scope,
        session,
        lambda r, n: r.execute_action(
            task, body.tool, body.params, n, scope.actor_label, body.units
        ),
    )
    if body.tool == "update_problem_status":
        effect = next(e for e in run.effects if e["id"] == step.data["effect_id"])
        if not await store.apply_problem_status(session, scope, row.customer_id, effect, False):
            effect["rolled_back"] = True
            run.fail(task, "the problem was not found", _now(), scope.actor_label)
            await store.save(session, scope, run, row)
            raise BusinessRuleViolation(
                "EXECUTION_REFUSED", "the problem was not found", status=409
            )
    return {**_view(run), "effect_id": step.data["effect_id"]}


@router.post("/runs/{ref}/tasks/{task}/finish")
async def finish(ref: str, task: str, scope: Scope, session: Session) -> dict[str, Any]:
    _r, run, _s = await _task_call(
        ref, scope, session, lambda r, n: r.finish_work(task, n, scope.actor_label)
    )
    return _view(run)


@router.post("/runs/{ref}/tasks/{task}/verify")
async def verify(
    ref: str, task: str, body: VerifyIn, scope: Scope, session: Session
) -> dict[str, Any]:
    _r, run, _s = await _task_call(
        ref,
        scope,
        session,
        lambda r, n: r.verify(
            task,
            verifier=scope.actor_label,
            passed=body.passed,
            evidence_refs=body.evidence_refs,
            now=n,
        ),
    )
    return _view(run)


@router.post("/runs/{ref}/tasks/{task}/fail")
async def fail(
    ref: str, task: str, body: ReasonIn, scope: Scope, session: Session
) -> dict[str, Any]:
    _r, run, _s = await _task_call(
        ref, scope, session, lambda r, n: r.fail(task, body.reason, n, scope.actor_label)
    )
    return _view(run)


@router.post("/runs/{ref}/tasks/{task}/rollback")
async def rollback(ref: str, task: str, scope: Scope, session: Session) -> dict[str, Any]:
    row, run, _s = await _task_call(
        ref, scope, session, lambda r, n: r.rollback(task, recorder=scope.actor_label, now=n)
    )
    for e in run.effects:
        if e["task_id"] == task and e["tool"] == "update_problem_status":
            await store.apply_problem_status(session, scope, row.customer_id, e, True)
    return _view(run)
