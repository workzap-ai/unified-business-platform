from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.hr.service import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeView,
    Headcount,
    HRService,
    Status,
)
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/hr", tags=["hr"])
Read = Annotated[WorkspaceScope, Depends(require("hr.read"))]
Write = Annotated[WorkspaceScope, Depends(require("hr.write"))]
Paging = Annotated[Pagination, Query()]


@router.get("/headcount", response_model=Headcount)
async def headcount(scope: Read, session: Session) -> Headcount:
    return await HRService(session, scope).headcount()


@router.get("/employees", response_model=Page[EmployeeView])
async def employees(
    scope: Read,
    session: Session,
    pagination: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Status | None, Query(alias="status")] = None,
    department_id: UUID | None = None,
) -> Page[EmployeeView]:
    return await HRService(session, scope).search(pagination, search, status_filter, department_id)


@router.post("/employees", response_model=EmployeeView, status_code=status.HTTP_201_CREATED)
async def create_employee(data: EmployeeCreate, scope: Write, session: Session) -> EmployeeView:
    result = await HRService(session, scope).create(data)
    await session.commit()
    return result


@router.get("/employees/{employee_id}", response_model=EmployeeView)
async def employee(employee_id: UUID, scope: Read, session: Session) -> EmployeeView:
    return await HRService(session, scope).get(employee_id)


@router.patch("/employees/{employee_id}", response_model=EmployeeView)
async def update_employee(
    employee_id: UUID, data: EmployeeUpdate, scope: Write, session: Session
) -> EmployeeView:
    result = await HRService(session, scope).update(employee_id, data)
    await session.commit()
    return result
