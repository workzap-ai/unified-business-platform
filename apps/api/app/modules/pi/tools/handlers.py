"""Tool implementations. Every value returned is read from a business service; nothing is
computed from model text. Identity is always the conversation's customer."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select

from app.core.pagination import Pagination
from app.modules.billing.service import BillingService
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.models import CatalogProduct, CatalogVariant
from app.modules.catalog.service import CatalogService
from app.modules.customers.service import CustomerService
from app.modules.inventory.service import InventoryService
from app.modules.orders.schemas import OrderCreate, OrderLineInput
from app.modules.orders.service import OrderService
from app.modules.pi.knowledge import KnowledgeService
from app.modules.pi.models import (
    KnowledgeDocument,
    KnowledgeSource,
    PiMemory,
    PiMessage,
    PiPendingAction,
)
from app.modules.pi.tools.base import ToolContext, ToolInput, ToolOutput, ToolRefused
from app.modules.pi.tools.confirmation import fingerprint, token_for, tokens_match
from app.modules.quotes.schemas import QuoteCreate, QuoteLineInput
from app.modules.quotes.service import QuoteService
from app.modules.tenants.models import Tenant
from app.shared.money import compute_totals
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

# ---------------------------------------------------------------------------- shared shapes


class Empty(ToolInput):
    pass


class CustomerOut(ToolOutput):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    company: str | None


class VariantOut(ToolOutput):
    id: UUID
    sku: str
    name: str
    price: str
    currency: str
    tracked: bool


class ProductOut(ToolOutput):
    id: UUID
    name: str
    offering_type: str
    description: str
    variants: list[VariantOut]


class LineOut(ToolOutput):
    variant_id: UUID | None
    description: str
    quantity: int
    unit_price: str
    line_total: str


class OrderOut(ToolOutput):
    id: UUID
    number: str
    status: str
    currency: str
    subtotal: str
    tax_total: str
    total: str
    notes: str
    lines: list[LineOut]
    created_at: datetime


class LineInput(ToolInput):
    variant_id: UUID
    quantity: int = Field(ge=1, le=10_000)


class DraftInput(ToolInput):
    lines: list[LineInput] = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=1000)


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


async def _visible_variant(
    ctx: ToolContext, variant_id: UUID
) -> tuple[CatalogVariant, CatalogProduct]:
    """Active, PI-approved catalog items only. Other tenants' ids resolve to not-found."""
    variant, product = await CatalogService(ctx.session, ctx.scope).sellable_variant(variant_id)
    if not product.pi_visible:
        raise ToolRefused("ITEM_NOT_AVAILABLE", "This item is not offered through PI")
    return variant, product


def _order_out(detail: dict[str, object]) -> OrderOut:
    return OrderOut.model_validate(
        {
            **{k: detail[k] for k in ("id", "number", "status", "currency", "notes")},
            "created_at": detail["created_at"],
            "subtotal": str(detail["subtotal"]),
            "tax_total": str(detail["tax_total"]),
            "total": str(detail["total"]),
            "lines": [
                {
                    "variant_id": line["variant_id"],
                    "description": line["description"],
                    "quantity": line["quantity"],
                    "unit_price": str(line["unit_price"]),
                    "line_total": str(line["line_total"]),
                }
                for line in detail["lines"]  # type: ignore[attr-defined]
            ],
        }
    )


async def _own_order(ctx: ToolContext, order_id: UUID, *, lock: bool = False) -> dict[str, object]:
    service = OrderService(ctx.session, ctx.scope)
    row = await service.orders.get(order_id, for_update=lock)
    if row.customer_id != ctx.conversation.customer_id:
        raise ToolRefused("CUSTOMER_MISMATCH", "This record belongs to another customer")
    return (await service.detail(order_id)).model_dump(mode="json")


# ------------------------------------------------------------------------------- customers


class SearchCustomerInput(ToolInput):
    phone: str = Field(min_length=6, max_length=20, pattern=r"^\+?[0-9 ()-]{6,20}$")


class SearchCustomerOutput(ToolOutput):
    match: CustomerOut | None


async def search_customer(ctx: ToolContext, data: SearchCustomerInput) -> SearchCustomerOutput:
    """Only ever confirms the conversation's own customer; never enumerates others."""
    customer = await CustomerService(ctx.session, ctx.scope).get(ctx.conversation.customer_id)
    digits = "".join(ch for ch in data.phone if ch.isdigit())
    own = {
        "".join(ch for ch in (customer.phone or "") if ch.isdigit()),
        customer.whatsapp_id or "",
    }
    if digits and digits in own:
        return SearchCustomerOutput(
            match=CustomerOut.model_validate(customer, from_attributes=True)
        )
    return SearchCustomerOutput(match=None)


class GetCustomerInput(ToolInput):
    customer_id: UUID | None = None


async def get_customer(ctx: ToolContext, data: GetCustomerInput) -> CustomerOut:
    if data.customer_id is not None and data.customer_id != ctx.conversation.customer_id:
        raise ToolRefused("CUSTOMER_MISMATCH", "PI can only read the current customer")
    customer = await CustomerService(ctx.session, ctx.scope).get(ctx.conversation.customer_id)
    return CustomerOut.model_validate(customer, from_attributes=True)


class CustomerOrdersInput(ToolInput):
    limit: int = Field(default=5, ge=1, le=10)
    status: str | None = Field(default=None, max_length=24, pattern=r"^[a-z_]+$")


class OrderSummaryOut(ToolOutput):
    id: UUID
    number: str
    status: str
    total: str
    currency: str
    created_at: datetime


class CustomerOrdersOutput(ToolOutput):
    orders: list[OrderSummaryOut]


async def get_customer_orders(ctx: ToolContext, data: CustomerOrdersInput) -> CustomerOrdersOutput:
    page = await OrderService(ctx.session, ctx.scope).search(
        Pagination(page_size=data.limit),
        status=data.status,
        customer_id=ctx.conversation.customer_id,
    )
    return CustomerOrdersOutput(
        orders=[
            OrderSummaryOut(
                id=o.id,
                number=o.number,
                status=o.status,
                total=_money(o.total),
                currency=o.currency,
                created_at=o.created_at,
            )
            for o in page.items
        ]
    )


class BalanceOutput(ToolOutput):
    balance: str
    currency: str


async def get_customer_balance(ctx: ToolContext, data: Empty) -> BalanceOutput:
    balance = await BillingService(ctx.session, ctx.scope).customer_balance(
        ctx.conversation.customer_id
    )
    settings = await get_settings_row(ctx.session, ctx.scope)
    return BalanceOutput(balance=_money(balance), currency=settings.default_currency)


# -------------------------------------------------------------------------------- catalog


class SearchProductsInput(ToolInput):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=5)


class SearchProductsOutput(ToolOutput):
    products: list[ProductOut]


async def search_products(ctx: ToolContext, data: SearchProductsInput) -> SearchProductsOutput:
    rows = await CatalogService(ctx.session, ctx.scope).search_for_assistant(data.query, data.limit)
    return SearchProductsOutput(
        products=[
            ProductOut(
                id=p.id,
                name=p.name,
                offering_type=p.offering_type,
                description=p.description[:500],
                variants=[
                    VariantOut(
                        id=v.id,
                        sku=v.sku,
                        name=v.name,
                        price=_money(v.price),
                        currency=v.currency,
                        tracked=v.track_inventory,
                    )
                    for v in variants
                ],
            )
            for p, variants in rows
        ]
    )


class GetProductInput(ToolInput):
    product_id: UUID


async def get_product(ctx: ToolContext, data: GetProductInput) -> ProductOut:
    detail = await CatalogService(ctx.session, ctx.scope).detail(data.product_id)
    if detail.status != "active" or not detail.pi_visible:
        raise ToolRefused("ITEM_NOT_AVAILABLE", "This item is not offered through PI")
    return ProductOut(
        id=detail.id,
        name=detail.name,
        offering_type=detail.offering_type,
        description=detail.description[:500],
        variants=[
            VariantOut(
                id=v.id,
                sku=v.sku,
                name=v.name,
                price=_money(v.price),
                currency=v.currency,
                tracked=v.track_inventory,
            )
            for v in detail.variants
            if v.status == "active"
        ],
    )


class InventoryInput(ToolInput):
    variant_ids: list[UUID] = Field(min_length=1, max_length=10)


class StockOut(ToolOutput):
    variant_id: UUID
    tracked: bool
    available: int | None


class InventoryOutput(ToolOutput):
    items: list[StockOut]


async def check_inventory(ctx: ToolContext, data: InventoryInput) -> InventoryOutput:
    for variant_id in data.variant_ids:
        await _visible_variant(ctx, variant_id)
    levels = await InventoryService(ctx.session, ctx.scope).availability(data.variant_ids)
    return InventoryOutput(
        items=[
            StockOut(
                variant_id=vid,
                tracked=levels[vid].tracked,
                # Untracked offerings (services) have no stock figure; never invent one.
                available=max(levels[vid].available, 0) if levels[vid].tracked else None,
            )
            for vid in data.variant_ids
            if vid in levels
        ]
    )


class TotalOutput(ToolOutput):
    currency: str
    lines: list[LineOut]
    subtotal: str
    tax_total: str
    total: str


async def calculate_order_total(ctx: ToolContext, data: DraftInput) -> TotalOutput:
    settings = await get_settings_row(ctx.session, ctx.scope)
    priced = []
    for line in data.lines:
        variant, product = await _visible_variant(ctx, line.variant_id)
        if variant.currency != settings.default_currency:
            raise ToolRefused("CURRENCY_MISMATCH", "Items must use the workspace currency")
        priced.append((variant, product, line.quantity))
    line_totals, totals = compute_totals(
        [(Decimal(q), v.price, Decimal("0")) for v, _, q in priced], settings.tax_rate
    )
    return TotalOutput(
        currency=settings.default_currency,
        lines=[
            LineOut(
                variant_id=v.id,
                description=f"{p.name} — {v.name}",
                quantity=q,
                unit_price=_money(v.price),
                line_total=_money(total),
            )
            for (v, p, q), total in zip(priced, line_totals, strict=True)
        ],
        subtotal=_money(totals.subtotal),
        tax_total=_money(totals.tax_total),
        total=_money(totals.total),
    )


# --------------------------------------------------------------------------------- orders


async def create_order_draft(ctx: ToolContext, data: DraftInput) -> OrderOut:
    """A draft only. It becomes an order solely through create_order + a valid token."""
    for line in data.lines:
        await _visible_variant(ctx, line.variant_id)
    digest = hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:24]
    anchor = ctx.run.message_id if ctx.run else ctx.conversation.id
    service = OrderService(ctx.session, ctx.scope)
    row = await service.create_draft(
        OrderCreate(
            customer_id=ctx.conversation.customer_id,
            notes=data.notes,
            lines=[
                OrderLineInput(variant_id=x.variant_id, quantity=x.quantity) for x in data.lines
            ],
        ),
        source="pi",
        idempotency_key=f"pi:{anchor}:{digest}",
    )
    return _order_out((await service.detail(row.id)).model_dump(mode="json"))


class OrderIdInput(ToolInput):
    order_id: UUID


async def create_order(ctx: ToolContext, data: OrderIdInput) -> OrderOut:
    """Confirms exactly the draft the customer confirmed. Never converts silently."""
    repo = WorkspaceRepository(ctx.session, PiPendingAction, ctx.scope)
    pending = await ctx.session.scalar(
        repo.select()
        .where(
            PiPendingAction.conversation_id == ctx.conversation.id,
            PiPendingAction.kind == "confirm_order",
            PiPendingAction.payload["order_id"].astext == str(data.order_id),
        )
        .order_by((PiPendingAction.status == "pending").desc(), PiPendingAction.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if pending is None or not ctx.confirmation:
        raise ToolRefused("CONFIRMATION_INVALID", "No confirmation was issued for this draft")
    if pending.status == "confirmed":
        raise ToolRefused("CONFIRMATION_USED", "This confirmation was already used")
    if pending.status != "pending":
        raise ToolRefused("CONFIRMATION_INVALID", "This confirmation is no longer actionable")
    if pending.expires_at <= datetime.now(UTC):
        raise ToolRefused("CONFIRMATION_EXPIRED", "This confirmation expired")
    order = await _own_order(ctx, data.order_id, lock=True)
    current = fingerprint(_order_out(order).model_dump(mode="json"))
    if current != pending.payload.get("fingerprint"):
        raise ToolRefused("DRAFT_CHANGED", "The draft changed after it was summarized")
    expected = token_for(str(pending.payload.get("nonce", "")), ctx.conversation.id, current)
    if not tokens_match(expected, ctx.confirmation):
        raise ToolRefused("CONFIRMATION_INVALID", "The confirmation does not match this draft")
    delivered = await WorkspaceRepository(ctx.session, PiMessage, ctx.scope).find(
        PiMessage.conversation_id == ctx.conversation.id,
        PiMessage.direction == "outbound",
        PiMessage.status.in_(["sent", "delivered", "read"]),
        PiMessage.body.startswith(pending.summary),
    )
    if delivered is None:
        raise ToolRefused("SUMMARY_NOT_DELIVERED", "The customer has not received the summary")
    service = OrderService(ctx.session, ctx.scope)
    await service.transition(data.order_id, "confirm")
    pending.status, pending.resolved_at = "confirmed", datetime.now(UTC)
    if ctx.run is not None:
        pending.resolved_by_message_id = ctx.run.message_id
    return _order_out((await service.detail(data.order_id)).model_dump(mode="json"))


async def get_order(ctx: ToolContext, data: OrderIdInput) -> OrderOut:
    return _order_out(await _own_order(ctx, data.order_id))


class InvoiceIdInput(ToolInput):
    invoice_id: UUID


class InvoiceOut(ToolOutput):
    id: UUID
    number: str
    status: str
    currency: str
    total: str
    amount_paid: str
    due_date: str | None


async def get_invoice(ctx: ToolContext, data: InvoiceIdInput) -> InvoiceOut:
    detail = await BillingService(ctx.session, ctx.scope).detail(data.invoice_id)
    if detail.customer_id != ctx.conversation.customer_id:
        raise ToolRefused("CUSTOMER_MISMATCH", "This record belongs to another customer")
    return InvoiceOut(
        id=detail.id,
        number=detail.number,
        status=detail.status,
        currency=detail.currency,
        total=_money(detail.total),
        amount_paid=_money(detail.amount_paid),
        due_date=detail.due_date.isoformat() if detail.due_date else None,
    )


# ------------------------------------------------------------------------ company/knowledge


class Passage(ToolOutput):
    title: str
    source: str
    snippet: str


class CompanyOutput(ToolOutput):
    name: str
    currency: str
    business_type: str
    information: list[Passage]


async def get_company_information(ctx: ToolContext, data: Empty) -> CompanyOutput:
    tenant = await ctx.session.get(Tenant, ctx.scope.tenant_id)
    settings = await get_settings_row(ctx.session, ctx.scope)
    documents = WorkspaceRepository(ctx.session, KnowledgeDocument, ctx.scope)
    sources = WorkspaceRepository(ctx.session, KnowledgeSource, ctx.scope)
    rows = await ctx.session.execute(
        select(KnowledgeDocument.title, KnowledgeSource.name, KnowledgeDocument.body)
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeDocument.source_id)
        .where(
            documents.predicate(),
            sources.predicate(),
            KnowledgeSource.kind == "company_info",
            KnowledgeSource.status == "active",
            KnowledgeDocument.status == "ready",
        )
        .order_by(KnowledgeDocument.created_at.desc())
        .limit(3)
    )
    return CompanyOutput(
        name=tenant.name if tenant else "",
        currency=settings.default_currency,
        business_type=settings.business_type,
        information=[Passage(title=t, source=s, snippet=b[:1000]) for t, s, b in rows],
    )


class QuoteOut(ToolOutput):
    id: UUID
    number: str
    status: str
    currency: str
    total: str


async def create_quote_draft(ctx: ToolContext, data: DraftInput) -> QuoteOut:
    for line in data.lines:
        await _visible_variant(ctx, line.variant_id)
    service = QuoteService(ctx.session, ctx.scope)
    row = await service.create(
        QuoteCreate(
            customer_id=ctx.conversation.customer_id,
            notes=data.notes or "Scope and delivery require team confirmation.",
            lines=[
                QuoteLineInput(variant_id=x.variant_id, quantity=Decimal(x.quantity))
                for x in data.lines
            ],
        ),
        source="pi",
    )
    detail = await service.detail(row.id)
    return QuoteOut(
        id=detail.id,
        number=detail.number,
        status=detail.status,
        currency=detail.currency,
        total=_money(detail.total),
    )


class KnowledgeInput(ToolInput):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class KnowledgeOutput(ToolOutput):
    passages: list[Passage]


async def search_knowledge_base(ctx: ToolContext, data: KnowledgeInput) -> KnowledgeOutput:
    rows = await KnowledgeService(ctx.session, ctx.scope).search(data.query, data.limit)
    return KnowledgeOutput(passages=[Passage.model_validate(x) for x in rows])


class MemoryInput(ToolInput):
    query: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=20)


class MemoryOut(ToolOutput):
    id: UUID
    kind: str
    content: str


class MemoryOutput(ToolOutput):
    memories: list[MemoryOut]


async def search_customer_memory(ctx: ToolContext, data: MemoryInput) -> MemoryOutput:
    repo = WorkspaceRepository(ctx.session, PiMemory, ctx.scope)
    statement = repo.select().where(
        PiMemory.customer_id == ctx.conversation.customer_id, PiMemory.status == "active"
    )
    if data.query:
        statement = statement.where(PiMemory.content.ilike(like_pattern(data.query)))
    rows = list(
        await ctx.session.scalars(statement.order_by(PiMemory.created_at.desc()).limit(data.limit))
    )
    now = datetime.now(UTC)
    for row in rows:
        row.last_used_at = now
    return MemoryOutput(memories=[MemoryOut(id=r.id, kind=r.kind, content=r.content) for r in rows])


# ------------------------------------------------------------------------- communication


class HandoffInput(ToolInput):
    reason: Literal["customer_request", "low_confidence", "complaint", "sensitive", "policy"]
    summary: str = Field(min_length=1, max_length=1000)


class HandoffOutput(ToolOutput):
    handoff_id: UUID
    status: str


async def create_handoff(ctx: ToolContext, data: HandoffInput) -> HandoffOutput:
    from app.modules.pi.service import PiService

    handoff = await PiService(ctx.session, ctx.scope).handoff(
        ctx.conversation.id, data.reason, data.summary
    )
    if ctx.run is not None and handoff.run_id is None:
        handoff.run_id = ctx.run.id
    return HandoffOutput(handoff_id=handoff.id, status=handoff.status)


class SendInput(ToolInput):
    body: str = Field(min_length=1, max_length=4000)


class SendOutput(ToolOutput):
    message_id: UUID
    status: str
    delivery: str


async def send_whatsapp_message(ctx: ToolContext, data: SendInput) -> SendOutput:
    """Queues one AI reply per inbound message. Delivery happens in the send job, which
    re-checks takeover, connection and the 24-hour window; it never reports 'sent' here."""
    if ctx.run is None:
        raise ToolRefused("RUN_REQUIRED", "Replies are only sent for an inbound message")
    repo = WorkspaceRepository(ctx.session, PiMessage, ctx.scope)
    key = f"reply:{ctx.run.message_id}"
    existing = await repo.find(PiMessage.idempotency_key == key)
    if existing is None:
        existing = await repo.add(
            repo.new(
                conversation_id=ctx.conversation.id,
                direction="outbound",
                sender_type="ai",
                body=data.body,
                status="queued",
                agent_key=ctx.agent_key,
                run_id=ctx.run.id,
                idempotency_key=key,
                media={"service_inbound_at": ctx.conversation.last_inbound_at.isoformat()}
                if ctx.conversation.service_brief and ctx.conversation.last_inbound_at
                else {},
            )
        )
        ctx.run.response_message_id = existing.id
    return SendOutput(
        message_id=existing.id,
        status=existing.status,
        delivery="queued_for_whatsapp_delivery",
    )
