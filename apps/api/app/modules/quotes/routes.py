from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.orders.schemas import OrderView
from app.modules.orders.service import OrderService
from app.modules.quotes.schemas import QuoteCreate, QuoteDetail, QuoteListItem, QuoteUpdate
from app.modules.quotes.service import QuoteService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/quotes", tags=["quotes"])
Read = Annotated[WorkspaceScope, Depends(require("quotes.read"))]
Write = Annotated[WorkspaceScope, Depends(require("quotes.write"))]
Paging = Annotated[Pagination, Query()]
QuoteStatus = Literal[
    "draft", "pending_approval", "approved", "sent", "accepted", "rejected", "expired", "cancelled"
]


class QuoteAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal[
        "submit", "approve", "return_to_draft", "send", "accept", "reject", "expire", "cancel"
    ]


@router.get("", response_model=Page[QuoteListItem])
async def quotes(
    scope: Read,
    session: Session,
    pagination: Paging,
    status_filter: Annotated[QuoteStatus | None, Query(alias="status")] = None,
    customer_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[QuoteListItem]:
    return await QuoteService(session, scope).search(pagination, status_filter, customer_id, search)


@router.post("", response_model=QuoteDetail, status_code=status.HTTP_201_CREATED)
async def create_quote(data: QuoteCreate, scope: Write, session: Session) -> QuoteDetail:
    service = QuoteService(session, scope)
    quote = await service.create(data)
    await session.commit()
    return await service.detail(quote.id)


@router.get("/{quote_id}", response_model=QuoteDetail)
async def quote(quote_id: UUID, scope: Read, session: Session) -> QuoteDetail:
    return await QuoteService(session, scope).detail(quote_id)


@router.patch("/{quote_id}", response_model=QuoteDetail)
async def update_quote(
    quote_id: UUID, data: QuoteUpdate, scope: Write, session: Session
) -> QuoteDetail:
    service = QuoteService(session, scope)
    await service.update(quote_id, data)
    await session.commit()
    return await service.detail(quote_id)


@router.post("/{quote_id}/actions", response_model=QuoteDetail)
async def act(quote_id: UUID, data: QuoteAction, scope: Read, session: Session) -> QuoteDetail:
    # Permission depends on the action (approve vs write) and is checked in the service.
    service = QuoteService(session, scope)
    await service.transition(quote_id, data.action)
    await session.commit()
    return await service.detail(quote_id)


@router.post("/{quote_id}/order", response_model=OrderView, status_code=status.HTTP_201_CREATED)
async def convert(quote_id: UUID, scope: Write, session: Session) -> OrderView:
    order = await OrderService(session, scope).create_from_quote(quote_id)
    await session.commit()
    return OrderView.model_validate(order)
