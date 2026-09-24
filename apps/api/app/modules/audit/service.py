import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.shared.scope import WorkspaceScope

SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|api[_-]?key|authorization|cookie|credential|signature|salary",
    re.IGNORECASE,
)
MAX_TEXT = 300


def redact(value: Any, depth: int = 0) -> Any:
    """Allow structural context but never secrets or unbounded customer content."""
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(k)[:60]: "[redacted]" if SENSITIVE_KEY.search(str(k)) else redact(v, depth + 1)
            for k, v in list(value.items())[:40]
        }
    if isinstance(value, list | tuple):
        return [redact(v, depth + 1) for v in list(value)[:40]]
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if isinstance(value, bool | int | None):
        return value
    return str(value)[:MAX_TEXT]


async def record(
    session: AsyncSession,
    action: str,
    *,
    scope: WorkspaceScope | None = None,
    tenant_id: UUID | None = None,
    environment_id: UUID | None = None,
    actor_user_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
    include_environment: bool = True,
) -> None:
    """Append an audit event inside the caller's transaction."""
    if scope is not None:
        tenant_id = scope.tenant_id
        environment_id = scope.environment_id if include_environment else None
        actor_user_id = scope.user_id
        actor_type: str = scope.actor_type
        actor_label = scope.actor_label
        request_id = request_id or scope.request_id
    else:
        actor_type = "user" if actor_user_id else "anonymous"
        actor_label = "user" if actor_user_id else "anonymous"
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            environment_id=environment_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            actor_label=actor_label[:80],
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            request_id=request_id,
            details=redact(details or {}),
        )
    )
    await session.flush()
