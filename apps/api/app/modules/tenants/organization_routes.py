"""Branch/department administration for the current workspace (RBAC protected)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Scope, Session, require
from app.modules.audit.service import record
from app.modules.departments.models import Department
from app.modules.tenants.models import Tenant
from app.modules.tenants.schemas import (
    BranchCreate,
    BranchView,
    DepartmentCreate,
    DepartmentView,
    Rename,
)
from app.modules.tenants.service import OrganizationService
from app.shared.errors import ResourceNotFound
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/organization", tags=["organization"])
Manage = Annotated[WorkspaceScope, Depends(require("admin.organization.manage"))]
Settings = Annotated[WorkspaceScope, Depends(require("settings.manage"))]
Paging = Annotated[Pagination, Depends()]


class OrganizationView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str


class OrganizationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]


@router.get("", response_model=OrganizationView)
async def organization(scope: Scope, session: Session) -> OrganizationView:
    tenant = await session.get(Tenant, scope.tenant_id)
    if tenant is None:
        raise ResourceNotFound
    return OrganizationView.model_validate(tenant)


@router.patch("", response_model=OrganizationView)
async def update_organization(
    data: OrganizationUpdate, scope: Settings, session: Session
) -> OrganizationView:
    tenant = await session.get(Tenant, scope.tenant_id, with_for_update=True)
    if tenant is None:
        raise ResourceNotFound
    tenant.name = data.name
    await record(
        session, "organization.renamed", scope=scope, entity_type="tenant", entity_id=tenant.id
    )
    await session.commit()
    return OrganizationView.model_validate(tenant)


@router.get("/branches", response_model=Page[BranchView])
async def branches(scope: Scope, session: Session, pagination: Paging) -> Page[BranchView]:
    return await OrganizationService(session, scope.tenant_scope()).list_branches(pagination)


@router.post("/branches", response_model=BranchView, status_code=status.HTTP_201_CREATED)
async def create_branch(data: BranchCreate, scope: Manage, session: Session) -> BranchView:
    result = await OrganizationService(session, scope.tenant_scope()).create_branch(data)
    await record(session, "branch.created", scope=scope, entity_type="branch", entity_id=result.id)
    await session.commit()
    return result


@router.patch("/branches/{branch_id}", response_model=BranchView)
async def rename_branch(
    branch_id: UUID, data: Rename, scope: Manage, session: Session
) -> BranchView:
    result = await OrganizationService(session, scope.tenant_scope()).rename_branch(branch_id, data)
    await record(session, "branch.renamed", scope=scope, entity_type="branch", entity_id=branch_id)
    await session.commit()
    return result


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(branch_id: UUID, scope: Manage, session: Session) -> Response:
    await OrganizationService(session, scope.tenant_scope()).delete_branch(branch_id)
    await record(session, "branch.deleted", scope=scope, entity_type="branch", entity_id=branch_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/departments", response_model=Page[DepartmentView])
async def departments(scope: Scope, session: Session, pagination: Paging) -> Page[DepartmentView]:
    service = OrganizationService(session, scope.tenant_scope())
    predicate = service.departments.predicate()
    total = await session.scalar(select(func.count()).select_from(Department).where(predicate))
    rows = await session.scalars(
        select(Department)
        .where(predicate)
        .order_by(Department.name, Department.id)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    return Page(
        items=[DepartmentView.model_validate(r) for r in rows],
        total=int(total or 0),
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/departments", response_model=DepartmentView, status_code=status.HTTP_201_CREATED)
async def create_department(
    data: DepartmentCreate, scope: Manage, session: Session
) -> DepartmentView:
    result = await OrganizationService(session, scope.tenant_scope()).create_department(data)
    await record(
        session, "department.created", scope=scope, entity_type="department", entity_id=result.id
    )
    await session.commit()
    return result


@router.patch("/departments/{department_id}", response_model=DepartmentView)
async def rename_department(
    department_id: UUID, data: Rename, scope: Manage, session: Session
) -> DepartmentView:
    service = OrganizationService(session, scope.tenant_scope())
    row = await service.departments.rename(department_id, data.name)
    await record(
        session, "department.renamed", scope=scope, entity_type="department", entity_id=row.id
    )
    await session.commit()
    return DepartmentView.model_validate(row)
