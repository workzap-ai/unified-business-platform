"""Audit a failed workspace permission check (outcome "denied").

Called from the 403 handler, which has no session of its own: the event is written in a
short transaction of its own, so it never rolls back with the failed request, and nothing
here may raise or change the 403. Details hold the route template and the missing
permission keys only: no path values, query string, body, headers or secrets.
"""

import asyncio
import logging
import time
from uuid import UUID

from fastapi import Request

from app.modules.audit.service import record
from app.shared.errors import PermissionDenied

logger = logging.getLogger("platform")

WINDOW_SECONDS = 60.0
PER_TENANT_PER_WINDOW = 60  # a flood from one workspace cannot write more than this a minute
MAX_TRACKED = 5000  # bounds the in-process throttle memory; when full, new keys are not audited
WRITE_TIMEOUT_SECONDS = 2.0

_seen: dict[tuple[UUID, UUID | None, str, str, str], float] = {}
_tenant_counts: dict[UUID, tuple[float, int]] = {}


def _allow(tenant_id: UUID, key: tuple[UUID, UUID | None, str, str, str], now: float) -> bool:
    if len(_seen) >= MAX_TRACKED:
        for k in [k for k, t in _seen.items() if now - t >= WINDOW_SECONDS]:
            del _seen[k]
        if len(_seen) >= MAX_TRACKED:
            return False
    if len(_tenant_counts) >= MAX_TRACKED:
        for t, (start, _) in list(_tenant_counts.items()):
            if now - start >= WINDOW_SECONDS:
                del _tenant_counts[t]
    seen_at = _seen.get(key)
    if seen_at is not None and now - seen_at < WINDOW_SECONDS:
        return False
    start, count = _tenant_counts.get(tenant_id, (now, 0))
    if now - start >= WINDOW_SECONDS:
        start, count = now, 0
    if count >= PER_TENANT_PER_WINDOW:
        _tenant_counts[tenant_id] = (start, count)
        return False
    _tenant_counts[tenant_id] = (start, count + 1)
    _seen[key] = now
    return True


async def audit_denial(request: Request, exc: PermissionDenied) -> None:
    """Record one throttled "denied" event; never raises."""
    try:
        if exc.tenant_id is None or not exc.missing:
            return  # not a workspace permission check (no tenant to scope the row to)
        route = getattr(request.scope.get("route"), "path", None) or "unknown"
        permission = ", ".join(exc.missing)[:200]
        method = request.method[:10]
        if not _allow(
            exc.tenant_id, (exc.tenant_id, exc.user_id, permission, method, route), time.monotonic()
        ):
            return
        sessions = request.app.state.sessions
        async with asyncio.timeout(WRITE_TIMEOUT_SECONDS), sessions() as session:
            await record(
                session,
                "access.denied",
                tenant_id=exc.tenant_id,
                environment_id=exc.environment_id,
                actor_user_id=exc.user_id,
                actor_label=exc.actor_label,
                request_id=exc.request_id,
                outcome="denied",
                details={"permission": permission, "method": method, "route": route[:200]},
            )
            await session.commit()
    except Exception:
        logger.warning("denied_audit_failed", extra={"error_kind": "audit_write"})
