from collections.abc import Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.memberships.models import Membership
from app.modules.tenants.context import active_memberships
from app.modules.tenants.models import Tenant
from app.shared.errors import ResourceNotFound
from app.shared.models import WorkspaceRow
from app.shared.scope import WorkspaceScope


def actor_is_active(scope: WorkspaceScope) -> ColumnElement[bool]:
    """Recheck the actor in SQL so revoked memberships stop working immediately."""
    if scope.user_id is not None and scope.membership_id is not None:
        member = active_memberships(scope.user_id).where(
            Membership.id == scope.membership_id, Membership.tenant_id == scope.tenant_id
        )
        return member.correlate(None).exists()
    return exists(
        select(Tenant.id).where(Tenant.id == scope.tenant_id, Tenant.status == "active")
    ).correlate(None)


class WorkspaceRepository[T: WorkspaceRow]:
    """Every statement is tenant + environment scoped. No unscoped lookups."""

    def __init__(self, session: AsyncSession, model: type[T], scope: WorkspaceScope) -> None:
        self.session, self.model, self.scope = session, model, scope

    def predicate(self) -> ColumnElement[bool]:
        return (
            (self.model.tenant_id == self.scope.tenant_id)
            & (self.model.environment_id == self.scope.environment_id)
            & actor_is_active(self.scope)
        )

    def select(self) -> Select[tuple[T]]:
        return select(self.model).where(self.predicate())

    async def get(self, record_id: UUID, *, for_update: bool = False) -> T:
        statement = self.select().where(self.model.id == record_id)
        if for_update:
            statement = statement.with_for_update()
        record = await self.session.scalar(statement)
        if record is None:
            raise ResourceNotFound
        return record

    async def find(self, *where: ColumnElement[bool]) -> T | None:
        found: T | None = await self.session.scalar(self.select().where(*where).limit(1))
        return found

    async def page(self, statement: Select[tuple[T]], page: Pagination) -> tuple[Sequence[T], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = await self.session.scalars(statement.offset(page.offset).limit(page.page_size))
        return rows.all(), int(total or 0)

    def new(self, **values: Any) -> T:
        # Ownership always comes from trusted scope, never from input payloads.
        values.pop("tenant_id", None)
        values.pop("environment_id", None)
        return self.model(
            tenant_id=self.scope.tenant_id, environment_id=self.scope.environment_id, **values
        )

    async def add(self, row: T) -> T:
        if row.tenant_id != self.scope.tenant_id or row.environment_id != self.scope.environment_id:
            raise ResourceNotFound
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete(self, row: T) -> None:
        await self.session.delete(row)
        await self.session.flush()


def to_page[S: BaseModel](
    schema: type[S], rows: Sequence[Any], total: int, page: Pagination
) -> Page[S]:
    return Page[S](
        items=[schema.model_validate(row) for row in rows],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
