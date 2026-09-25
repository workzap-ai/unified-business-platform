from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.billing.service import BillingService
from app.modules.business_settings.service import get_settings_row
from app.modules.customers.schemas import (
    ActivityView,
    CustomerCreate,
    CustomerDetail,
    CustomerStatusUpdate,
    CustomerSummary,
    CustomerUpdate,
    CustomerView,
    NoteCreate,
    NoteView,
)
from app.modules.customers.service import CustomerService
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation
from app.modules.quotes.models import Quote
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/customers", tags=["customers"])
Read = Annotated[WorkspaceScope, Depends(require("customers.read"))]
Write = Annotated[WorkspaceScope, Depends(require("customers.write"))]
Paging = Annotated[Pagination, Depends()]


async def summary_for(
    session: Session, scope: WorkspaceScope, customer_id: UUID
) -> CustomerSummary:
    orders = WorkspaceRepository(session, Order, scope)
    quotes = WorkspaceRepository(session, Quote, scope)
    order_count = await session.scalar(
        select(func.count())
        .select_from(Order)
        .where(orders.predicate(), Order.customer_id == customer_id, Order.status != "cancelled")
    )
    quote_count = await session.scalar(
        select(func.count())
        .select_from(Quote)
        .where(
            quotes.predicate(),
            Quote.customer_id == customer_id,
            Quote.status.in_(("draft", "pending_approval", "approved", "sent")),
        )
    )
    balance = None
    currency = None
    if scope.can("billing.read"):
        balance = await BillingService(session, scope).customer_balance(customer_id)
        currency = (await get_settings_row(session, scope)).default_currency
    open_conversations = 0
    if scope.can("pi.read"):
        conversations = WorkspaceRepository(session, PiConversation, scope)
        open_conversations = int(
            await session.scalar(
                select(func.count())
                .select_from(PiConversation)
                .where(
                    conversations.predicate(),
                    PiConversation.customer_id == customer_id,
                    PiConversation.status == "open",
                )
            )
            or 0
        )
    return CustomerSummary(
        order_count=int(order_count or 0),
        open_quote_count=int(quote_count or 0),
        outstanding_balance=balance,
        currency=currency,
        open_conversations=open_conversations,
    )


@router.get("", response_model=Page[CustomerView])
async def customers(
    scope: Read,
    session: Session,
    pagination: Paging,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Literal["active", "archived"] | None, Query(alias="status")] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[CustomerView]:
    return await CustomerService(session, scope).search(pagination, search, status_filter, tag)


@router.post("", response_model=CustomerView, status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerCreate, scope: Write, session: Session) -> CustomerView:
    customer = await CustomerService(session, scope).create(data)
    await session.commit()
    return CustomerView.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerDetail)
async def customer(customer_id: UUID, scope: Read, session: Session) -> CustomerDetail:
    row = await CustomerService(session, scope).get(customer_id)
    summary = await summary_for(session, scope, customer_id)
    return CustomerDetail(**CustomerView.model_validate(row).model_dump(), summary=summary)


@router.patch("/{customer_id}", response_model=CustomerView)
async def update_customer(
    customer_id: UUID, data: CustomerUpdate, scope: Write, session: Session
) -> CustomerView:
    row = await CustomerService(session, scope).update(customer_id, data)
    await session.commit()
    return CustomerView.model_validate(row)


@router.put("/{customer_id}/status", response_model=CustomerView)
async def set_customer_status(
    customer_id: UUID, data: CustomerStatusUpdate, scope: Write, session: Session
) -> CustomerView:
    row = await CustomerService(session, scope).set_status(customer_id, data.status)
    await session.commit()
    return CustomerView.model_validate(row)


@router.get("/{customer_id}/notes", response_model=Page[NoteView])
async def notes(
    customer_id: UUID, scope: Read, session: Session, pagination: Paging
) -> Page[NoteView]:
    return await CustomerService(session, scope).notes_page(customer_id, pagination)


@router.post("/{customer_id}/notes", response_model=NoteView, status_code=status.HTTP_201_CREATED)
async def add_note(customer_id: UUID, data: NoteCreate, scope: Write, session: Session) -> NoteView:
    note = await CustomerService(session, scope).add_note(customer_id, data.body)
    await session.commit()
    return NoteView.model_validate(note)


@router.get("/{customer_id}/activities", response_model=Page[ActivityView])
async def activities(
    customer_id: UUID, scope: Read, session: Session, pagination: Paging
) -> Page[ActivityView]:
    return await CustomerService(session, scope).activities_page(customer_id, pagination)
