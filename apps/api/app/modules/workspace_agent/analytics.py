"""Exact business analytics, forecasts and chart specs for Agent Beta.

Each section runs only when the caller may read that area, and every figure is a
database aggregate over rows the caller can already see. Money series use the
business's default currency; other currencies are counted and called out, never
converted or mixed. Forecasts say which method and how much history they used.

The output has one shape for chat, the Insights tab and the specialist agents:
``kpis`` (stat tiles), ``charts`` (series the web app draws), ``tables`` and
``facts`` (compact numbers for the language model).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast

from pydantic import Field
from sqlalchemy import Date, func, select
from sqlalchemy import cast as sql_cast

from app.modules.billing.models import Invoice, Payment
from app.modules.catalog.models import CatalogVariant
from app.modules.finance.models import Expense
from app.modules.inventory.models import StockLevel, StockMovement
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service import PiService
from app.modules.reports.service import ReportService, month_key, month_of, months_back
from app.modules.sales.models import SalesLead
from app.modules.workspace_agent.forecast import change, holt, next_months, trend_direction
from app.modules.workspace_agent.schemas import StrictInput
from app.modules.workspace_agent.service import AgentService, json_safe
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.models import WorkspaceRow
from app.shared.workspace_repository import WorkspaceRepository

Topic = Literal[
    "overview",
    "revenue",
    "cashflow",
    "sales",
    "orders",
    "customers",
    "expenses",
    "inventory",
    "whatsapp",
    "report",
]
TOPICS: dict[str, tuple[str, ...]] = {
    "overview": ("revenue", "orders", "sales", "expenses"),
    "report": (
        "revenue",
        "cashflow",
        "sales",
        "orders",
        "customers",
        "expenses",
        "inventory",
        "whatsapp",
    ),
}


class AnalyticsInput(StrictInput):
    topic: Topic = "overview"
    months: int = Field(default=12, ge=3, le=24)


# Standard stage odds for a weighted pipeline (stated, never presented as measured).
STAGE_ODDS = {"new": 0.1, "qualified": 0.3, "proposal": 0.6}
OPEN_INVOICE = ("issued", "partially_paid")
HORIZON = 3


def _month(value: Any) -> str:
    return month_key(value.date() if isinstance(value, datetime) else value)


def _num(value: Any) -> float:
    return float(Decimal(value or 0))


class Analytics:
    def __init__(self, agent: AgentService, months: int = 12) -> None:
        self.agent, self.session, self.scope = agent, agent.session, agent.scope
        self.months = max(3, min(months, 24))
        self.buckets = [month_key(m) for m in months_back(self.months)]
        self.start = months_back(self.months)[0]
        self.kpis: list[dict[str, Any]] = []
        self.charts: list[dict[str, Any]] = []
        self.tables: list[dict[str, Any]] = []
        self.facts: dict[str, Any] = {}
        self.notes: list[str] = []
        self.checked: list[str] = []
        self.currency = "USD"
        # The current month is partial: compare it with the same days of last month and
        # forecast from complete months only.
        self.today = date.today()
        month_start = self.today.replace(day=1)
        self.prev_start = (month_start - timedelta(days=1)).replace(day=1)
        self.prev_end = min(
            self.prev_start + timedelta(days=self.today.day), month_start
        )  # exclusive
        self.compare = f"vs first {self.today.day} days of last month"

    def repo(self, model: type[WorkspaceRow]) -> WorkspaceRepository[Any]:
        return WorkspaceRepository(self.session, model, self.scope)

    # -- builders -----------------------------------------------------------------------

    def kpi(
        self,
        key: str,
        label: str,
        value: float,
        unit: str,
        *,
        previous: float | None = None,
        good: str = "up",
        detail: str = "",
        compare: str | None = None,
    ) -> None:
        self.kpis.append(
            {
                "key": key,
                "label": label,
                "value": round(value, 2),
                "unit": unit,
                "currency": self.currency if unit == "currency" else None,
                "previous": None if previous is None else round(previous, 2),
                "change_pct": None if previous is None else change(value, previous),
                "good": good,
                "detail": detail,
                "compare": compare,
            }
        )

    def chart(
        self,
        id: str,
        title: str,
        data: list[dict[str, Any]],
        series: list[dict[str, Any]],
        *,
        kind: str = "bar",
        unit: str = "count",
        description: str = "",
        x_label: str = "Month",
        stacked: bool = False,
    ) -> None:
        self.charts.append(
            {
                "id": id,
                "title": title,
                "description": description,
                "kind": kind,
                "x_key": "period",
                "x_label": x_label,
                "series": series,
                "data": data,
                "unit": unit,
                "currency": self.currency if unit == "currency" else None,
                "stacked": stacked,
            }
        )

    def forecast_chart(
        self, id: str, title: str, history: list[float], label: str, unit: str
    ) -> dict[str, Any] | None:
        """Complete months as the actual line, then a dashed forecast for this month and
        the next two. The partial current month never feeds the model."""
        complete, buckets, so_far = history[:-1], self.buckets[:-1], history[-1]
        first = next((i for i, v in enumerate(complete) if v), len(complete))
        first = min(first, max(len(complete) - 3, 0))  # months before the business began
        complete, buckets = complete[first:], buckets[first:]
        result = holt(complete, HORIZON)
        data: list[dict[str, Any]] = [
            {"period": p, "actual": round(v, 2), "forecast": None}
            for p, v in zip(buckets, complete, strict=True)
        ]
        money = f"{self.currency} " if unit == "currency" else ""
        if result is None:
            data.append({"period": self.buckets[-1], "actual": round(so_far, 2)})
            self.chart(
                id,
                title,
                data,
                [{"key": "actual", "label": label}],
                kind="line",
                unit=unit,
                description=("Not enough history for a forecast yet (needs 4+ complete months)."),
            )
            return None
        periods = [self.buckets[-1], *next_months(self.buckets[-1], HORIZON - 1)]
        if data:
            data[-1]["forecast"] = data[-1]["actual"]
        for period, value in zip(periods, result.values, strict=True):
            data.append({"period": period, "actual": None, "forecast": value})
        self.chart(
            id,
            title,
            data,
            [
                {"key": "actual", "label": label},
                {"key": "forecast", "label": "Forecast", "dashed": True},
            ],
            kind="line",
            unit=unit,
            description=(
                f"This month: {money}{result.values[0]:,.0f} expected "
                f"(likely {money}{result.low[0]:,.0f}–{result.high[0]:,.0f}; "
                f"so far {money}{so_far:,.0f}). "
                f"{result.method} on {result.history_points} complete months."
                + (" " + " ".join(result.notes) if result.notes else "")
            ),
        )
        return {
            "next": result.values,
            "low": result.low,
            "high": result.high,
            "method": result.method,
            "history_points": result.history_points,
            "periods": periods,
            "current_month_so_far": round(so_far, 2),
        }

    async def previous_slice(
        self, model: Any, column: Any, amount: Any = None, *conditions: Any
    ) -> float:
        """Sum (or count) over the same first days of last month."""
        timestamp = column.type.python_type is datetime
        start: date | datetime = self.prev_start
        end: date | datetime = self.prev_end
        if timestamp:
            start = datetime.combine(self.prev_start, datetime.min.time(), UTC)
            end = datetime.combine(self.prev_end, datetime.min.time(), UTC)
        value = func.coalesce(func.sum(amount), 0) if amount is not None else func.count()
        query = select(value).select_from(model).where(self.repo(model).predicate())
        query = query.where(column >= start, column < end, *conditions)
        return _num(await self.session.scalar(query))

    async def note_currencies(self, label: str, model: Any, *conditions: Any) -> None:
        others = await self.other_currency(model, *conditions)
        if others:
            self.notes.append(f"{others} {label} in other currencies are not in these totals.")

    async def other_currency(self, model: Any, *conditions: Any) -> int:
        query = select(func.count()).select_from(model).where(self.repo(model).predicate())
        query = query.where(model.currency != self.currency, *conditions)
        return int(await self.session.scalar(query) or 0)

    # -- sections -----------------------------------------------------------------------

    async def revenue(self) -> None:
        if not self.scope.can("billing.read"):
            return
        self.checked.append("revenue")
        report = await ReportService(self.session, self.scope).revenue(self.months)
        invoiced = [_num(p.invoiced) for p in report.months]
        collected = [_num(p.collected) for p in report.months]
        self.chart(
            "revenue_monthly",
            "Invoiced vs collected",
            [
                {"period": p.month, "invoiced": _num(p.invoiced), "collected": _num(p.collected)}
                for p in report.months
            ],
            [{"key": "invoiced", "label": "Invoiced"}, {"key": "collected", "label": "Collected"}],
            unit="currency",
            description="Issued invoices and payments received per month.",
        )
        forecast = self.forecast_chart(
            "revenue_forecast", "Collections forecast", collected, "Collected", "currency"
        )
        self.prev_collected = await self.previous_slice(
            Payment, Payment.received_on, Payment.amount, Payment.currency == self.currency
        )
        self.kpi(
            "collected_month",
            "Collected this month",
            collected[-1],
            "currency",
            previous=self.prev_collected,
            compare=self.compare,
        )
        outstanding, overdue = await self._receivables()
        self.kpi(
            "receivables",
            "Unpaid invoices",
            outstanding,
            "currency",
            good="down",
            detail=f"{self.currency} {overdue:,.0f} overdue",
        )
        await self.note_currencies("invoice(s)", Invoice, Invoice.issue_date >= self.start)
        self.facts["revenue"] = {
            "currency": self.currency,
            "months": self.buckets,
            "invoiced": invoiced,
            "collected": collected,
            "collection_rate_pct": (
                round(sum(collected) / sum(invoiced) * 100, 1) if sum(invoiced) else None
            ),
            "trend_3m_pct": trend_direction(collected[:-1]),
            "current_month_so_far": collected[-1],
            "same_days_last_month": self.prev_collected,
            "outstanding": outstanding,
            "overdue": overdue,
            "forecast": forecast,
        }

    async def _receivables(self) -> tuple[float, float]:
        due = Invoice.total - Invoice.amount_paid
        base = select(func.coalesce(func.sum(due), 0)).where(
            self.repo(Invoice).predicate(),
            Invoice.currency == self.currency,
            Invoice.status.in_(OPEN_INVOICE),
        )
        total = _num(await self.session.scalar(base))
        overdue = _num(await self.session.scalar(base.where(Invoice.due_date < date.today())))
        return total, overdue

    async def cashflow(self) -> None:
        if not self.scope.can("billing.read"):
            return
        self.checked.append("cashflow")
        today = date.today()
        due = Invoice.total - Invoice.amount_paid
        rows = (
            await self.session.execute(
                select(Invoice.due_date, due).where(
                    self.repo(Invoice).predicate(),
                    Invoice.currency == self.currency,
                    Invoice.status.in_(OPEN_INVOICE),
                )
            )
        ).all()
        buckets = {"Overdue": 0.0, "0–30 days": 0.0, "31–60 days": 0.0, "61–90 days": 0.0}
        buckets |= {"Later / no date": 0.0}
        for due_date, amount in rows:
            days = (due_date - today).days if due_date else None
            label = (
                "Later / no date"
                if days is None or days > 90
                else "Overdue"
                if days < 0
                else "0–30 days"
                if days <= 30
                else "31–60 days"
                if days <= 60
                else "61–90 days"
            )
            buckets[label] += _num(amount)
        self.chart(
            "cash_due",
            "Money to collect, by due date",
            [{"period": k, "amount": round(v, 2)} for k, v in buckets.items()],
            [{"key": "amount", "label": "Unpaid"}],
            unit="currency",
            x_label="Due",
            description="Unpaid balances on issued invoices.",
        )
        await self.note_currencies("unpaid invoice(s)", Invoice, Invoice.status.in_(OPEN_INVOICE))
        self.facts["cashflow_due"] = {k: round(v, 2) for k, v in buckets.items()}

    async def sales(self) -> None:
        if not self.scope.can("sales.read"):
            return
        self.checked.append("sales")
        stage_rows = (
            await self.session.execute(
                select(
                    SalesLead.stage,
                    func.count(),
                    func.coalesce(func.sum(SalesLead.estimated_value), 0),
                )
                .where(self.repo(SalesLead).predicate(), SalesLead.currency == self.currency)
                .group_by(SalesLead.stage)
            )
        ).all()
        stages = {s: (int(n), _num(v)) for s, n, v in stage_rows}
        await self.note_currencies("lead(s)", SalesLead)
        order = ("new", "qualified", "proposal", "won", "lost")
        self.chart(
            "pipeline_stages",
            "Pipeline value by stage",
            [{"period": s.title(), "value": stages.get(s, (0, 0.0))[1]} for s in order],
            [{"key": "value", "label": "Estimated value"}],
            unit="currency",
            x_label="Stage",
        )
        open_value = sum(stages.get(s, (0, 0.0))[1] for s in STAGE_ODDS)
        weighted = sum(stages.get(s, (0, 0.0))[1] * p for s, p in STAGE_ODDS.items())
        won, lost = stages.get("won", (0, 0.0))[0], stages.get("lost", (0, 0.0))[0]
        win_rate = won / (won + lost) if won + lost else None
        self.kpi(
            "pipeline_weighted",
            "Weighted pipeline",
            weighted,
            "currency",
            detail=f"of {self.currency} {open_value:,.0f} open (standard stage odds)",
        )
        if win_rate is not None:
            self.kpi(
                "win_rate",
                "Win rate",
                win_rate * 100,
                "percent",
                detail=f"{won} won of {won + lost} closed",
            )
        created = month_of(SalesLead.created_at)
        monthly = {
            _month(m): int(n)
            for m, n in (
                await self.session.execute(
                    select(created, func.count())
                    .where(
                        self.repo(SalesLead).predicate(),
                        SalesLead.created_at
                        >= datetime.combine(self.start, datetime.min.time(), UTC),
                    )
                    .group_by(created)
                )
            ).all()
        }
        leads = [float(monthly.get(b, 0)) for b in self.buckets]
        self.chart(
            "leads_monthly",
            "New leads per month",
            [{"period": b, "leads": int(v)} for b, v in zip(self.buckets, leads, strict=True)],
            [{"key": "leads", "label": "Leads"}],
        )
        quotes = None
        if self.scope.can("quotes.read"):
            report = await ReportService(self.session, self.scope).quotes_report()
            quotes = {
                "conversion_pct": (
                    float(report.conversion_rate * 100) if report.conversion_rate else None
                ),
                "open_value": _num(report.open_value),
            }
            if report.conversion_rate is not None:
                self.kpi(
                    "quote_conversion",
                    "Quote acceptance",
                    float(report.conversion_rate * 100),
                    "percent",
                    detail=f"{self.currency} {_num(report.open_value):,.0f} in open quotes",
                )
        self.facts["sales"] = {
            "by_stage": {s: {"count": n, "value": v} for s, (n, v) in stages.items()},
            "open_value": open_value,
            "weighted_value": round(weighted, 2),
            "stage_odds": STAGE_ODDS,
            "win_rate_pct": None if win_rate is None else round(win_rate * 100, 1),
            "closed_leads": won + lost,
            "historical_expected_value": (
                None if win_rate is None else round(open_value * win_rate, 2)
            ),
            "new_leads_per_month": leads,
            "quotes": quotes,
        }

    async def orders(self) -> None:
        if not self.scope.can("orders.read"):
            return
        self.checked.append("orders")
        created = month_of(Order.created_at)
        rows = (
            await self.session.execute(
                select(created, func.count(), func.coalesce(func.sum(Order.total), 0))
                .where(
                    self.repo(Order).predicate(),
                    Order.currency == self.currency,
                    Order.status.notin_(("draft", "cancelled")),
                    Order.created_at >= datetime.combine(self.start, datetime.min.time(), UTC),
                )
                .group_by(created)
            )
        ).all()
        by_month = {_month(m): (int(n), _num(v)) for m, n, v in rows}
        counts = [float(by_month.get(b, (0, 0.0))[0]) for b in self.buckets]
        values = [by_month.get(b, (0, 0.0))[1] for b in self.buckets]
        others = await self.other_currency(
            Order,
            Order.status.notin_(("draft", "cancelled")),
            Order.created_at >= datetime.combine(self.start, datetime.min.time(), UTC),
        )
        if others:
            self.notes.append(f"{others} order(s) in other currencies are not in these totals.")
        forecast = self.forecast_chart(
            "orders_forecast", "Orders per month", counts, "Orders", "count"
        )
        total_n, total_v = sum(counts), sum(values)
        self.kpi(
            "orders_month",
            "Orders this month",
            counts[-1],
            "count",
            previous=await self.previous_slice(
                Order,
                Order.created_at,
                None,
                Order.currency == self.currency,
                Order.status.notin_(("draft", "cancelled")),
            ),
            compare=self.compare,
        )
        if total_n:
            self.kpi(
                "aov",
                "Average order value",
                total_v / total_n,
                "currency",
                detail=f"over {self.months} months",
            )
        self.facts["orders"] = {
            "count_per_month": counts,
            "value_per_month": values,
            "average_order_value": round(total_v / total_n, 2) if total_n else None,
            "trend_3m_pct": trend_direction(counts[:-1]),
            "forecast": forecast,
        }

    async def customers(self) -> None:
        if not self.scope.can("customers.read"):
            return
        self.checked.append("customers")
        report = await ReportService(self.session, self.scope).customers_report()
        new = dict(report.new_by_month)
        self.chart(
            "customers_new",
            "New customers per month",
            [{"period": b, "customers": new.get(b, 0)} for b in self.buckets[-12:]],
            [{"key": "customers", "label": "New customers"}],
        )
        self.kpi(
            "customers_total",
            "Customers",
            float(report.total),
            "count",
            detail=f"{new.get(self.buckets[-1], 0)} new this month",
        )
        top: list[dict[str, Any]] = []
        if self.scope.can("billing.read") and report.top:
            top = [
                {"customer": t.name, "invoiced": _num(t.invoiced), "orders": t.orders}
                for t in report.top[:8]
            ]
            total = sum(t["invoiced"] for t in top) or 1
            share = round(top[0]["invoiced"] / total * 100, 1)
            self.tables.append(
                {
                    "title": "Top customers by invoiced value",
                    "columns": ["customer", "invoiced"]
                    + (["orders"] if any(t["orders"] for t in top) else []),
                    "rows": top,
                    "note": f"The top customer is {share}% of the top-{len(top)} total.",
                }
            )
        self.facts["customers"] = {
            "total": report.total,
            "new_per_month": [new.get(b, 0) for b in self.buckets[-12:]],
            "top": top,
        }

    async def expenses(self) -> None:
        if not self.scope.can("finance.read"):
            return
        self.checked.append("expenses")
        month = month_of(Expense.incurred_on)
        rows = (
            await self.session.execute(
                select(month, Expense.category, func.coalesce(func.sum(Expense.amount), 0))
                .where(
                    self.repo(Expense).predicate(),
                    Expense.currency == self.currency,
                    Expense.status == "recorded",
                    Expense.incurred_on >= self.start,
                )
                .group_by(month, Expense.category)
            )
        ).all()
        totals: dict[str, float] = {}
        cells: dict[tuple[str, str], float] = {}
        for m, category, amount in rows:
            totals[category] = totals.get(category, 0.0) + _num(amount)
            cells[(_month(m), category)] = cells.get((_month(m), category), 0.0) + _num(amount)
        others = await self.other_currency(
            Expense, Expense.status == "recorded", Expense.incurred_on >= self.start
        )
        if others:
            self.notes.append(f"{others} expense(s) in other currencies are not in these totals.")
        top = sorted(totals, key=lambda c: -totals[c])[:4]
        series = [{"key": c, "label": c.replace("_", " ").title()} for c in top]
        if len(totals) > 4:
            series.append({"key": "other", "label": "Other"})
        data = []
        spend = []
        for b in self.buckets:
            row: dict[str, Any] = {"period": b}
            for c in top:
                row[c] = round(cells.get((b, c), 0.0), 2)
            if len(totals) > 4:
                row["other"] = round(
                    sum(v for (mm, c), v in cells.items() if mm == b and c not in top), 2
                )
            data.append(row)
            spend.append(sum(v for (mm, _), v in cells.items() if mm == b))
        self.chart(
            "expenses_monthly",
            "Expenses by category",
            data,
            series,
            unit="currency",
            stacked=True,
            description="Recorded expenses per month (top categories).",
        )
        prev_spend = await self.previous_slice(
            Expense,
            Expense.incurred_on,
            Expense.amount,
            Expense.currency == self.currency,
            Expense.status == "recorded",
        )
        self.kpi(
            "expenses_month",
            "Spent this month",
            spend[-1],
            "currency",
            previous=prev_spend,
            good="down",
            compare=self.compare,
        )
        net = None
        revenue = self.facts.get("revenue")
        if revenue:
            net = [round(c - s, 2) for c, s in zip(revenue["collected"], spend, strict=True)]
            self.chart(
                "net_cash",
                "Net cash (collected − expenses)",
                [{"period": b, "net": v} for b, v in zip(self.buckets, net, strict=True)],
                [{"key": "net", "label": "Net cash"}],
                unit="currency",
                description="A cash view, not accounting profit (no accruals or tax).",
            )
            self.kpi(
                "net_month",
                "Net cash this month",
                net[-1],
                "currency",
                previous=self.prev_collected - prev_spend,
                compare=self.compare,
            )
        self.facts["expenses"] = {
            "per_month": [round(v, 2) for v in spend],
            "by_category": {c: round(v, 2) for c, v in totals.items()},
            "net_cash_per_month": net,
            "trend_3m_pct": trend_direction(spend[:-1]),
        }

    async def inventory(self) -> None:
        if not self.scope.can("inventory.read"):
            return
        self.checked.append("inventory")
        since = datetime.now(UTC) - timedelta(days=30)
        sold = {
            v: -int(q)
            for v, q in (
                await self.session.execute(
                    select(StockMovement.variant_id, func.sum(StockMovement.quantity))
                    .where(
                        self.repo(StockMovement).predicate(),
                        StockMovement.kind == "sale",
                        StockMovement.created_at >= since,
                    )
                    .group_by(StockMovement.variant_id)
                )
            ).all()
            if q and q < 0
        }
        if not sold:
            self.facts["inventory"] = {"runway": [], "note": "No sales movements in 30 days."}
            return
        available = (
            await self.session.execute(
                select(
                    StockLevel.variant_id,
                    func.sum(StockLevel.on_hand - StockLevel.reserved),
                    CatalogVariant.name,
                    CatalogVariant.sku,
                )
                .join(
                    CatalogVariant,
                    (CatalogVariant.id == StockLevel.variant_id)
                    & (CatalogVariant.tenant_id == StockLevel.tenant_id)
                    & (CatalogVariant.environment_id == StockLevel.environment_id),
                )
                .where(self.repo(StockLevel).predicate(), StockLevel.variant_id.in_(list(sold)))
                .group_by(StockLevel.variant_id, CatalogVariant.name, CatalogVariant.sku)
            )
        ).all()
        runway: list[dict[str, Any]] = []
        for variant, left, name, sku in available:
            per_day = sold[variant] / 30
            days = max(int(left or 0), 0) / per_day if per_day else None
            runway.append(
                {
                    "item": f"{name} ({sku})",
                    "available": int(left or 0),
                    "sold_30d": sold[variant],
                    "days_left": None if days is None else round(days, 1),
                }
            )
        runway.sort(key=lambda r: r["days_left"] if r["days_left"] is not None else 1e9)
        soon = [r for r in runway if r["days_left"] is not None and r["days_left"] <= 14]
        self.kpi(
            "stockouts_14d",
            "Items running out in 14 days",
            float(len(soon)),
            "count",
            good="down",
            detail="at the last 30 days' sales pace",
        )
        if runway:
            self.tables.append(
                {
                    "title": "Stock runway (fastest-selling first to run out)",
                    "columns": ["item", "available", "sold_30d", "days_left"],
                    "rows": runway[:10],
                    "note": "Days left = available ÷ average daily sales over 30 days.",
                }
            )
        self.facts["inventory"] = {"runway": runway[:15], "running_out_14d": len(soon)}

    async def whatsapp(self) -> None:
        if not self.scope.can("pi.read"):
            return
        pi = PiService(self.session, self.scope)
        try:
            await pi.require("pi.read")
        except (BusinessRuleViolation, PermissionDenied):
            return
        self.checked.append("whatsapp")
        start = date.today() - timedelta(days=29)
        day = sql_cast(PiMessage.created_at, Date)
        visible = pi.conversations.select().with_only_columns(PiConversation.id)
        rows = (
            await self.session.execute(
                select(day, PiMessage.direction, func.count())
                .where(
                    self.repo(PiMessage).predicate(),
                    PiMessage.conversation_id.in_(visible),
                    PiMessage.created_at >= datetime.combine(start, datetime.min.time(), UTC),
                )
                .group_by(day, PiMessage.direction)
            )
        ).all()
        counts = {(d, k): int(n) for d, k, n in rows}
        days = [start + timedelta(days=i) for i in range(30)]
        inbound = [counts.get((d, "inbound"), 0) for d in days]
        outbound = [counts.get((d, "outbound"), 0) for d in days]
        data = [
            {"period": d.strftime("%d %b"), "inbound": i, "outbound": o}
            for d, i, o in zip(days, inbound, outbound, strict=True)
        ]
        self.chart(
            "whatsapp_daily",
            "WhatsApp messages per day",
            data,
            [
                {"key": "inbound", "label": "From customers"},
                {"key": "outbound", "label": "Replies"},
            ],
            kind="area",
            x_label="Day",
            description="Last 30 days, conversations you can see.",
        )
        self.kpi(
            "whatsapp_inbound",
            "Customer messages (30 days)",
            float(sum(inbound)),
            "count",
            detail=f"{sum(outbound)} replies sent",
        )
        self.facts["whatsapp"] = {
            "inbound_30d": sum(inbound),
            "outbound_30d": sum(outbound),
            "inbound_last_7d": sum(inbound[-7:]),
            "inbound_prev_7d": sum(inbound[-14:-7]),
        }

    # -- entry point --------------------------------------------------------------------

    async def run(self, topic: str) -> dict[str, Any]:
        self.currency = await ReportService(self.session, self.scope).currency()
        sections = TOPICS.get(topic, (topic,))
        # Revenue first: expenses reuse its collections for the net-cash view.
        if "expenses" in sections and "revenue" not in sections:
            sections = ("revenue", *sections)
        for name in sections:
            await getattr(self, name)()
        return cast(
            dict[str, Any],
            json_safe(
                {
                    "area": "analytics",
                    "topic": topic,
                    "currency": self.currency,
                    "months": self.months,
                    "kpis": self.kpis,
                    "charts": self.charts,
                    "tables": self.tables,
                    "facts": self.facts,
                    "notes": self.notes,
                    "checked_areas": self.checked,
                    "generated_at": datetime.now(UTC),
                }
            ),
        )
