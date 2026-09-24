from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.modules.access.dependencies import Session, require
from app.modules.hr.service import Headcount, HRService
from app.modules.reports.service import (
    CustomersReport,
    InventoryReport,
    OrdersReport,
    Overview,
    QuotesReport,
    ReportService,
    RevenueReport,
)
from app.shared.scope import WorkspaceScope

router = APIRouter(tags=["reports"])
Reports = Annotated[WorkspaceScope, Depends(require("reports.read"))]
OverviewRead = Annotated[WorkspaceScope, Depends(require("overview.read"))]


@router.get("/overview", response_model=Overview)
async def overview(scope: OverviewRead, session: Session) -> Overview:
    return await ReportService(session, scope).overview()


@router.get("/reports/revenue", response_model=RevenueReport)
async def revenue(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "billing.read"))],
    session: Session,
    months: Annotated[int, Query(ge=1, le=24)] = 12,
) -> RevenueReport:
    return await ReportService(session, scope).revenue(months)


@router.get("/reports/orders", response_model=OrdersReport)
async def orders(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "orders.read"))],
    session: Session,
    days: Annotated[int, Query(ge=1, le=366)] = 30,
) -> OrdersReport:
    return await ReportService(session, scope).orders_report(days)


@router.get("/reports/customers", response_model=CustomersReport)
async def customers(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "customers.read"))],
    session: Session,
) -> CustomersReport:
    return await ReportService(session, scope).customers_report()


@router.get("/reports/quotes", response_model=QuotesReport)
async def quotes(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "quotes.read"))],
    session: Session,
) -> QuotesReport:
    return await ReportService(session, scope).quotes_report()


@router.get("/reports/inventory", response_model=InventoryReport)
async def inventory(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "inventory.read"))],
    session: Session,
) -> InventoryReport:
    return await ReportService(session, scope).inventory_report()


@router.get("/reports/employees", response_model=Headcount)
async def employees(
    scope: Annotated[WorkspaceScope, Depends(require("reports.read", "hr.read"))],
    session: Session,
) -> Headcount:
    return await HRService(session, scope).headcount()
