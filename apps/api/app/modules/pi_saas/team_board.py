"""The team board: everything the business's team must do, across all customers, on one
Kanban (To do, In progress, Waiting, Done).

Cards are ``PiTask`` rows. pi makes most of them by itself from the team's real work
(``sync_board``): a proposal to price or approve, a payment proof to check, a question pi
asked the team, a chat handed to a person, paid work to start or deliver, an unhappy
customer to look after. Each one has the idempotency key ``board:<kind>:<source id>``,
so running the sync again never makes a duplicate, and it closes (done) by itself once
its source is resolved. pi never reopens or overwrites a card the team moved or
assigned by hand; it only closes it when the work behind it is done. The team adds its
own cards too (``kind`` "task").

Moving a "start" card to In progress starts the work, and a "deliver" card to Done
delivers it, exactly like the deal page's buttons (pi tells the customer).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Invoice
from app.modules.customers.models import Customer
from app.modules.memberships.models import Membership
from app.modules.orders.models import Order
from app.modules.pi.models import PiConversation, PiHandoff, PiMessage, WhatsAppConnection
from app.modules.pi.service import ACTIVE_HANDOFF
from app.modules.pi_saas import deals
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.models import PiStaffRequest, PiTask
from app.modules.quotes.models import Quote
from app.modules.sales.models import SalesLead
from app.modules.users.models import PlatformUser
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

PREFIX = "board:"
KINDS = (
    "price",
    "approve",
    "invoice",
    "payment",
    "request",
    "reply",
    "start",
    "deliver",
    "feedback",
)
LIVE = ("open", "in_progress", "blocked")
COLUMNS = {"open": "todo", "in_progress": "doing", "blocked": "waiting", "done": "done"}
DONE_DAYS = 7
SLA = {
    "urgent": timedelta(hours=2),
    "high": timedelta(hours=24),
    "normal": timedelta(hours=48),
    "low": timedelta(days=4),
}
RANK = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
FEEDBACK_DAYS = 30


@dataclass
class Card:
    """One piece of work pi found, before it becomes (or matches) a board card."""

    kind: str
    source: str
    title: str
    since: datetime
    customer_id: UUID | None = None
    conversation_id: UUID | None = None
    description: str = ""
    priority: str = "normal"
    status: str = "open"
    assignee_user_id: UUID | None = None

    @property
    def key(self) -> str:
        return f"{PREFIX}{self.kind}:{self.source}"[:200]


def kind_of(task: PiTask) -> str:
    """The card's kind from its key; the team's own cards are "task"."""
    key = task.idempotency_key or ""
    if key.startswith(PREFIX):
        kind = key[len(PREFIX) :].split(":", 1)[0]
        if kind in KINDS:
            return kind
    return "task"


def source_of(task: PiTask) -> str:
    key = task.idempotency_key or ""
    return key[len(PREFIX) :].split(":", 1)[1] if key.startswith(PREFIX) and ":" in key else ""


def _line(text: str, limit: int = 150) -> str:
    first = " ".join((text or "").split())
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def _aware(when: datetime | None) -> datetime:
    if when is None:
        return datetime.now(UTC)
    return when if when.tzinfo else when.replace(tzinfo=UTC)


# ---- Finding the work ---------------------------------------------------------------


async def _proposals(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Deal proposals that wait on the team: a draft with no prices, or one to approve."""
    rows = await session.execute(
        WorkspaceRepository(session, Quote, scope)
        .select()
        .add_columns(SalesLead.title, SalesLead.conversation_id)
        .join(SalesLead, SalesLead.id == Quote.lead_id)
        .where(
            or_(
                and_(Quote.status == "draft", Quote.total <= 0),
                Quote.status == "pending_approval",
            )
        )
        .limit(300)
    )
    cards = []
    for quote, project, conversation in rows:
        if quote.status == "draft":
            cards.append(
                Card(
                    "price",
                    str(quote.id),
                    f"Add prices: {quote.number} · {project}",
                    quote.created_at,
                    quote.customer_id,
                    conversation,
                    "The draft proposal is ready. Add the prices that aren't in your catalog, "
                    "then send it.",
                )
            )
        else:
            cards.append(
                Card(
                    "approve",
                    str(quote.id),
                    f"Approve proposal {quote.number}",
                    quote.updated_at,
                    quote.customer_id,
                    conversation,
                    f"{project}: {deals.money(quote.total, quote.currency)}. A manager "
                    "approves it, then it can be sent.",
                    priority="high",
                )
            )
    return cards


async def _payments(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Customers who say they paid by bank or wallet: someone checks the proof."""
    rows = await session.execute(
        WorkspaceRepository(session, PiPaymentRequest, scope)
        .select()
        .add_columns(Invoice.number)
        .join(Invoice, Invoice.id == PiPaymentRequest.invoice_id)
        .where(PiPaymentRequest.status.in_(["awaiting_verification", "needs_review"]))
        .limit(300)
    )
    return [
        Card(
            "payment",
            str(row.id),
            f"Check payment proof {number}",
            row.updated_at,
            row.customer_id,
            row.conversation_id,
            " ".join(
                part
                for part in (
                    f"{deals.money(row.amount, row.currency)} by {row.method.replace('_', ' ')}.",
                    f"Reference {row.reference}." if row.reference else "",
                    _line(row.proof_note, 300),
                )
                if part
            ),
            priority="high",
        )
        for row, number in rows
    ]


async def _requests(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Open requests on the request desk. Price/approve requests for a proposal are the
    proposal's own card, so they aren't shown twice."""
    rows = await session.scalars(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(
            PiStaffRequest.status == "open",
            ~and_(
                PiStaffRequest.kind.in_(["price", "approve"]),
                PiStaffRequest.quote_id.is_not(None),
            ),
        )
        .limit(300)
    )
    return [
        Card(
            "request",
            str(row.id),
            f"Answer pi: {_line(row.question, 140)}",
            row.created_at,
            row.customer_id,
            row.conversation_id,
            _line(row.context_summary or row.question, 1000),
            priority="high" if row.priority == "high" else "normal",
        )
        for row in rows
    ]


async def _replies(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Chats handed to a person that nobody has answered since."""
    replied = exists().where(
        PiMessage.tenant_id == PiHandoff.tenant_id,
        PiMessage.environment_id == PiHandoff.environment_id,
        PiMessage.conversation_id == PiHandoff.conversation_id,
        PiMessage.direction == "outbound",
        PiMessage.sender_type == "human",
        PiMessage.created_at >= PiHandoff.created_at,
    )
    rows = await session.execute(
        WorkspaceRepository(session, PiHandoff, scope)
        .select()
        .add_columns(Customer.name)
        .join(Customer, Customer.id == PiHandoff.customer_id)
        .where(PiHandoff.status.in_(ACTIVE_HANDOFF), ~replied)
        .limit(300)
    )
    return [
        Card(
            "reply",
            str(row.id),
            f"Reply to {name or 'the customer'}",
            row.created_at,
            row.customer_id,
            row.conversation_id,
            _line(row.summary, 1000),
            priority="urgent",
            assignee_user_id=row.assigned_user_id,
        )
        for row, name in rows
    ]


async def _work(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Deal orders: paid but not started yet, or started and not delivered."""
    rows = list(
        await session.execute(
            WorkspaceRepository(session, Order, scope)
            .select()
            .add_columns(SalesLead.title, SalesLead.conversation_id)
            .join(Quote, Quote.order_id == Order.id)
            .join(SalesLead, SalesLead.id == Quote.lead_id)
            .where(Order.status.in_(["confirmed", "processing", "shipped"]))
            .limit(300)
        )
    )
    confirmed = [order.id for order, _, _ in rows if order.status == "confirmed"]
    paid = {
        invoice.order_id: invoice
        for invoice in await session.scalars(
            WorkspaceRepository(session, Invoice, scope)
            .select()
            .where(Invoice.order_id.in_(confirmed or [None]), Invoice.status == "paid")
        )
    }
    cards = []
    for order, project, conversation in rows:
        if order.status == "confirmed":
            invoice = paid.get(order.id)
            if invoice is None:
                continue
            cards.append(
                Card(
                    "start",
                    str(order.id),
                    f"Start the work: {project}",
                    invoice.updated_at,
                    order.customer_id,
                    conversation,
                    f"The customer paid invoice {invoice.number}. Move this card to In "
                    "progress to start; pi tells them the work has started.",
                    priority="high",
                )
            )
        else:
            cards.append(
                Card(
                    "deliver",
                    str(order.id),
                    f"Deliver: {project}",
                    order.updated_at,
                    order.customer_id,
                    conversation,
                    "Move this card to Done when it's delivered; pi tells the customer and "
                    "asks how it went.",
                    status="in_progress",
                )
            )
    return cards


async def _invoices(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Accepted deals whose invoice is ready but not sent: pi never sends an invoice by
    itself, a person checks it and sends it."""
    rows = list(
        await session.execute(
            WorkspaceRepository(session, Invoice, scope)
            .select()
            .add_columns(SalesLead.title, SalesLead.conversation_id)
            .join(Quote, Quote.order_id == Invoice.order_id)
            .join(SalesLead, SalesLead.id == Quote.lead_id)
            .where(Invoice.status.in_(["draft", "issued"]))
            .limit(300)
        )
    )
    sent = await deals.invoices_sent(session, scope, [invoice for invoice, _, _ in rows])
    return [
        Card(
            "invoice",
            str(invoice.id),
            f"Send invoice {invoice.number}: {project}",
            invoice.created_at,
            invoice.customer_id,
            conversation,
            f"The customer accepted. Check invoice {invoice.number} "
            f"({deals.money(invoice.total, invoice.currency)}), then send it: they get it "
            "on WhatsApp with the payment link.",
            priority="high",
        )
        for invoice, project, conversation in rows
        if invoice.id not in sent
    ]


async def _feedback(session: AsyncSession, scope: WorkspaceScope) -> list[Card]:
    """Unhappy answers to "How did it go?" from the last 30 days."""
    since = datetime.now(UTC) - timedelta(days=FEEDBACK_DAYS)
    rows = await session.scalars(
        WorkspaceRepository(session, PiConversation, scope)
        .select()
        .where(
            PiConversation.service_brief.has_key("feedback"),
            PiConversation.last_message_at >= since,
        )
        .limit(300)
    )
    cards = []
    for conversation in rows:
        for entry in conversation.service_brief.get("feedback") or []:
            if not isinstance(entry, dict) or entry.get("mood") != "unhappy":
                continue
            try:
                at = datetime.fromisoformat(str(entry.get("at")))
            except ValueError:
                continue
            if _aware(at) < since:
                continue
            words = str(entry.get("words") or "")
            cards.append(
                Card(
                    "feedback",
                    f"{conversation.id}:{entry.get('at')}",
                    f"Fix: {_line(words, 140)}",
                    _aware(at),
                    conversation.customer_id,
                    conversation.id,
                    f"Feedback on {entry.get('project') or 'the project'}: {words}"[:2000],
                    priority="high",
                )
            )
    return cards


COLLECTORS = {
    "proposals": (_proposals, ("price", "approve")),
    "invoices": (_invoices, ("invoice",)),
    "payments": (_payments, ("payment",)),
    "requests": (_requests, ("request",)),
    "replies": (_replies, ("reply",)),
    "work": (_work, ("start", "deliver")),
    "feedback": (_feedback, ("feedback",)),
}
# Feedback has no "resolved" state in its source: the team closes those cards.
NEVER_AUTO_CLOSED = {"feedback"}


async def sync_board(session: AsyncSession, scope: WorkspaceScope) -> dict[str, int]:
    """Turn the team's real work into cards and close the ones whose work is done.
    Idempotent; each source runs in its own savepoint, and a source that fails leaves
    its cards exactly as they are. The caller commits."""
    found: dict[str, Card] = {}
    failed: set[str] = set()
    for name, (collect, kinds) in COLLECTORS.items():
        try:
            async with session.begin_nested():
                for card in await collect(session, scope):
                    found[card.key] = card
        except Exception:  # noqa: BLE001 - the other sources and the next run still go ahead
            logger.warning("pi_team_board_source_failed", extra={"source": name}, exc_info=True)
            failed.update(kinds)
    known: set[str] = set()
    keys = list(found)
    for start in range(0, len(keys), 500):
        known.update(
            await session.scalars(
                WorkspaceRepository(session, PiTask, scope)
                .select()
                .with_only_columns(PiTask.idempotency_key)
                .where(PiTask.idempotency_key.in_(keys[start : start + 500]))
            )
        )
    created = 0
    for key, card in found.items():
        if key in known:
            continue  # Never reopened or overwritten: the team may have moved it.
        inserted = await session.scalar(
            insert(PiTask)
            .values(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                title=card.title[:200],
                description=card.description,
                customer_id=card.customer_id,
                conversation_id=card.conversation_id,
                assignee_user_id=card.assignee_user_id,
                created_by_label="pi",
                status=card.status,
                priority=card.priority,
                due_at=_aware(card.since) + SLA[card.priority],
                idempotency_key=key,
            )
            .on_conflict_do_nothing()
            .returning(PiTask.id)
        )
        created += inserted is not None
    closed = 0
    live = await session.scalars(
        WorkspaceRepository(session, PiTask, scope)
        .select()
        .where(PiTask.idempotency_key.startswith(PREFIX), PiTask.status.in_(LIVE))
    )
    for task in live:
        kind = kind_of(task)
        if task.idempotency_key in found or kind in failed or kind in NEVER_AUTO_CLOSED:
            continue
        task.status = "done"
        closed += 1
    await session.flush()
    return {"created": created, "closed": closed}


# ---- Reading the board --------------------------------------------------------------


async def members(session: AsyncSession, scope: WorkspaceScope) -> list[dict[str, Any]]:
    """The business's active team members, for assigning cards."""
    rows = await session.execute(
        select(PlatformUser.id, PlatformUser.display_name, PlatformUser.email)
        .join(Membership, Membership.user_id == PlatformUser.id)
        .where(
            Membership.tenant_id == scope.tenant_id,
            Membership.status == "active",
            PlatformUser.status == "active",
        )
        .order_by(PlatformUser.display_name)
        .limit(200)
    )
    return [
        {"id": user_id, "name": name or (email or "").split("@")[0]}
        for user_id, name, email in rows
    ]


async def _context(
    session: AsyncSession, scope: WorkspaceScope, tasks: list[PiTask]
) -> dict[str, dict[str, Any]]:
    """Each card's project name and the page where the team does the work, looked up
    in a few batched reads (never stored, so they always follow the source)."""
    by_kind: dict[str, list[UUID]] = {}
    for task in tasks:
        kind = kind_of(task)
        try:
            source = UUID(source_of(task).split(":", 1)[0])
        except ValueError:
            continue
        by_kind.setdefault(kind, []).append(source)

    def ids(*kinds: str) -> list[UUID]:
        return [x for k in kinds for x in by_kind.get(k, [])] or [UUID(int=0)]

    payments = {
        row.id: row
        for row in await session.scalars(
            WorkspaceRepository(session, PiPaymentRequest, scope)
            .select()
            .where(PiPaymentRequest.id.in_(ids("payment")))
        )
    }
    invoices = {
        row.id: row
        for row in await session.scalars(
            WorkspaceRepository(session, Invoice, scope)
            .select()
            .where(
                Invoice.id.in_(
                    [*(p.invoice_id for p in payments.values()), *ids("invoice")] or [UUID(int=0)]
                )
            )
        )
    }
    requests = {
        row.id: row
        for row in await session.scalars(
            WorkspaceRepository(session, PiStaffRequest, scope)
            .select()
            .where(PiStaffRequest.id.in_(ids("request")))
        )
    }
    handoffs = {
        row.id: row
        for row in await session.scalars(
            WorkspaceRepository(session, PiHandoff, scope)
            .select()
            .where(PiHandoff.id.in_(ids("reply")))
        )
    }
    order_ids = [*ids("start", "deliver"), *(i.order_id for i in invoices.values() if i.order_id)]
    quotes = list(
        await session.scalars(
            WorkspaceRepository(session, Quote, scope)
            .select()
            .where(or_(Quote.id.in_(ids("price", "approve")), Quote.order_id.in_(order_ids)))
        )
    )
    by_order = {q.order_id: q for q in quotes if q.order_id}
    by_quote = {q.id: q for q in quotes}
    lead_ids = [q.lead_id for q in quotes if q.lead_id]
    lead_ids += [r.lead_id for r in requests.values() if r.lead_id]
    leads = {
        row.id: row
        for row in await session.scalars(
            WorkspaceRepository(session, SalesLead, scope)
            .select()
            .where(SalesLead.id.in_(lead_ids or [UUID(int=0)]))
        )
    }

    def title(lead_id: UUID | None) -> str | None:
        lead = leads.get(lead_id) if lead_id else None
        return lead.title if lead else None

    out: dict[str, dict[str, Any]] = {}
    for task in tasks:
        kind, raw = kind_of(task), source_of(task).split(":", 1)[0]
        project, link = None, None
        try:
            source = UUID(raw) if raw else None
        except ValueError:
            source = None
        chat = f"/pi/inbox?conversation={task.conversation_id}" if task.conversation_id else None
        if kind in {"price", "approve"} and source:
            quote = by_quote.get(source)
            project = title(quote.lead_id) if quote else None
            link = f"/quotes/{source}/edit" if kind == "price" else f"/quotes/{source}"
        elif kind == "invoice" and source:
            invoice = invoices.get(source)
            quote = by_order.get(invoice.order_id) if invoice and invoice.order_id else None
            project = title(quote.lead_id) if quote else None
            link = f"/billing/invoices/{source}"
        elif kind == "payment" and source:
            payment = payments.get(source)
            invoice = invoices.get(payment.invoice_id) if payment else None
            quote = by_order.get(invoice.order_id) if invoice and invoice.order_id else None
            project = title(quote.lead_id) if quote else None
            link = f"/billing/invoices/{payment.invoice_id}" if payment else None
        elif kind == "request" and source:
            request = requests.get(source)
            project = title(request.lead_id) if request else None
            link = f"/pi/requests?request={source}"
        elif kind in {"start", "deliver"} and source:
            quote = by_order.get(source)
            project = title(quote.lead_id) if quote else None
            link = f"/sales/leads/{quote.lead_id}" if quote and quote.lead_id else None
        elif kind == "reply" and source:
            handoff = handoffs.get(source)
            conversation = handoff.conversation_id if handoff else task.conversation_id
            link = f"/pi/inbox?conversation={conversation}" if conversation else None
        elif kind == "feedback":
            link = chat
        else:
            link = chat or (f"/customers/{task.customer_id}" if task.customer_id else None)
        out[str(task.id)] = {"project": project, "link": link}
    return out


def _sort_key(task: PiTask) -> tuple[Any, ...]:
    due = _aware(task.due_at).timestamp() if task.due_at else float("inf")
    return (RANK.get(task.priority, 2), due, -_aware(task.created_at).timestamp())


async def board(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    who: str = "all",
    kind: str | None = None,
) -> dict[str, Any]:
    """The four columns, each card with its customer, project, assignee, due time and
    link; the team's members for assigning; and counts (overall, before the filters)."""
    now = datetime.now(UTC)
    tasks = list(
        await session.scalars(
            WorkspaceRepository(session, PiTask, scope)
            .select()
            .where(
                or_(
                    PiTask.status.in_(LIVE),
                    and_(
                        PiTask.status == "done",
                        PiTask.updated_at >= now - timedelta(days=DONE_DAYS),
                    ),
                )
            )
            .order_by(PiTask.updated_at.desc())
            .limit(600)
        )
    )
    team = await members(session, scope)
    names = {m["id"]: m["name"] for m in team}
    customer_ids = {t.customer_id for t in tasks if t.customer_id}
    customers = {
        c.id: c.name
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_(list(customer_ids) or [UUID(int=0)]))
        )
    }
    context = await _context(session, scope, tasks)

    def overdue(task: PiTask) -> bool:
        return task.status in LIVE and task.due_at is not None and _aware(task.due_at) < now

    def view(task: PiTask) -> dict[str, Any]:
        extra = context.get(str(task.id), {})
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "kind": kind_of(task),
            "auto": (task.idempotency_key or "").startswith(PREFIX),
            "status": task.status,
            "column": COLUMNS[task.status],
            "customer": {"id": task.customer_id, "name": customers.get(task.customer_id, "")}
            if task.customer_id
            else None,
            "project": extra.get("project"),
            "assignee": {
                "id": task.assignee_user_id,
                "name": names.get(task.assignee_user_id, "Former member"),
            }
            if task.assignee_user_id
            else None,
            "priority": task.priority,
            "due_at": task.due_at,
            "overdue": overdue(task),
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "created_by": task.created_by_label,
            "link": extra.get("link"),
        }

    live = [t for t in tasks if t.status in LIVE]
    counts = {
        "todo": sum(t.status == "open" for t in tasks),
        "doing": sum(t.status == "in_progress" for t in tasks),
        "waiting": sum(t.status == "blocked" for t in tasks),
        "done": sum(t.status == "done" for t in tasks),
        "overdue": sum(overdue(t) for t in live),
        "mine": sum(t.assignee_user_id == scope.user_id for t in live),
        "unassigned": sum(t.assignee_user_id is None for t in live),
        "all": len(live),
    }
    kinds: dict[str, int] = {}
    for task in live:
        kinds[kind_of(task)] = kinds.get(kind_of(task), 0) + 1
    shown = tasks
    if who == "me":
        shown = [t for t in shown if t.assignee_user_id == scope.user_id]
    elif who == "unassigned":
        shown = [t for t in shown if t.assignee_user_id is None]
    if kind:
        shown = [t for t in shown if kind_of(t) == kind]
    columns: dict[str, list[dict[str, Any]]] = {c: [] for c in COLUMNS.values()}
    for task in sorted(shown, key=_sort_key):
        columns[COLUMNS[task.status]].append(view(task))
    columns["done"].sort(key=lambda c: c["updated_at"], reverse=True)
    return {
        "columns": columns,
        "members": team,
        "counts": counts,
        "kinds": kinds,
        "me": scope.user_id,
        "updated_at": now,
    }


async def card(session: AsyncSession, scope: WorkspaceScope, task: PiTask) -> dict[str, Any]:
    """One card, as the board shows it."""
    found = await board(session, scope)
    for column in found["columns"].values():
        for item in column:
            if item["id"] == task.id:
                return item
    return {"id": task.id, "title": task.title, "status": task.status, "kind": kind_of(task)}


# ---- The worker ---------------------------------------------------------------------


async def sweep(ctx: dict[str, Any]) -> int:
    """Cron job (every 2 minutes): keep every active pi business's board current."""
    from app.modules.pi.runtime import system_scope

    async with ctx["sessions"]() as session:
        connections = list(
            await session.scalars(
                select(WhatsAppConnection)
                .where(WhatsAppConnection.status == "active")
                .order_by(WhatsAppConnection.tenant_id, WhatsAppConnection.environment_id)
            )
        )
    seen: set[tuple[Any, Any]] = set()
    changed = 0
    for connection in connections:
        key = (connection.tenant_id, connection.environment_id)
        if key in seen:
            continue
        seen.add(key)
        async with ctx["sessions"]() as session:
            try:
                scope = await system_scope(session, connection)
                if scope is None:
                    continue
                result = await sync_board(session, scope)
                await session.commit()
                changed += result["created"] + result["closed"]
            except Exception:  # noqa: BLE001 - one business never stops the others
                logger.warning("pi_team_board_sweep_failed", exc_info=True)
    return changed
