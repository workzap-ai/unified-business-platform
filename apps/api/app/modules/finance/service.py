from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.billing.models import Invoice, Payment
from app.modules.business_settings.service import get_settings_row
from app.modules.finance.models import Expense
from app.shared.errors import BusinessRuleViolation
from app.shared.money import quantize
from app.shared.scope import WorkspaceScope
from app.shared.sequences import next_number
from app.shared.workspace_repository import WorkspaceRepository, like_pattern, to_page

Category = Literal[
    "rent",
    "payroll",
    "utilities",
    "inventory",
    "marketing",
    "software",
    "travel",
    "taxes",
    "professional_services",
    "other",
]


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ]
    vendor: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] = ""
    amount: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    incurred_on: date


class ExpenseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    category: str
    description: str
    vendor: str
    amount: Decimal
    currency: str
    incurred_on: date
    status: str
    recorded_by_label: str
    created_at: datetime


class AgingBucket(BaseModel):
    bucket: str
    amount: Decimal
    count: int


class CategoryTotal(BaseModel):
    category: str
    amount: Decimal


class FinanceSummary(BaseModel):
    currency: str
    period_start: date
    period_end: date
    cash_in: Decimal
    cash_out: Decimal
    net_cash: Decimal
    receivables: Decimal
    aging: list[AgingBucket]
    expenses_by_category: list[CategoryTotal]


class FinanceService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.expenses = WorkspaceRepository(session, Expense, scope)
        self.invoices = WorkspaceRepository(session, Invoice, scope)
        self.payments = WorkspaceRepository(session, Payment, scope)

    async def list_expenses(
        self, page: Pagination, category: str | None = None, search: str | None = None
    ) -> Page[ExpenseView]:
        statement = self.expenses.select()
        if category:
            statement = statement.where(Expense.category == category)
        if search:
            pattern = like_pattern(search.strip())
            statement = statement.where(
                Expense.description.ilike(pattern) | Expense.vendor.ilike(pattern)
            )
        statement = statement.order_by(Expense.incurred_on.desc(), Expense.id)
        rows, total = await self.expenses.page(statement, page)
        return to_page(ExpenseView, rows, total, page)

    async def create_expense(self, data: ExpenseCreate) -> Expense:
        self.scope.require("finance.write")
        if data.incurred_on > date.today():
            raise BusinessRuleViolation("FUTURE_DATE", "Expenses cannot be dated in the future")
        settings = await get_settings_row(self.session, self.scope)
        expense = await self.expenses.add(
            self.expenses.new(
                number=await next_number(self.session, self.scope, "expense"),
                currency=settings.default_currency,
                recorded_by_label=self.scope.actor_label[:80],
                **data.model_dump(),
            )
        )
        await record(
            self.session,
            "expense.recorded",
            scope=self.scope,
            entity_type="expense",
            entity_id=expense.id,
            details={"amount": str(expense.amount), "category": expense.category},
        )
        return expense

    async def void_expense(self, expense_id: UUID) -> Expense:
        self.scope.require("finance.write")
        expense = await self.expenses.get(expense_id, for_update=True)
        if expense.status == "void":
            raise BusinessRuleViolation("ALREADY_VOID", "This expense is already void")
        expense.status, expense.voided_at = "void", datetime.now(UTC)
        await self.session.flush()
        await record(
            self.session,
            "expense.voided",
            scope=self.scope,
            entity_type="expense",
            entity_id=expense.id,
        )
        return expense

    async def summary(self, start: date, end: date) -> FinanceSummary:
        if end < start or (end - start).days > 366:
            raise BusinessRuleViolation("INVALID_PERIOD", "Choose a period of up to one year")
        settings = await get_settings_row(self.session, self.scope)
        currency = settings.default_currency
        cash_in = await self.session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                self.payments.predicate(),
                Payment.currency == currency,
                Payment.received_on.between(start, end),
            )
        )
        expense_filter = (
            self.expenses.predicate(),
            Expense.status == "recorded",
            Expense.currency == currency,
            Expense.incurred_on.between(start, end),
        )
        cash_out = await self.session.scalar(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(*expense_filter)
        )
        categories = await self.session.execute(
            select(Expense.category, func.sum(Expense.amount))
            .where(*expense_filter)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
        today = date.today()
        days = func.coalesce(today - Invoice.due_date, 0)
        bucket = case(
            (Invoice.due_date.is_(None), "current"),
            (Invoice.due_date >= today, "current"),
            (days <= 30, "1-30"),
            (days <= 60, "31-60"),
            (days <= 90, "61-90"),
            else_="90+",
        )
        aging_rows = await self.session.execute(
            select(bucket, func.sum(Invoice.total - Invoice.amount_paid), func.count())
            .where(
                self.invoices.predicate(),
                Invoice.currency == currency,
                Invoice.status.in_(("issued", "partially_paid")),
            )
            .group_by(bucket)
        )
        aging_map = {b: (Decimal(a or 0), int(n)) for b, a, n in aging_rows}
        aging = [
            AgingBucket(
                bucket=b,
                amount=quantize(aging_map.get(b, (Decimal(0), 0))[0]),
                count=aging_map.get(b, (Decimal(0), 0))[1],
            )
            for b in ("current", "1-30", "31-60", "61-90", "90+")
        ]
        cash_in_d, cash_out_d = quantize(Decimal(cash_in or 0)), quantize(Decimal(cash_out or 0))
        return FinanceSummary(
            currency=currency,
            period_start=start,
            period_end=end,
            cash_in=cash_in_d,
            cash_out=cash_out_d,
            net_cash=quantize(cash_in_d - cash_out_d),
            receivables=quantize(sum((a.amount for a in aging), Decimal(0))),
            aging=aging,
            expenses_by_category=[
                CategoryTotal(category=c, amount=quantize(Decimal(a))) for c, a in categories
            ],
        )
