from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.branches.models import Branch
from app.modules.departments.models import Department
from app.modules.memberships.models import Membership
from app.modules.tenants.context import TenantScope, active_memberships, require_active_scope
from app.modules.tenants.errors import OrganizationConflict
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import (
    BranchCreate,
    BranchView,
    DepartmentCreate,
    DepartmentView,
    Rename,
    TenantView,
)
from app.shared.repositories import TenantRepository


async def list_tenants(session: AsyncSession, user_id: UUID, page: Pagination) -> Page[TenantView]:
    member_tenants = active_memberships(user_id).with_only_columns(Membership.tenant_id)
    predicate = Tenant.id.in_(member_tenants)
    total = await session.scalar(select(func.count()).select_from(Tenant).where(predicate))
    rows = await session.scalars(
        select(Tenant)
        .where(predicate)
        .order_by(Tenant.name, Tenant.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return Page(
        items=[TenantView.model_validate(row) for row in rows],
        total=int(total or 0),
        page=page.page,
        page_size=page.page_size,
    )


class OrganizationService:
    """Internal scoped operations. Caller owns the transaction; HTTP writes await RBAC."""

    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self.session, self.scope = session, scope
        self.branches = TenantRepository(session, Branch, scope)
        self.departments = TenantRepository(session, Department, scope)

    async def list_branches(self, page: Pagination) -> Page[BranchView]:
        await require_active_scope(self.session, self.scope)
        rows, total = await self.branches.list(page)
        return Page(
            items=[BranchView.model_validate(row) for row in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def create_branch(self, data: BranchCreate) -> BranchView:
        await require_active_scope(self.session, self.scope, for_write=True)
        try:
            async with self.session.begin_nested():
                row = Branch(tenant_id=self.scope.tenant_id, **data.model_dump())
                self.session.add(row)
                await self.session.flush()
                result = BranchView.model_validate(row)
        except IntegrityError:
            raise OrganizationConflict from None
        return result

    async def create_department(self, data: DepartmentCreate) -> DepartmentView:
        await require_active_scope(self.session, self.scope, for_write=True)
        if data.branch_id is not None:
            await self.branches.get(data.branch_id)
        try:
            async with self.session.begin_nested():
                row = Department(tenant_id=self.scope.tenant_id, **data.model_dump())
                self.session.add(row)
                await self.session.flush()
                result = DepartmentView.model_validate(row)
        except IntegrityError:
            raise OrganizationConflict from None
        return result

    async def rename_branch(self, record_id: UUID, data: Rename) -> BranchView:
        row = await self.branches.rename(record_id, data.name)
        return BranchView.model_validate(row)

    async def delete_branch(self, record_id: UUID) -> None:
        try:
            async with self.session.begin_nested():
                await self.branches.delete(record_id)
        except IntegrityError:
            raise OrganizationConflict from None
