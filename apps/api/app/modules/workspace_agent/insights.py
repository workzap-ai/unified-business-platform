"""Read-only aggregates, WhatsApp inbox digests and workspace monitoring for Agent Beta.

Every figure is an exact database aggregate over rows the caller may already read; nothing
here writes, sends messages or widens visibility. WhatsApp access reuses the PI inbox
record scope, so members without ``pi.inbox.all`` only see conversations assigned to them.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from pydantic import Field
from sqlalchemy import func, select

from app.modules.billing.models import Invoice
from app.modules.customers.models import Customer
from app.modules.integrations.models import IntegrationConnection
from app.modules.inventory.models import StockLevel
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation, PiHandoff, PiMessage
from app.modules.pi.service import ACTIVE_HANDOFF, PiService
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead
from app.modules.workspace_agent.models import WorkspaceTask
from app.modules.workspace_agent.schemas import StrictInput
from app.modules.workspace_agent.service import AgentService, json_safe
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.models import WorkspaceRow
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

OPEN_LEAD_STAGES = ("new", "qualified", "proposal")
OPEN_INVOICE_STATUSES = ("issued", "partially_paid")
ACTIVE_ORDER_STATUSES = ("confirmed", "processing")
UNHEALTHY_CONNECTIONS = ("degraded", "expired", "revoked", "error")
MESSAGE_CHARS = 500
CRM_PERMISSIONS = ("customers.read", "sales.read", "quotes.read", "orders.read", "billing.read")


class WhatsAppInput(StrictInput):
    conversation_id: UUID | None = None
    search: str = Field(default="", max_length=100)
    unread_only: bool = False
    days: int = Field(default=7, ge=1, le=90)


def safe(value: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json_safe(value))


def metric(
    label: str, count: int, amount: Any = None, currency: str | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {"metric": label, "count": int(count or 0)}
    if amount is not None:
        row["amount"], row["currency"] = amount, currency
    return row


TITLES = {
    "crm_customers": ("CRM · Customers", "customers"),
    "crm_pipeline": ("CRM · Sales pipeline", "leads"),
    "crm_quotes": ("CRM · Quotes", "quotes"),
    "crm_orders": ("CRM · Orders", "orders"),
    "crm_receivables": ("CRM · Receivables", "invoices"),
}


def block(
    area: str, specialist: str, route: str, items: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    title, noun = TITLES[area]
    if not items:
        items = [metric(f"No {noun} yet", 0)]
    return safe(
        {
            "area": area,
            "title": title,
            "specialist": specialist,
            "route": route,
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": max(len(items), 1),
            "count_unit": extra.pop("count_unit", "metrics"),
            "exact": True,
            **extra,
        }
    )


class Insights:
    def __init__(self, agent: AgentService) -> None:
        self.agent, self.session, self.scope = agent, agent.session, agent.scope

    def repo(self, model: type[WorkspaceRow]) -> WorkspaceRepository[Any]:
        return WorkspaceRepository(self.session, model, self.scope)

    async def grouped(
        self, model: Any, column: Any, amount: Any = None, *conditions: Any
    ) -> list[Any]:
        columns = [column, func.count()]
        if amount is not None:
            columns += [model.currency, func.coalesce(func.sum(amount), 0)]
        query = (
            select(*columns)
            .where(self.repo(model).predicate(), *conditions)
            .group_by(*([column, model.currency] if amount is not None else [column]))
            .order_by(column)
        )
        return list((await self.session.execute(query)).all())

    async def count(self, model: type[WorkspaceRow], *conditions: Any) -> int:
        query = select(func.count()).select_from(model).where(self.repo(model).predicate())
        return int(await self.session.scalar(query.where(*conditions)) or 0)

    # CRM ------------------------------------------------------------------------------

    async def crm(self) -> list[dict[str, Any]]:
        """Exact CRM aggregates for permitted areas; each currency stays separate."""
        blocks: list[dict[str, Any]] = []
        now = datetime.now(UTC)
        if self.scope.can("customers.read"):
            rows = await self.grouped(Customer, Customer.status)
            items = [metric(f"Customers · {status}", n) for status, n in rows]
            items.append(
                metric(
                    "New customers · last 30 days",
                    await self.count(Customer, Customer.created_at >= now - timedelta(days=30)),
                )
            )
            items.append(
                metric(
                    "Active customers not contacted in 30 days",
                    await self.count(
                        Customer,
                        Customer.status == "active",
                        (Customer.last_contacted_at.is_(None))
                        | (Customer.last_contacted_at < now - timedelta(days=30)),
                    ),
                )
            )
            by_source = await self.grouped(Customer, Customer.source)
            items += [metric(f"Customers from {source}", n) for source, n in by_source]
            blocks.append(block("crm_customers", "crm", "/customers", items))
        if self.scope.can("sales.read"):
            rows = await self.grouped(SalesLead, SalesLead.stage, SalesLead.estimated_value)
            items = [
                metric(f"Leads · {stage}", n, total, currency) for stage, n, currency, total in rows
            ]
            items.append(
                metric(
                    "Open leads without an update in 14 days",
                    await self.count(
                        SalesLead,
                        SalesLead.stage.in_(OPEN_LEAD_STAGES),
                        SalesLead.updated_at < now - timedelta(days=14),
                    ),
                )
            )
            blocks.append(block("crm_pipeline", "crm", "/sales", items))
        if self.scope.can("quotes.read"):
            rows = await self.grouped(Quote, Quote.status, Quote.total)
            items = [metric(f"Quotes · {s}", n, total, currency) for s, n, currency, total in rows]
            blocks.append(block("crm_quotes", "crm", "/quotes", items))
        if self.scope.can("orders.read"):
            rows = await self.grouped(Order, Order.status, Order.total)
            items = [metric(f"Orders · {s}", n, total, currency) for s, n, currency, total in rows]
            blocks.append(block("crm_orders", "operations", "/orders", items))
        if self.scope.can("billing.read"):
            outstanding = Invoice.total - Invoice.amount_paid
            rows = await self.grouped(Invoice, Invoice.status, outstanding)
            items = [
                metric(f"Invoices · {s} (outstanding)", n, total, currency)
                for s, n, currency, total in rows
            ]
            blocks.append(block("crm_receivables", "finance", "/billing", items))
        return blocks

    # WhatsApp -------------------------------------------------------------------------

    async def whatsapp(self, data: WhatsAppInput) -> dict[str, Any]:
        """Conversation list or one thread. Message bodies are customer-authored, untrusted."""
        pi = PiService(self.session, self.scope)
        await pi.require("pi.read")
        if data.conversation_id is not None:
            conversation = await pi.conversations.get(data.conversation_id)
            customer = await pi.customers.get(conversation.customer_id)
            rows = list(
                await self.session.scalars(
                    pi.messages.select()
                    .where(PiMessage.conversation_id == conversation.id)
                    .order_by(PiMessage.created_at.desc(), PiMessage.id.desc())
                    .limit(40)
                )
            )
            total = await self.count(PiMessage, PiMessage.conversation_id == conversation.id)
            items = [
                {
                    "at": m.created_at,
                    "from": m.sent_by_label or m.sender_type,
                    "direction": m.direction,
                    "type": m.message_type,
                    "body": (m.body or "")[:MESSAGE_CHARS],
                    "status": m.status,
                }
                for m in reversed(rows)
            ]
            return safe(
                {
                    "area": "whatsapp_thread",
                    "title": f"WhatsApp · {customer.name}",
                    "specialist": "crm",
                    "route": "/pi/inbox",
                    "conversation_id": conversation.id,
                    "customer": customer.name,
                    "conversation_status": conversation.status,
                    "mode": conversation.mode,
                    "stored_summary": conversation.summary,
                    "items": items,
                    "total": total,
                    "page": 1,
                    "page_size": 40,
                    "count_unit": "messages",
                    "untrusted_content": True,
                }
            )
        since = datetime.now(UTC) - timedelta(days=data.days)
        query = pi.conversations.select().where(PiConversation.last_message_at >= since)
        if data.unread_only:
            query = query.where(PiConversation.unread_count > 0)
        if data.search:
            matching = select(Customer.id).where(
                self.repo(Customer).predicate(),
                Customer.name.ilike(like_pattern(data.search)),
            )
            query = query.where(
                PiConversation.customer_id.in_(matching)
                | PiConversation.last_message_preview.ilike(like_pattern(data.search))
            )
        total = int(
            await self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        conversations = list(
            await self.session.scalars(
                query.order_by(PiConversation.last_message_at.desc(), PiConversation.id).limit(12)
            )
        )
        names = {
            c.id: c.name
            for c in await self.session.scalars(
                self.repo(Customer)
                .select()
                .where(Customer.id.in_([c.customer_id for c in conversations]))
            )
        }
        handoffs = {
            h.conversation_id: h.status
            for h in await self.session.scalars(
                pi.handoffs.select().where(
                    PiHandoff.conversation_id.in_([c.id for c in conversations]),
                    PiHandoff.status.in_(ACTIVE_HANDOFF),
                )
            )
        }
        items = []
        for c in conversations:
            recent = list(
                await self.session.scalars(
                    pi.messages.select()
                    .where(PiMessage.conversation_id == c.id)
                    .order_by(PiMessage.created_at.desc(), PiMessage.id.desc())
                    .limit(6)
                )
            )
            items.append(
                {
                    "conversation_id": c.id,
                    "customer": names.get(c.customer_id, "Unknown"),
                    "status": c.status,
                    "mode": c.mode,
                    "unread": c.unread_count,
                    "handoff": handoffs.get(c.id),
                    "last_message_at": c.last_message_at,
                    "stored_summary": (c.summary or "")[:MESSAGE_CHARS],
                    "recent": " | ".join(
                        f"{m.sender_type}: {(m.body or '[' + m.message_type + ']')[:160]}"
                        for m in reversed(recent)
                    ),
                }
            )
        stats = {
            "open": await self._visible_count(pi, PiConversation.status == "open"),
            "unread": await self._visible_count(pi, PiConversation.unread_count > 0),
            "human_mode": await self._visible_count(
                pi, PiConversation.status == "open", PiConversation.mode == "human"
            ),
        }
        return safe(
            {
                "area": "whatsapp",
                "title": "WhatsApp inbox",
                "specialist": "crm",
                "route": "/pi/inbox",
                "items": items,
                "total": total,
                "page": 1,
                "page_size": 12,
                "count_unit": f"conversations active in {data.days} days",
                "inbox": stats,
                "scope": "all" if self.scope.can("pi.inbox.all") else "assigned to you",
                "untrusted_content": True,
            }
        )

    async def _visible_count(self, pi: PiService, *conditions: Any) -> int:
        query = select(func.count()).select_from(PiConversation)
        return int(
            await self.session.scalar(query.where(pi.conversations.predicate(), *conditions)) or 0
        )

    # Monitoring -----------------------------------------------------------------------

    async def monitor(self) -> dict[str, Any]:
        """Deterministic health signals with a suggested next step, filtered by permission."""
        now = datetime.now(UTC)
        today = now.date()
        signals: list[dict[str, Any]] = []
        checked: list[str] = []

        def add(
            key: str,
            area: str,
            severity: str,
            count: int,
            title: str,
            suggestion: str,
            route: str,
            **extra: Any,
        ) -> None:
            if count:
                signals.append(
                    {
                        "key": key,
                        "area": area,
                        "severity": severity,
                        "count": count,
                        "title": title,
                        "suggestion": suggestion,
                        "route": route,
                        **extra,
                    }
                )

        if self.scope.can("tasks.read"):
            checked.append("tasks")
            tasks = self.agent.task_query().where(WorkspaceTask.status.in_(("todo", "in_progress")))
            overdue = await self.session.scalar(
                select(func.count()).select_from(
                    tasks.where(WorkspaceTask.due_date < today).subquery()
                )
            )
            add(
                "tasks.overdue",
                "tasks",
                "warning",
                int(overdue or 0),
                "Overdue workspace tasks",
                "Review overdue tasks: complete, reassign or move the due date.",
                "/workspace-agent",
            )
            urgent = await self.session.scalar(
                select(func.count()).select_from(
                    tasks.where(WorkspaceTask.priority == "high").subquery()
                )
            )
            add(
                "tasks.high_priority",
                "tasks",
                "info",
                int(urgent or 0),
                "Open high-priority tasks",
                "Start with high-priority tasks today.",
                "/workspace-agent",
            )
        if self.scope.can("billing.read"):
            checked.append("billing")
            conditions = (
                Invoice.status.in_(OPEN_INVOICE_STATUSES),
                Invoice.due_date < today,
            )
            rows = (
                await self.session.execute(
                    select(
                        Invoice.currency,
                        func.count(),
                        func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0),
                    )
                    .where(self.repo(Invoice).predicate(), *conditions)
                    .group_by(Invoice.currency)
                )
            ).all()
            add(
                "billing.overdue",
                "billing",
                "critical",
                sum(n for _, n, _ in rows),
                "Overdue unpaid invoices",
                "Send payment reminders for overdue invoices and record any payments received.",
                "/billing",
                amounts=[{"currency": c, "outstanding": total} for c, _, total in rows],
            )
        if self.scope.can("sales.read"):
            checked.append("sales")
            add(
                "sales.stale",
                "sales",
                "warning",
                await self.count(
                    SalesLead,
                    SalesLead.stage.in_(OPEN_LEAD_STAGES),
                    SalesLead.updated_at < now - timedelta(days=14),
                ),
                "Open leads with no update in 14 days",
                "Follow up on stale leads or mark them lost to keep the pipeline accurate.",
                "/sales",
            )
            add(
                "sales.new",
                "sales",
                "info",
                await self.count(
                    SalesLead,
                    SalesLead.stage == "new",
                    SalesLead.created_at < now - timedelta(days=2),
                ),
                "New leads not qualified after 2 days",
                "Qualify new leads quickly; response speed drives conversion.",
                "/sales",
            )
        if self.scope.can("quotes.read"):
            checked.append("quotes")
            add(
                "quotes.approval",
                "quotes",
                "warning",
                await self.count(Quote, Quote.status == "pending_approval"),
                "Quotes waiting for approval",
                "Approve or reject pending quotes so customers are not kept waiting.",
                "/quotes",
            )
            add(
                "quotes.expiring",
                "quotes",
                "info",
                await self.count(
                    Quote,
                    Quote.status == "sent",
                    Quote.valid_until <= today + timedelta(days=3),
                ),
                "Sent quotes expiring within 3 days",
                "Contact these customers before their quotes expire.",
                "/quotes",
            )
        if self.scope.can("orders.read"):
            checked.append("orders")
            add(
                "orders.stuck",
                "orders",
                "warning",
                await self.count(
                    Order,
                    Order.status.in_(ACTIVE_ORDER_STATUSES),
                    Order.updated_at < now - timedelta(days=3),
                ),
                "Orders not progressed for 3+ days",
                "Check fulfilment for confirmed or processing orders that have not moved.",
                "/orders",
            )
        if self.scope.can("inventory.read"):
            checked.append("inventory")
            add(
                "inventory.out",
                "inventory",
                "warning",
                await self.count(StockLevel, StockLevel.on_hand - StockLevel.reserved <= 0),
                "Stock locations with nothing available",
                "Restock or pause sales for items with no available quantity.",
                "/inventory",
            )
        if self.scope.can("customers.read"):
            checked.append("customers")
            add(
                "customers.new",
                "customers",
                "info",
                await self.count(Customer, Customer.created_at >= now - timedelta(days=7)),
                "New customers this week",
                "Welcome new customers and capture their details for follow-up.",
                "/customers",
            )
        if self.scope.can("pi.read"):
            try:
                await self._monitor_whatsapp(add, now)
                checked.append("whatsapp")
            except (BusinessRuleViolation, PermissionDenied):
                pass  # PI not installed/enabled here; not a workspace problem.
        if self.scope.can("integrations.read"):
            checked.append("integrations")
            add(
                "integrations.unhealthy",
                "integrations",
                "critical",
                await self.count(
                    IntegrationConnection,
                    IntegrationConnection.status.in_(UNHEALTHY_CONNECTIONS)
                    | IntegrationConnection.health.in_(("degraded", "failing")),
                ),
                "Integrations needing attention",
                "Reconnect or fix failing integrations so data keeps syncing.",
                "/settings/integrations",
            )
        order = {"critical": 0, "warning": 1, "info": 2}
        signals.sort(key=lambda s: (order[s["severity"]], -s["count"]))
        return safe(
            {
                "generated_at": now,
                "checked_areas": checked,
                "signals": signals,
                "healthy": not any(s["severity"] != "info" for s in signals),
            }
        )

    async def _monitor_whatsapp(self, add: Any, now: datetime) -> None:
        pi = PiService(self.session, self.scope)
        await pi.require("pi.read")
        waiting = await self._visible_count(
            pi,
            PiConversation.status == "open",
            PiConversation.unread_count > 0,
            PiConversation.last_inbound_at < now - timedelta(minutes=30),
        )
        add(
            "whatsapp.waiting",
            "whatsapp",
            "critical",
            waiting,
            "WhatsApp chats waiting 30+ minutes",
            "Open the inbox and reply or take over these conversations.",
            "/pi/inbox",
        )
        visible = pi.conversations.select().with_only_columns(PiConversation.id)
        unassigned = await self.count(
            PiHandoff,
            PiHandoff.status == "open",
            PiHandoff.assigned_user_id.is_(None),
            PiHandoff.conversation_id.in_(visible),
        )
        add(
            "whatsapp.handoffs",
            "whatsapp",
            "warning",
            unassigned,
            "Unassigned handoffs",
            "Assign each handoff to a team member so customers get a human reply.",
            "/pi/handoffs",
        )
        failed = await self.count(
            PiMessage,
            PiMessage.direction == "outbound",
            PiMessage.status == "failed",
            PiMessage.created_at >= now - timedelta(hours=24),
            PiMessage.conversation_id.in_(visible),
        )
        add(
            "whatsapp.failed",
            "whatsapp",
            "warning",
            failed,
            "WhatsApp messages that failed to send (24h)",
            "Check the WhatsApp connection and resend important replies.",
            "/pi/whatsapp",
        )
        approvals = await self.count(
            PiMessage,
            PiMessage.status == "pending_approval",
            PiMessage.conversation_id.in_(visible),
        )
        add(
            "whatsapp.approvals",
            "whatsapp",
            "warning",
            approvals,
            "AI replies waiting for approval",
            "Review drafted replies in the inbox and approve or edit them.",
            "/pi/inbox",
        )
