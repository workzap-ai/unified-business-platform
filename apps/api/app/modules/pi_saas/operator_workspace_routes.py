"""Platform operator view of every Owner OS workspace (/api/v1/operator/workspaces).

Operational metadata only (name, status, size, products, whether it is a Pi business).
No business records or customer content are returned. Suspending a workspace blocks its
members' requests (active-tenant checks run on every request) and stops Pi automation;
its data is kept.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.modules.access.dependencies import Session
from app.modules.audit.service import record
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.pi_saas.models import PiBusinessAccount
from app.modules.pi_saas.operator import Operator
from app.modules.products.models import PlatformProduct, TenantProductInstallation
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.workspace_repository import like_pattern

router = APIRouter(prefix="/operator/workspaces", tags=["operator-workspaces"])


def _members(tenant_id: Any) -> Any:
    return (
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.status == "active")
        .scalar_subquery()
    )


@router.get("")
async def workspaces(
    operator: Operator,
    session: Session,
    search: str | None = Query(None, max_length=100),
    kind: Literal["all", "pi", "owner_os"] = "all",
    status: Literal["active", "inactive"] | None = None,
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    query = select(
        Tenant,
        _members(Tenant.id).label("members"),
        select(PiBusinessAccount.setup_state)
        .where(PiBusinessAccount.tenant_id == Tenant.id)
        .scalar_subquery()
        .label("pi_state"),
        select(Membership.id)
        .where(
            Membership.tenant_id == Tenant.id,
            Membership.user_id == operator.user_id,
            Membership.status == "active",
        )
        .exists()
        .label("is_member"),
    )
    if search:
        pattern = like_pattern(search)
        query = query.where(Tenant.name.ilike(pattern) | Tenant.slug.ilike(pattern))
    pi_tenants = select(PiBusinessAccount.tenant_id)
    if kind == "pi":
        query = query.where(Tenant.id.in_(pi_tenants))
    elif kind == "owner_os":
        query = query.where(Tenant.id.not_in(pi_tenants))
    if status:
        query = query.where(Tenant.status == status)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        await session.execute(
            query.order_by(Tenant.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    products: dict[Any, list[str]] = {}
    if rows:
        found = await session.execute(
            select(TenantProductInstallation.tenant_id, PlatformProduct.key)
            .join(PlatformProduct, PlatformProduct.id == TenantProductInstallation.product_id)
            .where(
                TenantProductInstallation.tenant_id.in_([r[0].id for r in rows]),
                TenantProductInstallation.status == "installed",
            )
        )
        for tenant_id, key in found:
            products.setdefault(tenant_id, []).append(key)
    return {
        "items": [
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "created_at": tenant.created_at,
                "members": int(members or 0),
                "products": sorted(products.get(tenant.id, [])),
                "kind": "pi" if pi_state is not None else "owner_os",
                "pi_setup_state": pi_state,
                # The operator can't suspend a workspace they work in (see set_status).
                "is_member": bool(is_member),
            }
            for tenant, members, pi_state, is_member in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{tenant_id}")
async def workspace(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ResourceNotFound
    environments = await session.scalars(
        select(Environment)
        .where(Environment.tenant_id == tenant_id)
        .order_by(Environment.created_at)
    )
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    members = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.status == "active")
    )
    await record(
        session,
        "pi_operator.workspace_viewed",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        include_environment=False,
    )
    await session.commit()
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "created_at": tenant.created_at,
        "members": int(members or 0),
        "environments": [
            {"key": e.key, "name": e.name, "kind": e.kind, "status": e.status} for e in environments
        ],
        "pi_business": {"setup_state": account.setup_state, "status": account.status}
        if account
        else None,
    }


class WorkspaceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["active", "inactive"]
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{tenant_id}/status")
async def set_status(
    tenant_id: UUID, data: WorkspaceStatus, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.manage")
    tenant = await session.get(Tenant, tenant_id, with_for_update=True)
    if tenant is None:
        raise ResourceNotFound
    if data.status == "inactive":
        own = await session.scalar(
            select(Membership.id).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == operator.user_id,
                Membership.status == "active",
            )
        )
        if own is not None:
            raise BusinessRuleViolation(
                "OWN_WORKSPACE", "You can't suspend a workspace you are working in"
            )
    before = tenant.status
    tenant.status = data.status
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id).with_for_update()
    )
    touched = False
    if account is not None and data.status == "inactive" and account.status == "active":
        account.status, account.suspended_by_workspace, touched = "suspended", True, True
    elif (
        account is not None
        and data.status == "active"
        and account.status == "suspended"
        and account.suspended_by_workspace
    ):
        # Only undo the suspension this action caused; a separate business suspension
        # (for example abuse) stays until an operator reinstates that business.
        account.status, account.suspended_by_workspace, touched = "active", False, True
    await record(
        session,
        f"pi_operator.workspace_{'reactivated' if data.status == 'active' else 'suspended'}",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        details={
            "from": before,
            "to": data.status,
            "reason": data.reason,
            "role": operator.role,
            "pi_account_suspended": touched and data.status == "inactive",
        },
        include_environment=False,
    )
    await session.commit()
    return {"id": tenant.id, "status": tenant.status}
