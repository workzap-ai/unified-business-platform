from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.access.members import MemberService
from app.modules.access.permissions import PERMISSIONS
from app.modules.access.schemas import (
    MemberCreate,
    MemberRolesUpdate,
    MemberView,
    PermissionView,
    RoleCreate,
    RoleUpdate,
    RoleView,
)
from app.modules.access.service import RoleService
from app.shared.scope import WorkspaceScope

router = APIRouter(tags=["access"])
MembersRead = Annotated[WorkspaceScope, Depends(require("admin.members.read"))]
MembersManage = Annotated[WorkspaceScope, Depends(require("admin.members.manage"))]
RolesManage = Annotated[WorkspaceScope, Depends(require("admin.roles.manage"))]
Paging = Annotated[Pagination, Query()]


@router.get("/permissions", response_model=list[PermissionView])
async def permissions(scope: MembersRead) -> list[PermissionView]:
    return [PermissionView(key=p.key, label=p.label, group=p.group) for p in PERMISSIONS.values()]


@router.get("/roles", response_model=list[RoleView])
async def roles(scope: MembersRead, session: Session) -> list[RoleView]:
    return [
        RoleView(
            id=r.id,
            key=r.key,
            name=r.name,
            description=r.description,
            is_system=r.is_system,
            permissions=perms,
            member_count=count,
        )
        for r, perms, count in await RoleService(session, scope).search()
    ]


@router.post("/roles", response_model=RoleView, status_code=status.HTTP_201_CREATED)
async def create_role(data: RoleCreate, scope: RolesManage, session: Session) -> RoleView:
    role = await RoleService(session, scope).create(
        data.key, data.name, data.description, set(data.permissions)
    )
    await session.commit()
    return RoleView(
        id=role.id,
        key=role.key,
        name=role.name,
        description=role.description,
        is_system=False,
        permissions=sorted(set(data.permissions)),
        member_count=0,
    )


@router.put("/roles/{role_id}", response_model=RoleView)
async def update_role(
    role_id: UUID, data: RoleUpdate, scope: RolesManage, session: Session
) -> RoleView:
    service = RoleService(session, scope)
    await service.update(role_id, data.name, data.description, set(data.permissions))
    await session.commit()
    for r, perms, count in await service.search():
        if r.id == role_id:
            return RoleView(
                id=r.id,
                key=r.key,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
                permissions=perms,
                member_count=count,
            )
    raise RuntimeError("Role disappeared")  # pragma: no cover


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(role_id: UUID, scope: RolesManage, session: Session) -> Response:
    await RoleService(session, scope).delete(role_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/members", response_model=Page[MemberView])
async def members(
    scope: MembersRead,
    session: Session,
    pagination: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[MemberView]:
    return await MemberService(session, scope).search(pagination, search)


@router.post("/members", response_model=MemberView, status_code=status.HTTP_201_CREATED)
async def add_member(data: MemberCreate, scope: MembersManage, session: Session) -> MemberView:
    result = await MemberService(session, scope).add(data)
    await session.commit()
    return result


@router.put("/members/{membership_id}/roles", response_model=MemberView)
async def update_member_roles(
    membership_id: UUID, data: MemberRolesUpdate, scope: MembersManage, session: Session
) -> MemberView:
    result = await MemberService(session, scope).update_roles(membership_id, data.role_ids)
    await session.commit()
    return result


@router.delete("/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_member(membership_id: UUID, scope: MembersManage, session: Session) -> Response:
    await MemberService(session, scope).revoke(membership_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
