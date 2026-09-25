from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.orders.schemas import (
    OrderCreate,
    OrderDetail,
    OrderLinesUpdate,
    OrderListItem,
    OrderTransition,
)
from app.modules.orders.service import OrderService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/orders", tags=["orders"])
Read = Annotated[WorkspaceScope, Depends(require("orders.read"))]
Write = Annotated[WorkspaceScope, Depends(require("orders.write"))]
Paging = Annotated[Pagination, Depends()]
OrderStatus = Literal["draft", "confirmed", "processing", "shipped", "delivered", "cancelled"]


@router.get("", response_model=Page[OrderListItem])
async def orders(
    scope: Read,
    session: Session,
    pagination: Paging,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    customer_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[OrderListItem]:
    return await OrderService(session, scope).search(pagination, status_filter, customer_id, search)


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
async def create_order(data: OrderCreate, scope: Write, session: Session) -> OrderDetail:
    service = OrderService(session, scope)
    order = await service.create_draft(data)
    await session.commit()
    return await service.detail(order.id)


@router.get("/{order_id}", response_model=OrderDetail)
async def order(order_id: UUID, scope: Read, session: Session) -> OrderDetail:
    return await OrderService(session, scope).detail(order_id)


@router.put("/{order_id}/lines", response_model=OrderDetail)
async def update_lines(
    order_id: UUID, data: OrderLinesUpdate, scope: Write, session: Session
) -> OrderDetail:
    service = OrderService(session, scope)
    await service.update_lines(order_id, data.lines)
    await session.commit()
    return await service.detail(order_id)


@router.post("/{order_id}/actions", response_model=OrderDetail)
async def act(order_id: UUID, data: OrderTransition, scope: Read, session: Session) -> OrderDetail:
    # confirm/progress need orders.write, cancel needs orders.cancel; checked in the service.
    service = OrderService(session, scope)
    await service.transition(order_id, data.action)
    await session.commit()
    return await service.detail(order_id)
