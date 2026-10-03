"""More read-only tools for Agent Beta: customer 360, global search, what-if scenarios and
workspace activity.

Same rules as the rest of the agent: every section is gated by the permission for its
area, rows come from the caller's workspace repositories (and the PI inbox visibility
rule for WhatsApp), and results use the ``results`` / analytics shapes the web panel
already renders, so no section can show data the user couldn't open in the app.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from pydantic import Field
from sqlalchemy import func, or_, select

from app.core.pagination import Pagination
from app.modules.audit.models import AuditEvent
from app.modules.billing.models import Invoice
from app.modules.catalog.models import CatalogProduct
from app.modules.customers.models import Customer, CustomerActivity, CustomerNote
from app.modules.hr.service import HRService
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation
from app.modules.pi.service import PiService
from app.modules.quotes.models import Quote
from app.modules.reports.service import ReportService
from app.modules.sales.models import SalesLead
from app.modules.workspace_agent.analytics import Analytics
from app.modules.workspace_agent.forecast import next_months
from app.modules.workspace_agent.schemas import StrictInput
from app.modules.workspace_agent.service import AgentService, json_safe
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.models import WorkspaceRow
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

OPEN_QUOTES = ("draft", "pending_approval", "approved", "sent")
OPEN_INVOICES = ("issued", "partially_paid")


class Customer360Input(StrictInput):
    customer_id: UUID | None = None
    name: str = Field(default="", max_length=120)


class SearchInput(StrictInput):
    query: str = Field(min_length=2, max_length=100)


class WhatIfInput(StrictInput):
    revenue_change_pct: float = Field(default=0, ge=-90, le=500)
    expense_change_pct: float = Field(default=0, ge=-90, le=500)
    new_monthly_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    new_monthly_income: float = Field(default=0, ge=0, le=1_000_000_000)
    one_time_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    months: int = Field(default=6, ge=3, le=12)
    label: str = Field(default="Scenario", max_length=80)


class ActivityInput(StrictInput):
    days: int = Field(default=7, ge=1, le=30)
    search: str = Field(default="", max_length=60)


def block(
    area: str, title: str, route: str, items: list[dict[str, Any]], total: int, **extra: Any
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json_safe(
            {
                "area": area,
                "title": title,
                "specialist": extra.pop("specialist", "crm"),
                "route": route,
                "items": items,
                "total": total,
                "page": 1,
                "page_size": max(len(items), 1),
                **extra,
            }
        ),
    )


class Toolkit:
    def __init__(self, agent: AgentService) -> None:
        self.agent, self.session, self.scope = agent, agent.session, agent.scope

    def repo(self, model: type[WorkspaceRow]) -> WorkspaceRepository[Any]:
        return WorkspaceRepository(self.session, model, self.scope)

    async def rows(self, query: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in (await self.session.execute(query)).mappings()]

    async def count(self, model: type[WorkspaceRow], *conditions: Any) -> int:
        query = select(func.count()).select_from(model).where(self.repo(model).predicate())
        return int(await self.session.scalar(query.where(*conditions)) or 0)

    # -- customer 360 -------------------------------------------------------------------

    async def customer_360(self, data: Customer360Input) -> dict[str, Any]:
        self.scope.require("customers.read")
        customers = self.repo(Customer)
        if data.customer_id is not None:
            customer = await customers.get(data.customer_id)
        else:
            if not data.name.strip():
                raise BusinessRuleViolation("AGENT_INPUT", "Give a customer name or id.")
            matches = list(
                await self.session.scalars(
                    customers.select()
                    .where(
                        or_(
                            Customer.name.ilike(like_pattern(data.name.strip())),
                            Customer.company.ilike(like_pattern(data.name.strip())),
                        )
                    )
                    .order_by(Customer.name)
                    .limit(6)
                )
            )
            if len(matches) != 1:
                return {
                    "ambiguous": True,
                    "message": "No customer matched."
                    if not matches
                    else "Several customers match; ask which one.",
                    "results": [
                        block(
                            "customer_matches",
                            "Matching customers",
                            "/customers",
                            [{"id": c.id, "name": c.name, "company": c.company} for c in matches],
                            len(matches),
                        )
                    ],
                }
            customer = matches[0]
        cid = customer.id
        sections: list[dict[str, Any]] = [
            block(
                "customer_profile",
                f"Customer · {customer.name}",
                "/customers",
                [
                    {
                        "id": customer.id,
                        "name": customer.name,
                        "company": customer.company,
                        "status": customer.status,
                        "source": customer.source,
                        "tags": ", ".join(customer.tags or []),
                        "last_contacted_at": customer.last_contacted_at,
                        "customer_since": customer.created_at,
                    }
                ],
                1,
            )
        ]
        facts: dict[str, Any] = {"customer": customer.name, "id": str(cid)}
        if self.scope.can("orders.read"):
            q: Any = (
                self.repo(Order)
                .select()
                .with_only_columns(
                    Order.id, Order.number, Order.status, Order.total, Order.currency
                )
                .where(Order.customer_id == cid)
                .order_by(Order.created_at.desc())
                .limit(8)
            )
            total = await self.count(Order, Order.customer_id == cid, Order.status != "cancelled")
            sections.append(
                block(
                    "customer_orders",
                    "Recent orders",
                    "/orders",
                    await self.rows(q),
                    total,
                    specialist="operations",
                )
            )
            facts["orders"] = total
        if self.scope.can("quotes.read"):
            q = (
                self.repo(Quote)
                .select()
                .with_only_columns(
                    Quote.id,
                    Quote.number,
                    Quote.status,
                    Quote.total,
                    Quote.currency,
                    Quote.valid_until,
                )
                .where(Quote.customer_id == cid, Quote.status.in_(OPEN_QUOTES))
                .order_by(Quote.created_at.desc())
                .limit(8)
            )
            items = await self.rows(q)
            sections.append(block("customer_quotes", "Open quotes", "/quotes", items, len(items)))
            facts["open_quotes"] = len(items)
        if self.scope.can("billing.read"):
            q = (
                self.repo(Invoice)
                .select()
                .with_only_columns(
                    Invoice.id,
                    Invoice.number,
                    Invoice.status,
                    Invoice.total,
                    Invoice.amount_paid,
                    Invoice.currency,
                    Invoice.due_date,
                )
                .where(Invoice.customer_id == cid, Invoice.status.in_(OPEN_INVOICES))
                .order_by(Invoice.due_date)
                .limit(8)
            )
            items = await self.rows(q)
            for item in items:
                item["outstanding"] = item["total"] - item["amount_paid"]
                item["overdue"] = bool(
                    item["due_date"] and item["due_date"] < datetime.now(UTC).date()
                )
            sections.append(
                block(
                    "customer_invoices",
                    "Unpaid invoices",
                    "/billing",
                    items,
                    len(items),
                    specialist="finance",
                )
            )
            by_currency: dict[str, float] = {}
            for item in items:
                by_currency[item["currency"]] = by_currency.get(item["currency"], 0) + float(
                    item["outstanding"]
                )
            facts["outstanding_by_currency"] = by_currency
            facts["overdue_invoices"] = sum(1 for i in items if i["overdue"])
        if self.scope.can("sales.read"):
            q = (
                self.repo(SalesLead)
                .select()
                .with_only_columns(
                    SalesLead.id,
                    SalesLead.title,
                    SalesLead.stage,
                    SalesLead.estimated_value,
                    SalesLead.currency,
                )
                .where(SalesLead.customer_id == cid)
                .order_by(SalesLead.created_at.desc())
                .limit(8)
            )
            items = await self.rows(q)
            sections.append(block("customer_leads", "Leads", "/sales", items, len(items)))
            facts["leads"] = [f"{i['title']} ({i['stage']})" for i in items]
        notes = await self.rows(
            self.repo(CustomerNote)
            .select()
            .with_only_columns(
                CustomerNote.created_at, CustomerNote.author_label, CustomerNote.body
            )
            .where(CustomerNote.customer_id == cid)
            .order_by(CustomerNote.created_at.desc())
            .limit(5)
        )
        for note in notes:
            note["body"] = note["body"][:300]
        timeline = await self.rows(
            self.repo(CustomerActivity)
            .select()
            .with_only_columns(
                CustomerActivity.created_at,
                CustomerActivity.kind,
                CustomerActivity.summary,
                CustomerActivity.actor_label,
            )
            .where(CustomerActivity.customer_id == cid)
            .order_by(CustomerActivity.created_at.desc())
            .limit(10)
        )
        sections.append(
            block(
                "customer_notes", "Notes", "/customers", notes, len(notes), untrusted_content=True
            )
        )
        sections.append(
            block("customer_timeline", "Timeline", "/customers", timeline, len(timeline))
        )
        if self.scope.can("pi.read"):
            try:
                pi = PiService(self.session, self.scope)
                await pi.require("pi.read")
                conversations = list(
                    await self.session.scalars(
                        pi.conversations.select()
                        .where(PiConversation.customer_id == cid)
                        .order_by(PiConversation.last_message_at.desc())
                        .limit(3)
                    )
                )
                items = [
                    {
                        "conversation_id": c.id,
                        "status": c.status,
                        "mode": c.mode,
                        "unread": c.unread_count,
                        "last_message_at": c.last_message_at,
                        "stored_summary": (c.summary or "")[:400],
                        "last_message": c.last_message_preview,
                    }
                    for c in conversations
                ]
                sections.append(
                    block(
                        "customer_whatsapp",
                        "WhatsApp conversations",
                        "/pi/inbox",
                        items,
                        len(items),
                        untrusted_content=True,
                    )
                )
            except (BusinessRuleViolation, PermissionDenied):
                pass
        return {"facts": facts, "results": sections}

    # -- global search ------------------------------------------------------------------

    async def search(self, data: SearchInput) -> dict[str, Any]:
        text = data.query.strip()
        pattern = like_pattern(text)
        results: list[dict[str, Any]] = []

        async def add(
            permission: str,
            model: Any,
            area: str,
            title: str,
            route: str,
            columns: list[Any],
            *where: Any,
        ) -> None:
            if not self.scope.can(permission):
                return
            q = self.repo(model).select().where(or_(*where))
            total = int(
                await self.session.scalar(select(func.count()).select_from(q.subquery())) or 0
            )
            if total:
                items = await self.rows(
                    q.with_only_columns(*columns).order_by(model.created_at.desc()).limit(5)
                )
                results.append(block(area, title, route, items, total))

        await add(
            "customers.read",
            Customer,
            "customers",
            "Customers",
            "/customers",
            [Customer.id, Customer.name, Customer.company, Customer.email, Customer.phone],
            Customer.name.ilike(pattern),
            Customer.company.ilike(pattern),
            Customer.email.ilike(pattern),
            Customer.phone.ilike(pattern),
        )
        await add(
            "sales.read",
            SalesLead,
            "sales",
            "Leads",
            "/sales",
            [
                SalesLead.id,
                SalesLead.title,
                SalesLead.stage,
                SalesLead.estimated_value,
                SalesLead.currency,
            ],
            SalesLead.title.ilike(pattern),
        )
        await add(
            "quotes.read",
            Quote,
            "quotes",
            "Quotes",
            "/quotes",
            [Quote.id, Quote.number, Quote.status, Quote.total, Quote.currency],
            Quote.number.ilike(pattern),
        )
        await add(
            "orders.read",
            Order,
            "orders",
            "Orders",
            "/orders",
            [Order.id, Order.number, Order.status, Order.total, Order.currency],
            Order.number.ilike(pattern),
        )
        await add(
            "billing.read",
            Invoice,
            "billing",
            "Invoices",
            "/billing",
            [
                Invoice.id,
                Invoice.number,
                Invoice.status,
                Invoice.total,
                Invoice.currency,
                Invoice.due_date,
            ],
            Invoice.number.ilike(pattern),
        )
        await add(
            "catalog.read",
            CatalogProduct,
            "catalog",
            "Products and services",
            "/catalog",
            [
                CatalogProduct.id,
                CatalogProduct.name,
                CatalogProduct.offering_type,
                CatalogProduct.status,
            ],
            CatalogProduct.name.ilike(pattern),
        )
        if self.scope.can("hr.read"):
            page = await HRService(self.session, self.scope).search(
                Pagination(page=1, page_size=5), text
            )
            if page.total:
                items = [
                    {
                        k: v
                        for k, v in e.model_dump(mode="json").items()
                        if k in {"id", "full_name", "job_title", "status", "email"}
                    }
                    for e in page.items
                ]
                results.append(
                    block("employees", "Employees", "/hr", items, page.total, specialist="hr")
                )
        return {
            "query": text,
            "found_in": [r["area"] for r in results],
            "results": results,
        }

    # -- what-if ------------------------------------------------------------------------

    async def what_if(self, data: WhatIfInput) -> dict[str, Any]:
        """Project monthly net cash from the last three complete months' averages."""
        self.scope.require("billing.read")
        analytics = Analytics(self.agent, 12)
        analytics.currency = await ReportService(self.session, self.scope).currency()
        report = await ReportService(self.session, self.scope).revenue(12)
        collected = [float(p.collected) for p in report.months][:-1]  # complete months
        expenses: list[float] = []
        if self.scope.can("finance.read"):
            await analytics.expenses()
            expenses = list(analytics.facts["expenses"]["per_month"])[:-1]
        base_in = sum(collected[-3:]) / 3 if collected else 0.0
        base_out = sum(expenses[-3:]) / 3 if expenses else 0.0
        if not base_in and not base_out:
            raise BusinessRuleViolation(
                "AGENT_INPUT", "There isn't enough recorded income or spending to project yet."
            )
        income = base_in * (1 + data.revenue_change_pct / 100) + data.new_monthly_income
        costs = base_out * (1 + data.expense_change_pct / 100) + data.new_monthly_cost
        months = next_months(analytics.buckets[-2], data.months)  # starts this month
        baseline_cum = scenario_cum = 0.0
        rows: list[dict[str, Any]] = []
        for i, month in enumerate(months):
            baseline_cum += base_in - base_out
            scenario_cum += income - costs - (data.one_time_cost if i == 0 else 0)
            rows.append(
                {
                    "period": month,
                    "baseline": round(baseline_cum, 2),
                    "scenario": round(scenario_cum, 2),
                }
            )
        monthly_delta = (income - costs) - (base_in - base_out)
        payback = (
            round(data.one_time_cost / (income - costs), 1)
            if data.one_time_cost and income - costs > 0
            else None
        )
        money = analytics.currency
        analytics.charts = []
        analytics.kpis = []
        analytics.chart(
            "what_if",
            f"What if: {data.label}",
            rows,
            [
                {"key": "baseline", "label": "Today's pace"},
                {"key": "scenario", "label": data.label, "dashed": True},
            ],
            kind="line",
            unit="currency",
            description=(
                "Cumulative net cash from the last three complete months' averages "
                f"(income {money} {base_in:,.0f}/month, spending {money} {base_out:,.0f}/month). "
                "A projection, not a forecast: it assumes those averages hold."
            ),
        )
        analytics.kpi(
            "scenario_monthly",
            "Net cash per month (scenario)",
            income - costs,
            "currency",
            previous=base_in - base_out,
            compare="vs today's pace",
        )
        analytics.kpi(
            "scenario_total",
            f"Cash after {data.months} months",
            scenario_cum,
            "currency",
            previous=baseline_cum,
            compare="vs today's pace",
        )
        if payback is not None:
            analytics.kpi(
                "payback", "Months to recover the one-time cost", payback, "count", good="down"
            )
        notes = []
        if not expenses:
            notes.append("Spending isn't included: your role can't read finance.")
        return cast(
            dict[str, Any],
            json_safe(
                {
                    "area": "analytics",
                    "topic": "what_if",
                    "currency": money,
                    "months": data.months,
                    "kpis": analytics.kpis,
                    "charts": analytics.charts,
                    "tables": [],
                    "facts": {
                        "assumptions": data.model_dump(),
                        "base_monthly_income": round(base_in, 2),
                        "base_monthly_spend": round(base_out, 2),
                        "scenario_monthly_income": round(income, 2),
                        "scenario_monthly_spend": round(costs, 2),
                        "monthly_change_vs_today": round(monthly_delta, 2),
                        "cumulative_after_months": round(scenario_cum, 2),
                        "baseline_after_months": round(baseline_cum, 2),
                        "payback_months": payback,
                        "goes_negative_in_month": next(
                            (r["period"] for r in rows if r["scenario"] < 0), None
                        ),
                    },
                    "notes": notes,
                    "checked_areas": ["revenue"] + (["expenses"] if expenses else []),
                    "generated_at": datetime.now(UTC),
                }
            ),
        )

    # -- activity -----------------------------------------------------------------------

    async def activity(self, data: ActivityInput) -> dict[str, Any]:
        self.scope.require("audit.read")
        since = datetime.now(UTC) - timedelta(days=data.days)
        base = select(AuditEvent).where(
            AuditEvent.tenant_id == self.scope.tenant_id,
            or_(
                AuditEvent.environment_id == self.scope.environment_id,
                AuditEvent.environment_id.is_(None),
            ),
            AuditEvent.created_at >= since,
            ~AuditEvent.action.startswith("auth."),
        )
        if data.search:
            pattern = like_pattern(data.search)
            base = base.where(
                or_(AuditEvent.action.ilike(pattern), AuditEvent.actor_label.ilike(pattern))
            )
        events = base.subquery()
        by_actor = (
            await self.session.execute(
                select(events.c.actor_label, func.count())
                .group_by(events.c.actor_label)
                .order_by(func.count().desc())
                .limit(8)
            )
        ).all()
        by_action = (
            await self.session.execute(
                select(events.c.action, func.count())
                .group_by(events.c.action)
                .order_by(func.count().desc())
                .limit(10)
            )
        ).all()
        recent = list(
            await self.session.scalars(base.order_by(AuditEvent.created_at.desc()).limit(20))
        )
        total = sum(n for _, n in by_actor)
        return {
            "facts": {
                "days": data.days,
                "events": total,
                "by_person": {a: n for a, n in by_actor},
                "by_action": {a: n for a, n in by_action},
                "failures_or_denied": sum(1 for e in recent if e.outcome != "success"),
            },
            "results": [
                block(
                    "activity",
                    f"Workspace activity · last {data.days} days",
                    "/workspace-agent",
                    [
                        {
                            "at": e.created_at,
                            "who": e.actor_label,
                            "action": e.action,
                            "record": e.entity_type,
                            "outcome": e.outcome,
                        }
                        for e in recent
                    ],
                    total,
                    specialist="operations",
                )
            ],
        }
