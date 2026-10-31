"""Audit a failed workspace permission check (outcome "denied").

Called from the 403 handler, which has no session of its own: the event is written in a
short transaction of its own, so it never rolls back with the failed request, and nothing
here may raise or change the 403. Details hold the route template and the missing
permission keys only: no path values, query string, body, headers or secrets.

Covered: `WorkspaceScope.require` denials and the two identity checks in
`access.dependencies.workspace_scope` (membership lost, Pi account closed or missing).
Not covered (bare `raise PermissionDenied`, no workspace context): the operator console,
payment routes, workflows and workspace_agent checks.

Bounds: per workspace, one row per (user, permission, method, route) a minute (200 keys, least
recently used evicted) and 60 rows a minute, so a workspace can only exhaust its own budget. At
most MAX_CONCURRENT_WRITES run at once (a saturated moment skips the audit, never the 403). A key
counts as seen only after its write succeeded, so a failed write is retried by the next denial.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from uuid import UUID

from fastapi import Request

from app.modules.audit.service import record
from app.shared.errors import PermissionDenied

logger = logging.getLogger("platform")

WINDOW_SECONDS = 60.0
KEYS_PER_TENANT = 200
PER_TENANT_PER_WINDOW = 60
MAX_TENANTS = 2000  # the least recently active workspace is forgotten (it only loses its throttle)
MAX_CONCURRENT_WRITES = 4
WRITE_TIMEOUT_SECONDS = 2.0

Key = tuple[UUID | None, str, str, str]


class _Tenant:
    __slots__ = ("count", "keys", "start")

    def __init__(self, now: float) -> None:
        self.start = now
        self.count = 0
        self.keys: OrderedDict[Key, float] = OrderedDict()


_tenants: OrderedDict[UUID, _Tenant] = OrderedDict()
_in_flight: set[tuple[UUID, Key]] = set()


def _reset() -> None:
    _tenants.clear()
    _in_flight.clear()


def _state(tenant_id: UUID, now: float) -> _Tenant:
    state = _tenants.get(tenant_id)
    if state is None:
        state = _tenants[tenant_id] = _Tenant(now)
        while len(_tenants) > MAX_TENANTS:
            _tenants.popitem(last=False)
    else:
        _tenants.move_to_end(tenant_id)
    if now - state.start >= WINDOW_SECONDS:
        state.start, state.count = now, 0
    return state


def _allow(tenant_id: UUID, key: Key, now: float) -> bool:
    """Whether a denial may be written now. Marks nothing: see `_mark_written`."""
    state = _state(tenant_id, now)
    seen_at = state.keys.get(key)
    if seen_at is not None and now - seen_at < WINDOW_SECONDS:
        return False
    return state.count < PER_TENANT_PER_WINDOW and (tenant_id, key) not in _in_flight


def _mark_written(tenant_id: UUID, key: Key, now: float) -> None:
    state = _state(tenant_id, now)
    state.count += 1
    state.keys[key] = now
    state.keys.move_to_end(key)
    while len(state.keys) > KEYS_PER_TENANT:
        state.keys.popitem(last=False)


def _safe_label(label: str | None) -> str | None:
    """display_name is free text the user typed (never defaulted to the email), but it may be
    an address: such a label is replaced, so no email lands in the audit row."""
    if label and "@" in label:
        return "user"
    return label


async def audit_denial(request: Request, exc: PermissionDenied) -> None:
    """Record one throttled "denied" event; never raises."""
    slot: tuple[UUID, Key] | None = None
    try:
        tenant_id = exc.tenant_id
        if tenant_id is None or not exc.missing:
            return  # not a workspace permission check (no tenant to scope the row to)
        route = getattr(request.scope.get("route"), "path", None) or "unknown"
        permission = ", ".join(exc.missing)[:200]
        method = request.method[:10]
        key: Key = (exc.user_id, permission, method, route)
        if len(_in_flight) >= MAX_CONCURRENT_WRITES or not _allow(tenant_id, key, time.monotonic()):
            return
        slot = (tenant_id, key)
        _in_flight.add(slot)
        sessions = request.app.state.sessions
        async with asyncio.timeout(WRITE_TIMEOUT_SECONDS), sessions() as session:
            await record(
                session,
                "access.denied",
                tenant_id=tenant_id,
                environment_id=exc.environment_id,
                actor_user_id=exc.user_id,
                actor_label=_safe_label(exc.actor_label),
                actor_type=exc.actor_type,
                request_id=exc.request_id,
                outcome="denied",
                details={"permission": permission, "method": method, "route": route[:200]},
            )
            await session.commit()
        _mark_written(tenant_id, key, time.monotonic())
    except Exception:
        logger.warning("denied_audit_failed", extra={"error_kind": "audit_write"})
    finally:
        if slot is not None:
            _in_flight.discard(slot)
