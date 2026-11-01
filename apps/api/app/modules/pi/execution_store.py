# ruff: noqa: E501
"""Level 3 persistence: load and save a run as one sealed snapshot in `pi_execution_runs`.

Every load re-verifies the scope seal, each task seal, the audit hash chain and the anchored head; a
stored run that was edited by hand raises `TamperedRun` and is treated as not existing for outcomes.
Also applies the one execution record that touches an existing table: a problem's status (and its
reversal on rollback). Other records (staff task, draft document, follow-up, note) live in the run.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import execution_flow as ef
from app.modules.pi.execution_models import PiExecutionRun
from app.modules.pi.problem_models import PiProblem
from app.shared.scope import WorkspaceScope


def _status_of(run: ef.ExecutionRun) -> str:
    o = run.outcome()["implementation_status"]
    if o == "implemented":
        return "implemented"
    if run.outcome()["failed"] and not run.outcome()["in_progress"]:
        return "failed"
    return "in_progress" if o == "approved" else ("approved" if run.scope else "proposed")


def _load_row(row: PiExecutionRun) -> ef.ExecutionRun:
    run = ef.from_json(row.snapshot)
    if row.head_hash and run.log.head != row.head_hash:
        raise ef.TamperedRun("audit head differs from its anchor")
    return run


async def get(
    session: AsyncSession, scope: WorkspaceScope, run_ref: str
) -> tuple[PiExecutionRun, ef.ExecutionRun] | None:
    row = await session.scalar(
        select(PiExecutionRun)
        .where(
            PiExecutionRun.tenant_id == scope.tenant_id,
            PiExecutionRun.environment_id == scope.environment_id,
            PiExecutionRun.run_ref == run_ref,
        )
        .with_for_update()
    )
    return None if row is None else (row, _load_row(row))


async def for_customer(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID
) -> list[tuple[PiExecutionRun, ef.ExecutionRun]]:
    rows = await session.scalars(
        select(PiExecutionRun).where(
            PiExecutionRun.tenant_id == scope.tenant_id,
            PiExecutionRun.environment_id == scope.environment_id,
            PiExecutionRun.customer_id == customer_id,
        )
    )
    out: list[tuple[PiExecutionRun, ef.ExecutionRun]] = []
    for row in rows:
        try:
            out.append((row, _load_row(row)))
        except ef.TamperedRun:
            continue  # a tampered run never counts toward an outcome
    return out


async def save(
    session: AsyncSession,
    scope: WorkspaceScope,
    run: ef.ExecutionRun,
    row: PiExecutionRun | None = None,
    *,
    customer_id: UUID | None = None,
    conversation_id: UUID | None = None,
) -> PiExecutionRun:
    if row is None:
        row = PiExecutionRun(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            run_ref=run.run_id,
            customer_id=customer_id,
            conversation_id=conversation_id,
        )
        session.add(row)
    else:
        row.version = (row.version or 1) + 1
    row.snapshot = ef.to_json(run)
    row.head_hash = run.log.head
    row.status = _status_of(run)
    await session.flush()
    return row


async def apply_problem_status(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID | None,
    effect: dict[str, Any],
    undo: bool,
) -> bool:
    """Set (or restore) a problem's status for an `update_problem_status` record. False when not found."""
    rec = effect.get("record") or {}
    try:
        pid = UUID(str(rec["problem_ref"]))
    except (KeyError, ValueError):
        return False
    problem = await session.scalar(
        select(PiProblem).where(
            PiProblem.id == pid,
            PiProblem.tenant_id == scope.tenant_id,
            PiProblem.environment_id == scope.environment_id,
            *([PiProblem.customer_id == customer_id] if customer_id else []),
        )
    )
    if problem is None:
        return False
    problem.status = str(rec["prior_status"] if undo else rec["status"])
    return True
