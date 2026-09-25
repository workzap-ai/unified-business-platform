from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Session, require
from app.modules.finance.service import (
    Category,
    ExpenseCreate,
    ExpenseView,
    FinanceService,
    FinanceSummary,
)
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/finance", tags=["finance"])
Read = Annotated[WorkspaceScope, Depends(require("finance.read"))]
Write = Annotated[WorkspaceScope, Depends(require("finance.write"))]
Paging = Annotated[Pagination, Depends()]


@router.get("/summary", response_model=FinanceSummary)
async def summary(
    scope: Read,
    session: Session,
    start: date | None = None,
    end: date | None = None,
) -> FinanceSummary:
    end = end or date.today()
    start = start or (end - timedelta(days=29))
    return await FinanceService(session, scope).summary(start, end)


@router.get("/expenses", response_model=Page[ExpenseView])
async def expenses(
    scope: Read,
    session: Session,
    pagination: Paging,
    category: Category | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[ExpenseView]:
    return await FinanceService(session, scope).list_expenses(pagination, category, search)


@router.post("/expenses", response_model=ExpenseView, status_code=status.HTTP_201_CREATED)
async def create_expense(data: ExpenseCreate, scope: Write, session: Session) -> ExpenseView:
    row = await FinanceService(session, scope).create_expense(data)
    await session.commit()
    return ExpenseView.model_validate(row)


@router.post("/expenses/{expense_id}/void", response_model=ExpenseView)
async def void_expense(expense_id: UUID, scope: Write, session: Session) -> ExpenseView:
    row = await FinanceService(session, scope).void_expense(expense_id)
    await session.commit()
    return ExpenseView.model_validate(row)
