"""Backend-controlled environment capabilities, independent of role grants."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business_settings.models import BusinessSettings


async def business_permissions(
    session: AsyncSession, tenant_id: UUID, environment_id: UUID, permissions: frozenset[str]
) -> frozenset[str]:
    kind = await session.scalar(
        select(BusinessSettings.business_type).where(
            BusinessSettings.tenant_id == tenant_id,
            BusinessSettings.environment_id == environment_id,
        )
    )
    return apply_business_type(kind, permissions)


def apply_business_type(kind: str | None, permissions: frozenset[str]) -> frozenset[str]:
    """Service businesses have no stock: inventory permissions do not apply."""
    if kind is None or kind == "service_business":
        return frozenset(p for p in permissions if not p.startswith("inventory."))
    return permissions
