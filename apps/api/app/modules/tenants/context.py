from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memberships.models import Membership
from app.modules.tenants.errors import ResourceNotFound
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Internal context. Never deserialize this from browser or model input."""

    user_id: UUID
    tenant_id: UUID
    membership_id: UUID


def active_memberships(user_id: UUID) -> Select[tuple[Membership]]:
    return (
        select(Membership)
        .join(Tenant, Tenant.id == Membership.tenant_id)
        .join(PlatformUser, PlatformUser.id == Membership.user_id)
        .where(
            Membership.user_id == user_id,
            Membership.status == "active",
            Tenant.status == "active",
            PlatformUser.status == "active",
        )
    )


async def resolve_scope(
    session: AsyncSession, authenticated_user_id: UUID, tenant_id: UUID
) -> TenantScope:
    membership = await session.scalar(
        active_memberships(authenticated_user_id).where(Membership.tenant_id == tenant_id)
    )
    if membership is None:
        raise ResourceNotFound
    return TenantScope(authenticated_user_id, tenant_id, membership.id)


async def require_active_scope(
    session: AsyncSession, scope: TenantScope, *, for_write: bool = False
) -> None:
    query = active_memberships(scope.user_id).where(
        Membership.id == scope.membership_id, Membership.tenant_id == scope.tenant_id
    )
    if for_write:
        # Hold shared locks through the caller's transaction so revocation/deactivation
        # cannot race a scoped insert. Locks do not grant a business permission.
        query = query.with_for_update(read=True)
    found = await session.scalar(query)
    if found is None:
        raise ResourceNotFound
