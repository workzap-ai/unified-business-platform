from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditEvent
from app.modules.billing.models import Invoice, Payment
from app.modules.billing.service import BillingService
from app.modules.business_settings.service import get_settings_row
from app.modules.customers.models import Customer
from app.modules.hr.models import Employee
from app.modules.inventory.service import InventoryService
from app.modules.orders.models import Order
from app.modules.products.service import ProductService
from app.modules.quotes.models import Quote
from app.shared.money import quantize
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


class MonthPoint(BaseModel):
    month: str  # YYYY-MM
    invoiced: Decimal
    collected: Decimal


class RevenueReport(BaseModel):
    currency: str
    months: list[MonthPoint]
    total_invoiced: Decimal
    total_collected: Decimal


class StatusCount(BaseModel):
    status: str
    count: int
    value: Decimal


class DayPoint(BaseModel):
    day: date
    count: int
    value: Decimal


class OrdersReport(BaseModel):
    currency: str
    by_status: list[StatusCount]
    by_day: list[DayPoint]
    average_order_value: Decimal


class TopCustomer(BaseModel):
    customer_id: UUID
    name: str
    invoiced: Decimal
    orders: int


class CustomersReport(BaseModel):
    currency: str
    total: int
    new_by_month: list[tuple[str, int]]
    top: list[TopCustomer]


class QuotesReport(BaseModel):
    currency: str
    by_status: list[StatusCount]
    conversion_rate: Decimal | None
    open_value: Decimal


class InventoryReport(BaseModel):
    low_stock_count: int
    stock_value: Decimal
    currency: str


class MetricBlock(BaseModel):
    value: Decimal | int
    previous: Decimal | int | None = None
    currency: str | None = None
    detail: str | None = None


class ActivityItem(BaseModel):
    id: UUID
    action: str
    actor_label: str
    entity_type: str | None
    entity_id: UUID | None
    created_at: datetime


class Overview(BaseModel):
    currency: str
    revenue: MetricBlock | None
    orders: MetricBlock | None
    customers: MetricBlock | None
    pending_payments: MetricBlock | None
    outstanding_invoices: MetricBlock | None
    inventory_alerts: MetricBlock | None
    quotes: MetricBlock | None
    employees: MetricBlock | None
    installed_products: list[dict[str, Any]]
    recent_activity: list[ActivityItem]


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def months_back(count: int) -> list[date]:
    today = date.today().replace(day=1)
    result = []
    year, month = today.year, today.month
    for _ in range(count):
        result.append(date(year, month, 1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(result))


class ReportService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.invoices = WorkspaceRepository(session, Invoice, scope)
        self.payments = WorkspaceRepository(session, Payment, scope)
        self.orders = WorkspaceRepository(session, Order, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)
        self.quotes = WorkspaceRepository(session, Quote, scope)
        self.employees = WorkspaceRepository(session, Employee, scope)

    async def currency(self) -> str:
        return (await get_settings_row(self.session, self.scope)).default_currency

    async def revenue(self, months: int = 12) -> RevenueReport:
        currency = await self.currency()
        buckets = months_back(max(1, min(months, 24)))
        start = buckets[0]
        invoiced_month = func.date_trunc("month", Invoice.issue_date)
        invoiced = await self.session.execute(
            select(invoiced_month, func.sum(Invoice.total))
            .where(
                self.invoices.predicate(),
                Invoice.currency == currency,
                Invoice.status.in_(("issued", "partially_paid", "paid")),
                Invoice.issue_date >= start,
            )
            .group_by(invoiced_month)
        )
        collected_month = func.date_trunc("month", Payment.received_on)
        collected = await self.session.execute(
            select(collected_month, func.sum(Payment.amount))
            .where(
                self.payments.predicate(),
                Payment.currency == currency,
                Payment.received_on >= start,
            )
            .group_by(collected_month)
        )
        inv = {
            month_key(m.date() if isinstance(m, datetime) else m): Decimal(v) for m, v in invoiced
        }
        col = {
            month_key(m.date() if isinstance(m, datetime) else m): Decimal(v) for m, v in collected
        }
        points = [
            MonthPoint(
                month=month_key(b),
                invoiced=quantize(inv.get(month_key(b), Decimal(0))),
                collected=quantize(col.get(month_key(b), Decimal(0))),
            )
            for b in buckets
        ]
        return RevenueReport(
            currency=currency,
            months=points,
            total_invoiced=quantize(sum((p.invoiced for p in points), Decimal(0))),
            total_collected=quantize(sum((p.collected for p in points), Decimal(0))),
        )

    async def orders_report(self, days: int = 30) -> OrdersReport:
        currency = await self.currency()
        days = max(1, min(days, 366))
        since = datetime.now(UTC) - timedelta(days=days)
        status_rows = await self.session.execute(
            select(Order.status, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(self.orders.predicate(), Order.currency == currency, Order.created_at >= since)
            .group_by(Order.status)
        )
        by_status = [
            StatusCount(status=s, count=int(n), value=quantize(Decimal(v)))
            for s, n, v in status_rows
        ]
        day = cast(Order.created_at, Date)
        day_rows = await self.session.execute(
            select(day, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(
                self.orders.predicate(),
                Order.currency == currency,
                Order.created_at >= since,
                Order.status != "cancelled",
            )
            .group_by(day)
            .order_by(day)
        )
        by_day = [DayPoint(day=d, count=int(n), value=quantize(Decimal(v))) for d, n, v in day_rows]
        counted = [s for s in by_status if s.status not in ("cancelled", "draft")]
        total_count = sum(s.count for s in counted)
        total_value = sum((s.value for s in counted), Decimal(0))
        return OrdersReport(
            currency=currency,
            by_status=by_status,
            by_day=by_day,
            average_order_value=quantize(total_value / total_count)
            if total_count
            else Decimal("0.00"),
        )

    async def customers_report(self) -> CustomersReport:
        currency = await self.currency()
        total = await self.session.scalar(
            select(func.count()).select_from(Customer).where(self.customers.predicate())
        )
        start = months_back(12)[0]
        created_month = func.date_trunc("month", Customer.created_at)
        month_rows = await self.session.execute(
            select(created_month, func.count())
            .where(self.customers.predicate(), Customer.created_at >= start)
            .group_by(created_month)
        )
        counts = {month_key(m.date()): int(n) for m, n in month_rows}
        top_rows = await self.session.execute(
            select(
                Customer.id,
                Customer.name,
                func.sum(Invoice.total),
                func.count(func.distinct(Invoice.order_id)),
            )
            .join(
                Invoice,
                (Invoice.customer_id == Customer.id)
                & (Invoice.tenant_id == Customer.tenant_id)
                & (Invoice.environment_id == Customer.environment_id),
            )
            .where(
                self.customers.predicate(),
                Invoice.currency == currency,
                Invoice.status.in_(("issued", "partially_paid", "paid")),
            )
            .group_by(Customer.id, Customer.name)
            .order_by(func.sum(Invoice.total).desc())
            .limit(10)
        )
        return CustomersReport(
            currency=currency,
            total=int(total or 0),
            new_by_month=[(month_key(m), counts.get(month_key(m), 0)) for m in months_back(12)],
            top=[
                TopCustomer(customer_id=i, name=n, invoiced=quantize(Decimal(v)), orders=int(o))
                for i, n, v, o in top_rows
            ],
        )

    async def quotes_report(self) -> QuotesReport:
        currency = await self.currency()
        rows = await self.session.execute(
            select(Quote.status, func.count(), func.coalesce(func.sum(Quote.total), 0))
            .where(self.quotes.predicate(), Quote.currency == currency)
            .group_by(Quote.status)
        )
        by_status = [
            StatusCount(status=s, count=int(n), value=quantize(Decimal(v))) for s, n, v in rows
        ]
        counts = {s.status: s.count for s in by_status}
        decided = counts.get("accepted", 0) + counts.get("rejected", 0) + counts.get("expired", 0)
        rate = (
            (Decimal(counts.get("accepted", 0)) / Decimal(decided)).quantize(Decimal("0.0001"))
            if decided
            else None
        )
        open_value = sum(
            (
                s.value
                for s in by_status
                if s.status in ("draft", "pending_approval", "approved", "sent")
            ),
            Decimal(0),
        )
        return QuotesReport(
            currency=currency,
            by_status=by_status,
            conversion_rate=rate,
            open_value=quantize(open_value),
        )

    async def inventory_report(self) -> InventoryReport:
        from app.modules.catalog.models import CatalogVariant
        from app.modules.inventory.models import StockLevel

        currency = await self.currency()
        inventory = InventoryService(self.session, self.scope)
        value = await self.session.scalar(
            select(func.coalesce(func.sum(StockLevel.on_hand * CatalogVariant.price), 0))
            .select_from(StockLevel)
            .join(
                CatalogVariant,
                (CatalogVariant.id == StockLevel.variant_id)
                & (CatalogVariant.tenant_id == StockLevel.tenant_id)
                & (CatalogVariant.environment_id == StockLevel.environment_id),
            )
            .where(inventory.levels.predicate(), CatalogVariant.currency == currency)
        )
        return InventoryReport(
            low_stock_count=await inventory.low_stock_count(),
            stock_value=quantize(Decimal(value or 0)),
            currency=currency,
        )

    async def overview(self) -> Overview:
        s = self.scope
        currency = await self.currency()
        month_start = date.today().replace(day=1)
        prev_start = (month_start - timedelta(days=1)).replace(day=1)
        revenue = orders = customers = pending = outstanding = alerts = quotes = employees = None
        if s.can("billing.read"):

            async def collected(since: date, until: date) -> Decimal:
                value = await self.session.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        self.payments.predicate(),
                        Payment.currency == currency,
                        Payment.received_on >= since,
                        Payment.received_on < until,
                    )
                )
                return quantize(Decimal(value or 0))

            revenue = MetricBlock(
                value=await collected(month_start, date.today() + timedelta(days=1)),
                previous=await collected(prev_start, month_start),
                currency=currency,
                detail="Payments received this month",
            )
            summary = await BillingService(self.session, s).summary()
            pending = MetricBlock(
                value=summary.outstanding,
                currency=currency,
                detail=f"{summary.overdue_count} overdue",
            )
            open_count = await self.session.scalar(
                select(func.count())
                .select_from(Invoice)
                .where(self.invoices.predicate(), Invoice.status.in_(("issued", "partially_paid")))
            )
            outstanding = MetricBlock(value=int(open_count or 0), detail="Issued and unpaid")
        if s.can("orders.read"):
            this_month = await self.session.scalar(
                select(func.count())
                .select_from(Order)
                .where(
                    self.orders.predicate(),
                    Order.status != "cancelled",
                    Order.status != "draft",
                    Order.created_at >= datetime.combine(month_start, datetime.min.time(), UTC),
                )
            )
            open_orders = await self.session.scalar(
                select(func.count())
                .select_from(Order)
                .where(
                    self.orders.predicate(),
                    Order.status.in_(("confirmed", "processing", "shipped")),
                )
            )
            orders = MetricBlock(value=int(this_month or 0), detail=f"{int(open_orders or 0)} open")
        if s.can("customers.read"):
            total = await self.session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(self.customers.predicate(), Customer.status == "active")
            )
            new = await self.session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(
                    self.customers.predicate(),
                    Customer.created_at >= datetime.combine(month_start, datetime.min.time(), UTC),
                )
            )
            customers = MetricBlock(value=int(total or 0), detail=f"{int(new or 0)} new this month")
        if s.can("inventory.read"):
            alerts = MetricBlock(
                value=await InventoryService(self.session, s).low_stock_count(),
                detail="Items at or below threshold",
            )
        if s.can("quotes.read"):
            row = (
                await self.session.execute(
                    select(func.count(), func.coalesce(func.sum(Quote.total), 0)).where(
                        self.quotes.predicate(),
                        Quote.currency == currency,
                        Quote.status.in_(("draft", "pending_approval", "approved", "sent")),
                    )
                )
            ).one()
            quotes = MetricBlock(
                value=int(row[0] or 0),
                currency=currency,
                detail=f"{currency} {quantize(Decimal(row[1] or 0)):,.2f} open",
            )
        if s.can("hr.read"):
            active = await self.session.scalar(
                select(func.count())
                .select_from(Employee)
                .where(self.employees.predicate(), Employee.status == "active")
            )
            employees = MetricBlock(value=int(active or 0), detail="Active employees")
        products = [
            {"key": p.key, "name": p.name, "enabled": p.environment_enabled}
            for p in await ProductService(self.session, s).states()
            if p.tenant_status == "installed"
        ]
        activity: list[ActivityItem] = []
        if s.can("audit.read"):
            rows = await self.session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.tenant_id == s.tenant_id,
                    or_(
                        AuditEvent.environment_id == s.environment_id,
                        AuditEvent.environment_id.is_(None),
                    ),
                    AuditEvent.outcome == "success",
                    ~AuditEvent.action.startswith("auth."),
                )
                .order_by(AuditEvent.created_at.desc())
                .limit(12)
            )
            activity = [
                ActivityItem(
                    id=r.id,
                    action=r.action,
                    actor_label=r.actor_label,
                    entity_type=r.entity_type,
                    entity_id=r.entity_id,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        return Overview(
            currency=currency,
            revenue=revenue,
            orders=orders,
            customers=customers,
            pending_payments=pending,
            outstanding_invoices=outstanding,
            inventory_alerts=alerts,
            quotes=quotes,
            employees=employees,
            installed_products=products,
            recent_activity=activity,
        )
