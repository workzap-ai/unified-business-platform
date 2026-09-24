from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.billing.schemas import (
    BillingSummary,
    InvoiceAction,
    InvoiceCreate,
    InvoiceDetail,
    InvoiceListItem,
    PaymentCreate,
    PaymentView,
)
from app.modules.billing.service import BillingService
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/billing", tags=["billing"])
Read = Annotated[WorkspaceScope, Depends(require("billing.read"))]
Write = Annotated[WorkspaceScope, Depends(require("billing.write"))]
Paging = Annotated[Pagination, Query()]
InvoiceStatus = Literal["draft", "issued", "partially_paid", "paid", "void"]


@router.get("/summary", response_model=BillingSummary)
async def summary(scope: Read, session: Session) -> BillingSummary:
    return await BillingService(session, scope).summary()


@router.get("/invoices", response_model=Page[InvoiceListItem])
async def invoices(
    scope: Read,
    session: Session,
    pagination: Paging,
    status_filter: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    customer_id: UUID | None = None,
    overdue: bool = False,
    search: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[InvoiceListItem]:
    return await BillingService(session, scope).search(
        pagination, status_filter, customer_id, overdue, search
    )


@router.post("/invoices", response_model=InvoiceDetail, status_code=status.HTTP_201_CREATED)
async def create_invoice(data: InvoiceCreate, scope: Write, session: Session) -> InvoiceDetail:
    service = BillingService(session, scope)
    invoice = await service.create(data)
    await session.commit()
    return await service.detail(invoice.id)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
async def invoice(invoice_id: UUID, scope: Read, session: Session) -> InvoiceDetail:
    return await BillingService(session, scope).detail(invoice_id)


@router.post("/invoices/{invoice_id}/actions", response_model=InvoiceDetail)
async def act(
    invoice_id: UUID, data: InvoiceAction, scope: Write, session: Session
) -> InvoiceDetail:
    service = BillingService(session, scope)
    await service.act(invoice_id, data.action)
    await session.commit()
    return await service.detail(invoice_id)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentView,
    status_code=status.HTTP_201_CREATED,
)
async def pay(invoice_id: UUID, data: PaymentCreate, scope: Write, session: Session) -> PaymentView:
    payment = await BillingService(session, scope).record_payment(invoice_id, data)
    await session.commit()
    return PaymentView.model_validate(payment)


@router.get("/payments", response_model=Page[PaymentView])
async def payments(scope: Read, session: Session, pagination: Paging) -> Page[PaymentView]:
    return await BillingService(session, scope).payments_page(pagination)
