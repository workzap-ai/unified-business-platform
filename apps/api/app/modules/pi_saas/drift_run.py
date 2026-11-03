"""The daily drift run's persistence and cron job (platform spec Part A.7 "keep auditing", 11.10).

The checks themselves are `app/modules/pi/drift_check.py` (read-only, no model call). This file
decides who runs them, stores each run in the audit log (`pi.health.drift_check`, no migration;
same surface as the self-test rows) and reads the latest back for Health.

Off unless a workspace turns it on: `response_rules.brain.drift_check = true` (default off).
At most one run a day per workspace. The previous run's stored baseline is what "drift" is
measured against, so the first run only records a baseline and reports gaps.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record
from app.modules.pi import drift_check
from app.modules.pi.learning_models import PiReplyAudit
from app.modules.pi.models import WhatsAppConnection
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

ACTION = "pi.health.drift_check"
DAILY_GAP = timedelta(hours=20)
STAMPS = 50  # the last replies whose stamp is checked (A.3 step 9)


def enabled(response_rules: dict[str, Any] | None) -> bool:
    return ((response_rules or {}).get("brain") or {}).get("drift_check") is True


def _where(scope: WorkspaceScope) -> Any:
    return (
        (AuditEvent.tenant_id == scope.tenant_id)
        & (AuditEvent.environment_id == scope.environment_id)
        & (AuditEvent.action == ACTION)
    )


async def _last_event(session: AsyncSession, scope: WorkspaceScope) -> AuditEvent | None:
    found: AuditEvent | None = await session.scalar(
        select(AuditEvent).where(_where(scope)).order_by(AuditEvent.created_at.desc()).limit(1)
    )
    return found


async def due(session: AsyncSession, scope: WorkspaceScope) -> bool:
    last = await _last_event(session, scope)
    return last is None or last.created_at < datetime.now(UTC) - DAILY_GAP


async def recent_stamps(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(PiReplyAudit.prompt_version, PiReplyAudit.pack_versions)
        .where(
            PiReplyAudit.tenant_id == scope.tenant_id,
            PiReplyAudit.environment_id == scope.environment_id,
        )
        .order_by(PiReplyAudit.created_at.desc())
        .limit(STAMPS)
    )
    return [{"prompt_version": r[0], "pack_versions": r[1]} for r in rows.all()]


async def run_drift_check(
    session: AsyncSession, scope: WorkspaceScope, report: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run the checks for one workspace, store the result, return it. Pass `report` to share one
    file scan between workspaces."""
    if report is None:
        report = await asyncio.to_thread(drift_check.build_report)
    last = await _last_event(session, scope)
    previous = (last.details if last else None) or None
    findings = drift_check.compare(previous, report)
    stamps = drift_check.stamp_summary(await recent_stamps(session, scope), report["versions"])
    findings += drift_check.stamp_findings(stamps)
    stored = drift_check.baseline_of(report, findings)
    drift = [f for f in findings if f.kind == "drift"]
    await record(
        session,
        ACTION,
        scope=scope,
        entity_type="pi_health",
        outcome="failure" if drift else "success",
        details={
            **stored,
            "stamps": stamps,
            "status": "drift" if drift else ("gaps" if findings else "ok"),
            "baseline": previous is None,
            "drift_count": len(drift),
            "gap_count": len(findings) - len(drift),
        },
    )
    await session.commit()
    return {"findings": [f.line() for f in findings], "stored": stored, "stamps": stamps}


async def latest(session: AsyncSession, scope: WorkspaceScope) -> dict[str, Any] | None:
    """The newest run for Health: status, counts, findings, the main numbers, when it ran."""
    last = await _last_event(session, scope)
    if last is None:
        return None
    d = last.details or {}
    return {
        "at": last.created_at.isoformat(),
        "status": d.get("status"),
        "baseline": bool(d.get("baseline")),
        "drift_count": d.get("drift_count", 0),
        "gap_count": d.get("gap_count", 0),
        "findings": d.get("findings", []),
        "summary": d.get("summary", {}),
        "versions": d.get("versions", {}),
        "stamps": d.get("stamps", {}),
    }


async def drift_check_daily(ctx: dict[str, Any]) -> int:
    """Cron job: for every workspace with an active WhatsApp number that turned the drift run on,
    run it at most once a day. One file scan serves every workspace."""
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.runtime import system_scope
    from app.modules.pi_saas.health_selftest import runner_scope

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection).where(WhatsAppConnection.status == "active")
            )
        )
    report: dict[str, Any] | None = None
    seen: set[tuple[Any, Any]] = set()
    ran = 0
    for connection in connections:
        key = (connection.tenant_id, connection.environment_id)
        if key in seen:
            continue
        seen.add(key)
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None:
                    continue
                scope = runner_scope(scope)
                policy = await settings_row(session, scope)
                if not enabled(policy.response_rules) or not await due(session, scope):
                    continue
                if report is None:
                    report = await asyncio.to_thread(drift_check.build_report)
                await run_drift_check(session, scope, report)
                ran += 1
            except Exception:  # noqa: BLE001 - one business never stops the others
                logger.warning("pi_drift_check_failed", exc_info=True)
    return ran
