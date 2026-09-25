from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import Page, Pagination
from app.modules.tenants.context import resolve_scope
from app.modules.tenants.dependencies import authenticated_user_id
from app.modules.tenants.schemas import BranchView, TenantView
from app.modules.tenants.service import OrganizationService, list_tenants

router = APIRouter(prefix="/tenants", tags=["tenants"])
Actor = Annotated[UUID, Depends(authenticated_user_id)]
Session = Annotated[AsyncSession, Depends(get_session)]
Paging = Annotated[Pagination, Depends()]


@router.get("", response_model=Page[TenantView])
async def tenants(user_id: Actor, session: Session, pagination: Paging) -> Page[TenantView]:
    return await list_tenants(session, user_id, pagination)


@router.get("/{tenant_id}/branches", response_model=Page[BranchView])
async def branches(
    tenant_id: UUID, user_id: Actor, session: Session, pagination: Paging
) -> Page[BranchView]:
    scope = await resolve_scope(session, user_id, tenant_id)
    return await OrganizationService(session, scope).list_branches(pagination)
