from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.sales.schemas import (
    LeadCreate,
    LeadListItem,
    LeadStageUpdate,
    LeadUpdate,
    LeadView,
    PipelineStage,
    Stage,
)
from app.modules.sales.service import LEAD_STAGES, SalesService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/sales", tags=["sales"])
Read = Annotated[WorkspaceScope, Depends(require("sales.read"))]
Write = Annotated[WorkspaceScope, Depends(require("sales.write"))]
Paging = Annotated[Pagination, Query()]


@router.get("/pipeline", response_model=list[PipelineStage])
async def pipeline(scope: Read, session: Session) -> list[PipelineStage]:
    return await SalesService(session, scope).pipeline()


@router.get("/leads", response_model=Page[LeadListItem])
async def leads(
    scope: Read,
    session: Session,
    pagination: Paging,
    stage: Stage | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[LeadListItem]:
    return await SalesService(session, scope).search(pagination, stage, search)


@router.post("/leads", response_model=LeadView, status_code=status.HTTP_201_CREATED)
async def create_lead(data: LeadCreate, scope: Write, session: Session) -> LeadView:
    row = await SalesService(session, scope).create(data)
    await session.commit()
    return LeadView.model_validate(row)


@router.get("/leads/{lead_id}", response_model=LeadListItem)
async def lead(lead_id: UUID, scope: Read, session: Session) -> LeadListItem:
    row = await SalesService(session, scope).get(lead_id)
    return LeadListItem(
        **LeadView.model_validate(row).model_dump(),
        customer_name=None,
        next_stages=LEAD_STAGES.next_states(row.stage),
    )


@router.patch("/leads/{lead_id}", response_model=LeadView)
async def update_lead(lead_id: UUID, data: LeadUpdate, scope: Write, session: Session) -> LeadView:
    row = await SalesService(session, scope).update(lead_id, data)
    await session.commit()
    return LeadView.model_validate(row)


@router.put("/leads/{lead_id}/stage", response_model=LeadView)
async def move_lead(
    lead_id: UUID, data: LeadStageUpdate, scope: Write, session: Session
) -> LeadView:
    row = await SalesService(session, scope).move(lead_id, data.stage)
    await session.commit()
    return LeadView.model_validate(row)
