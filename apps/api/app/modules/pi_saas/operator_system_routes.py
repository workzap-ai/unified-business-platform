"""Operator control plane: every platform user, the audit log across workspaces, and
platform status. Part of the separate operator dashboard.

Capabilities:
- ``operator.users.read`` and ``operator.users.manage`` (disable/enable, sign out).
- ``operator.audit.read`` for the cross-workspace audit log.
- ``operator.system.read`` for platform counts.

Nothing here returns passwords, tokens or customer message content. Every change is
audited.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text, update

from app.modules.access.dependencies import Session
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record
from app.modules.auth.models import AuthSession
from app.modules.memberships.models import Membership
from app.modules.pi.models import PiMessage, WhatsAppConnection, WhatsAppWebhookEvent
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiOperatorMember,
    PiPoolNumber,
    PiProviderEvent,
    PiSubscription,
)
from app.modules.pi_saas.operator import Operator
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound
from app.shared.workspace_repository import like_pattern

router = APIRouter(prefix="/operator", tags=["pi-operator-system"])


# ------------------------------------------------------------------------ users


@router.get("/users")
async def users(
    operator: Operator,
    session: Session,
    search: str | None = Query(None, max_length=100),
    status: Literal["active", "inactive"] | None = None,
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    operator.require("operator.users.read")
    query = select(PlatformUser)
    if search:
        pattern = like_pattern(search)
        query = query.where(
            or_(PlatformUser.email.ilike(pattern), PlatformUser.display_name.ilike(pattern))
        )
    if status:
        query = query.where(PlatformUser.status == status)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        await session.scalars(
            query.order_by(PlatformUser.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    ids: list[Any] = [u.id for u in rows] or [None]
    seen: dict[Any, Any] = dict(
        (
            await session.execute(
                select(AuthSession.user_id, func.max(AuthSession.last_seen_at))
                .where(AuthSession.user_id.in_(ids))
                .group_by(AuthSession.user_id)
            )
        )
        .tuples()
        .all()
    )
    workspaces: dict[Any, list[str]] = {}
    for user_id, name in await session.execute(
        select(Membership.user_id, Tenant.name)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .where(Membership.user_id.in_(ids), Membership.status == "active")
    ):
        workspaces.setdefault(user_id, []).append(name)
    operators: dict[Any, Any] = dict(
        (
            await session.execute(
                select(PiOperatorMember.user_id, PiOperatorMember.role).where(
                    PiOperatorMember.user_id.in_(ids), PiOperatorMember.status == "active"
                )
            )
        )
        .tuples()
        .all()
    )
    return {
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.display_name,
                "status": u.status,
                "created_at": u.created_at,
                "last_seen_at": seen.get(u.id),
                "workspaces": sorted(workspaces.get(u.id, []))[:10],
                "operator_role": operators.get(u.id),
                "is_you": u.id == operator.user_id,
            }
            for u in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class UserStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["active", "inactive"]
    reason: str = Field(min_length=3, max_length=300)


async def _revoke_sessions(session: Any, user_id: UUID) -> int:
    result = await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return int(result.rowcount or 0)


async def _target_user(session: Any, operator: Any, user_id: UUID) -> PlatformUser:
    if user_id == operator.user_id:
        raise BusinessRuleViolation("OWN_ACCOUNT", "You can't do this to your own account")
    user: PlatformUser | None = await session.get(PlatformUser, user_id, with_for_update=True)
    if user is None:
        raise ResourceNotFound
    member = await session.scalar(
        select(PiOperatorMember).where(
            PiOperatorMember.user_id == user_id, PiOperatorMember.status == "active"
        )
    )
    if member is not None and member.role == "owner" and operator.role != "owner":
        raise PermissionDenied  # Only an operator owner can act on another owner.
    return user


@router.post("/users/{user_id}/status")
async def set_user_status(
    user_id: UUID, data: UserStatus, operator: Operator, session: Session
) -> dict[str, Any]:
    """Disable (or re-enable) a platform account. Disabling signs it out everywhere."""
    operator.require("operator.users.manage")
    user = await _target_user(session, operator, user_id)
    before, user.status = user.status, data.status
    revoked = await _revoke_sessions(session, user.id) if data.status == "inactive" else 0
    await record(
        session,
        f"pi_operator.user_{'disabled' if data.status == 'inactive' else 'enabled'}",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="platform_user",
        entity_id=user.id,
        details={"from": before, "to": data.status, "reason": data.reason, "sessions": revoked},
        include_environment=False,
    )
    await session.commit()
    return {"id": user.id, "status": user.status, "sessions_revoked": revoked}


@router.post("/users/{user_id}/sign-out")
async def sign_out_user(user_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.users.manage")
    user = await _target_user(session, operator, user_id)
    revoked = await _revoke_sessions(session, user.id)
    await record(
        session,
        "pi_operator.user_signed_out",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="platform_user",
        entity_id=user.id,
        details={"sessions": revoked},
        include_environment=False,
    )
    await session.commit()
    return {"sessions_revoked": revoked}


# ------------------------------------------------------------------------ audit


@router.get("/audit")
async def audit(
    operator: Operator,
    session: Session,
    tenant_id: UUID | None = None,
    action: str | None = Query(None, max_length=80),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Who did what, across every workspace (details are the audited metadata only)."""
    operator.require("operator.audit.read")
    query = select(AuditEvent, Tenant.name).outerjoin(Tenant, Tenant.id == AuditEvent.tenant_id)
    if tenant_id:
        query = query.where(AuditEvent.tenant_id == tenant_id)
    if action:
        query = query.where(AuditEvent.action.ilike(like_pattern(action)))
    rows = list(
        await session.execute(
            query.order_by(AuditEvent.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size + 1)
        )
    )
    return {
        "items": [
            {
                "id": event.id,
                "at": event.created_at,
                "workspace": name,
                "tenant_id": event.tenant_id,
                "action": event.action,
                "actor": event.actor_label,
                "actor_type": event.actor_type,
                "entity_type": event.entity_type,
                "outcome": event.outcome,
                "details": event.details,
            }
            for event, name in rows[:page_size]
        ],
        "page": page,
        "has_more": len(rows) > page_size,
    }


# ------------------------------------------------------------------------ system


@router.get("/system")
async def system(request: Request, operator: Operator, session: Session) -> dict[str, Any]:
    """Platform counts and runtime state for the operator dashboard."""
    operator.require("operator.system.read")
    since = datetime.now(UTC) - timedelta(hours=24)

    async def grouped(column: Any, model: Any) -> dict[str, int]:
        return {
            str(k): int(v)
            for k, v in await session.execute(
                select(column, func.count()).select_from(model).group_by(column)
            )
        }

    async def count(statement: Any) -> int:
        return int(await session.scalar(statement) or 0)

    try:
        head = await session.scalar(text("select version_num from alembic_version limit 1"))
    except Exception:  # noqa: BLE001 - informational only
        head = None
    settings = request.app.state.settings
    queue = type(getattr(request.app.state, "queue", None)).__name__
    return {
        "workspaces": await grouped(Tenant.status, Tenant),
        "users": await grouped(PlatformUser.status, PlatformUser),
        "pi_businesses": await grouped(PiBusinessAccount.setup_state, PiBusinessAccount),
        "subscriptions": await grouped(PiSubscription.status, PiSubscription),
        "whatsapp_numbers": await grouped(WhatsAppConnection.provider, WhatsAppConnection),
        "pool_numbers": await grouped(PiPoolNumber.status, PiPoolNumber),
        "operators": await count(
            select(func.count())
            .select_from(PiOperatorMember)
            .where(PiOperatorMember.status == "active")
        ),
        "messages_24h": {
            "received": await count(
                select(func.count())
                .select_from(PiMessage)
                .where(PiMessage.direction == "inbound", PiMessage.created_at >= since)
            ),
            "sent": await count(
                select(func.count())
                .select_from(PiMessage)
                .where(
                    PiMessage.direction == "outbound",
                    PiMessage.status.in_(["sent", "delivered", "read"]),
                    PiMessage.created_at >= since,
                )
            ),
            "failed": await count(
                select(func.count())
                .select_from(PiMessage)
                .where(PiMessage.status == "failed", PiMessage.created_at >= since)
            ),
        },
        "failed_events": await count(
            select(func.count())
            .select_from(WhatsAppWebhookEvent)
            .where(WhatsAppWebhookEvent.status == "failed")
        )
        + await count(
            select(func.count())
            .select_from(PiProviderEvent)
            .where(PiProviderEvent.status == "failed")
        ),
        "runtime": {
            "environment": settings.app_env,
            "database_revision": head,
            "job_queue": "background workers"
            if queue == "ArqQueue"
            else "in-process (single server)",
            "kapso_billing_mode": settings.kapso_meta_billing_mode,
        },
        "generated_at": datetime.now(UTC),
    }
