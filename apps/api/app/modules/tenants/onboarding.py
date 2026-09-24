import re
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.service import assign_roles, seed_system_roles
from app.modules.audit.service import record
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60].strip("-")
    return slug or "workspace"


async def unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    for candidate in [base, *(f"{base}-{n}" for n in range(2, 6))]:
        if await session.scalar(select(Tenant.id).where(Tenant.slug == candidate)) is None:
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


async def provision_tenant(
    session: AsyncSession, owner: PlatformUser, name: str
) -> tuple[Tenant, Environment, Membership]:
    """Create a tenant with a default production environment and an owner membership.

    Runs inside the caller's transaction; the caller commits.
    """
    tenant = Tenant(name=name, slug=await unique_slug(session, name))
    session.add(tenant)
    await session.flush()
    environment = Environment(
        tenant_id=tenant.id, key="production", name="Production", kind="production", is_default=True
    )
    membership = Membership(tenant_id=tenant.id, user_id=owner.id)
    session.add_all([environment, membership])
    await session.flush()
    roles = await seed_system_roles(session, tenant.id)
    await assign_roles(session, tenant.id, membership.id, [roles["owner"].id])
    await record(
        session,
        "tenant.provisioned",
        tenant_id=tenant.id,
        actor_user_id=owner.id,
        entity_type="tenant",
        entity_id=tenant.id,
    )
    return tenant, environment, membership
