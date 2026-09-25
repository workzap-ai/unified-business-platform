from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.inventory.schemas import (
    LocationCreate,
    LocationView,
    MovementView,
    StockAdjustment,
    StockLevelView,
)
from app.modules.inventory.service import InventoryService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/inventory", tags=["inventory"])
Read = Annotated[WorkspaceScope, Depends(require("inventory.read"))]
Adjust = Annotated[WorkspaceScope, Depends(require("inventory.adjust"))]
Paging = Annotated[Pagination, Depends()]


@router.get("/locations", response_model=list[LocationView])
async def locations(scope: Read, session: Session) -> list[LocationView]:
    rows = await InventoryService(session, scope).list_locations()
    await session.commit()  # the default location may have been created on first use
    return [LocationView.model_validate(r) for r in rows]


@router.post("/locations", response_model=LocationView, status_code=status.HTTP_201_CREATED)
async def create_location(data: LocationCreate, scope: Adjust, session: Session) -> LocationView:
    row = await InventoryService(session, scope).create_location(data)
    await session.commit()
    return LocationView.model_validate(row)


@router.get("/levels", response_model=Page[StockLevelView])
async def levels(
    scope: Read,
    session: Session,
    pagination: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    location_id: UUID | None = None,
    low_only: bool = False,
) -> Page[StockLevelView]:
    return await InventoryService(session, scope).list_levels(
        pagination, search, location_id, low_only
    )


@router.post("/adjustments", response_model=MovementView, status_code=status.HTTP_201_CREATED)
async def adjust(data: StockAdjustment, scope: Adjust, session: Session) -> MovementView:
    movement = await InventoryService(session, scope).adjust(data)
    await session.commit()
    return MovementView.model_validate(movement)


@router.get("/movements", response_model=Page[MovementView])
async def movements(
    scope: Read, session: Session, pagination: Paging, variant_id: UUID | None = None
) -> Page[MovementView]:
    return await InventoryService(session, scope).movements_page(pagination, variant_id)
