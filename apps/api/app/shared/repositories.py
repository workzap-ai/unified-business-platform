from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Pagination
from app.modules.memberships.models import Membership
from app.modules.tenants.context import TenantScope, active_memberships
from app.modules.tenants.errors import ResourceNotFound
from app.shared.models import TenantRow


class TenantRepository[T: TenantRow]:
    """No unscoped get/update/delete. Membership is rechecked in every statement."""

    def __init__(self, session: AsyncSession, model: type[T], scope: TenantScope) -> None:
        self.session, self.model, self.scope = session, model, scope

    def predicate(self) -> ColumnElement[bool]:
        member = active_memberships(self.scope.user_id).where(
            Membership.id == self.scope.membership_id, Membership.tenant_id == self.scope.tenant_id
        )
        return (self.model.tenant_id == self.scope.tenant_id) & member.correlate(None).exists()

    async def get(self, record_id: UUID) -> T:
        record = await self.session.scalar(
            select(self.model).where(self.predicate(), self.model.id == record_id)
        )
        if record is None:
            raise ResourceNotFound
        return record

    async def list(self, page: Pagination) -> tuple[list[T], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(self.model).where(self.predicate())
        )
        rows = await self.session.scalars(
            select(self.model)
            .where(self.predicate())
            .order_by(self.model.id)
            .offset(page.offset)
            .limit(page.page_size)
        )
        return list(rows), int(total or 0)

    async def rename(self, record_id: UUID, name: str) -> T:
        # Only a name can be changed here: never mass-assign ownership or IDs.
        if "name" not in self.model.__table__.columns:
            raise TypeError("This repository model has no name")
        record = await self.session.scalar(
            update(self.model)
            .where(self.predicate(), self.model.id == record_id)
            .values(name=name)
            .returning(self.model)
        )
        if record is None:
            raise ResourceNotFound
        return record

    async def delete(self, record_id: UUID) -> None:
        deleted = await self.session.scalar(
            delete(self.model)
            .where(self.predicate(), self.model.id == record_id)
            .returning(self.model.id)
        )
        if deleted is None:
            raise ResourceNotFound
