from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.integrations.outbox import EntityRef, emit
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.billing.service import BillingService
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.models import CatalogProduct, CatalogVariant
from app.modules.catalog.service import CatalogService
from app.modules.customers.models import Customer
from app.modules.customers.service import log_activity
from app.modules.inventory.service import InventoryService
from app.modules.orders.models import Order, OrderLine
from app.modules.orders.schemas import (
    OrderCreate,
    OrderDetail,
    OrderLineInput,
    OrderLineView,
    OrderListItem,
    OrderView,
)
from app.modules.quotes.models import Quote, QuoteLine
from app.shared.errors import BusinessRuleViolation
from app.shared.money import compute_totals, quantize
from app.shared.scope import WorkspaceScope
from app.shared.sequences import next_number
from app.shared.state_machine import StateMachine
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

ORDER_STATES = StateMachine(
    "order",
    {
        "draft": frozenset({"confirmed", "cancelled"}),
        "confirmed": frozenset({"processing", "cancelled"}),
        "processing": frozenset({"shipped", "delivered", "cancelled"}),
        "shipped": frozenset({"delivered"}),
        "delivered": frozenset(),
        "cancelled": frozenset(),
    },
)
ORDER_EVENTS = {
    "confirmed": "order.confirmed",
    "cancelled": "order.cancelled",
    "delivered": "order.fulfilled",
}


def _order_payload(order: Order) -> dict[str, str | None]:
    return {
        "order_id": str(order.id),
        "number": order.number,
        "status": order.status,
        "customer_id": str(order.customer_id) if order.customer_id else None,
        "total": str(order.total),
        "currency": order.currency,
    }


def _ref(order: Order) -> EntityRef:
    return EntityRef("order", order.id)


ACTION_TARGET = {
    "confirm": "confirmed",
    "start_processing": "processing",
    "ship": "shipped",
    "deliver": "delivered",
    "complete": "delivered",
    "cancel": "cancelled",
}
STOCK_DEDUCTED = frozenset({"confirmed", "processing", "shipped", "delivered"})


def fulfillment_type(types: list[str]) -> str:
    if all(t in {"service", "package"} for t in types):
        return "service"
    return "product" if all(t == "product" for t in types) else "hybrid"


def action_applies(order: Order, action: str) -> bool:
    if action == "complete":
        return order.fulfillment_type == "service" and order.status == "processing"
    if action in {"ship", "deliver"} and order.fulfillment_type == "service":
        return False
    if action == "deliver" and order.status != "shipped":
        return False
    return True


class OrderService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.orders = WorkspaceRepository(session, Order, scope)
        self.lines = WorkspaceRepository(session, OrderLine, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)
        self.quotes = WorkspaceRepository(session, Quote, scope)
        self.quote_lines = WorkspaceRepository(session, QuoteLine, scope)

    async def _names(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(
            select(Customer.id, Customer.name).where(
                self.customers.predicate(), Customer.id.in_(ids)
            )
        )
        return {i: n for i, n in rows}

    async def search(
        self,
        page: Pagination,
        status: str | None = None,
        customer_id: UUID | None = None,
        search: str | None = None,
    ) -> Page[OrderListItem]:
        statement = self.orders.select()
        if status:
            statement = statement.where(Order.status == status)
        if customer_id:
            statement = statement.where(Order.customer_id == customer_id)
        if search:
            statement = statement.where(Order.number.ilike(like_pattern(search.strip())))
        statement = statement.order_by(Order.created_at.desc(), Order.id)
        rows, total = await self.orders.page(statement, page)
        names = await self._names({r.customer_id for r in rows})
        items = [
            OrderListItem(
                **OrderView.model_validate(r).model_dump(), customer_name=names.get(r.customer_id)
            )
            for r in rows
        ]
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    async def lines_for(self, order_id: UUID) -> list[OrderLine]:
        rows = await self.session.scalars(
            self.lines.select().where(OrderLine.order_id == order_id).order_by(OrderLine.position)
        )
        return list(rows)

    async def detail(self, order_id: UUID) -> OrderDetail:
        order = await self.orders.get(order_id)
        lines = await self.lines_for(order.id)
        names = await self._names({order.customer_id})
        invoice = await self.session.scalar(
            select(Invoice).where(
                Invoice.tenant_id == self.scope.tenant_id,
                Invoice.environment_id == self.scope.environment_id,
                Invoice.order_id == order.id,
                Invoice.status != "void",
            )
        )
        next_actions = [
            action
            for action, target in ACTION_TARGET.items()
            if ORDER_STATES.can(order.status, target) and action_applies(order, action)
        ]
        return OrderDetail(
            **OrderView.model_validate(order).model_dump(),
            customer_name=names.get(order.customer_id),
            lines=[OrderLineView.model_validate(x) for x in lines],
            next_actions=next_actions,
            invoice_id=invoice.id if invoice else None,
            invoice_number=invoice.number if invoice else None,
        )

    async def _replace_lines(self, order: Order, inputs: list[OrderLineInput]) -> None:
        """Price every line from the approved catalog price; never from input."""
        settings = await get_settings_row(self.session, self.scope)
        catalog = CatalogService(self.session, self.scope)
        priced: list[tuple[CatalogVariant, str, int, Decimal]] = []
        offering_types = []
        for item in inputs:
            variant, product = await catalog.sellable_variant(item.variant_id)
            offering_types.append(product.offering_type)
            if variant.currency != order.currency:
                raise BusinessRuleViolation(
                    "CURRENCY_MISMATCH", "All order items must use the workspace currency"
                )
            priced.append(
                (variant, f"{product.name} — {variant.name}", item.quantity, item.discount)
            )
        if any(d > 0 for *_, d in priced):
            self.scope.require("orders.write")
            if self.scope.is_system:
                raise BusinessRuleViolation(
                    "DISCOUNT_NOT_ALLOWED", "Discounts need approval from a team member"
                )
        try:
            line_totals, totals = compute_totals(
                [(Decimal(q), v.price, d) for v, _, q, d in priced], settings.tax_rate
            )
        except ValueError:
            raise BusinessRuleViolation("INVALID_DISCOUNT", "A discount exceeds its line") from None
        await self.session.execute(
            delete(OrderLine).where(
                OrderLine.tenant_id == self.scope.tenant_id,
                OrderLine.environment_id == self.scope.environment_id,
                OrderLine.order_id == order.id,
            )
        )
        for position, ((variant, description, qty, discount), line_total) in enumerate(
            zip(priced, line_totals, strict=True), start=1
        ):
            self.session.add(
                self.lines.new(
                    order_id=order.id,
                    variant_id=variant.id,
                    position=position,
                    sku=variant.sku,
                    description=description[:300],
                    quantity=qty,
                    unit_price=variant.price,
                    discount=quantize(discount),
                    line_total=line_total,
                )
            )
        order.fulfillment_type = fulfillment_type(offering_types)
        order.subtotal, order.discount_total = totals.subtotal, totals.discount_total
        order.tax_rate, order.tax_total, order.total = (
            settings.tax_rate,
            totals.tax_total,
            totals.total,
        )
        await self.session.flush()

    async def create_draft(
        self,
        data: OrderCreate,
        source: str = "manual",
        idempotency_key: str | None = None,
    ) -> Order:
        self.scope.require("orders.write")
        if idempotency_key:
            existing = await self.orders.find(Order.idempotency_key == idempotency_key)
            if existing is not None:
                return existing
        await self.customers.get(data.customer_id)
        settings = await get_settings_row(self.session, self.scope)
        order = await self.orders.add(
            self.orders.new(
                number=await next_number(self.session, self.scope, "order"),
                customer_id=data.customer_id,
                source=source,
                currency=settings.default_currency,
                notes=data.notes,
                idempotency_key=idempotency_key,
                created_by_label=self.scope.actor_label[:80],
            )
        )
        await self._replace_lines(order, data.lines)
        await log_activity(
            self.session,
            self.scope,
            order.customer_id,
            "order",
            f"Draft order {order.number}",
            "order",
            order.id,
        )
        await record(
            self.session,
            "order.draft_created",
            scope=self.scope,
            entity_type="order",
            entity_id=order.id,
            details={"number": order.number, "total": str(order.total), "source": source},
        )
        await emit(self.session, self.scope, "order.created", _order_payload(order), _ref(order))
        return order

    async def update_lines(self, order_id: UUID, inputs: list[OrderLineInput]) -> Order:
        self.scope.require("orders.write")
        order = await self.orders.get(order_id, for_update=True)
        if order.status != "draft":
            raise BusinessRuleViolation("ORDER_LOCKED", "Only draft orders can be edited")
        await self._replace_lines(order, inputs)
        await record(
            self.session,
            "order.lines_updated",
            scope=self.scope,
            entity_type="order",
            entity_id=order.id,
            details={"total": str(order.total)},
        )
        return order

    async def create_from_quote(self, quote_id: UUID) -> Order:
        self.scope.require("orders.write")
        quote = await self.quotes.get(quote_id, for_update=True)
        if quote.status != "accepted":
            raise BusinessRuleViolation("QUOTE_NOT_ACCEPTED", "Only accepted quotes become orders")
        if quote.order_id is not None:
            return await self.orders.get(quote.order_id)
        lines = (
            await self.session.scalars(
                self.quote_lines.select()
                .where(QuoteLine.quote_id == quote.id)
                .order_by(QuoteLine.position)
            )
        ).all()
        if any(x.quantity != x.quantity.to_integral_value() for x in lines):
            raise BusinessRuleViolation(
                "FRACTIONAL_QUANTITY", "Order quantities must be whole units"
            )
        order = await self.orders.add(
            self.orders.new(
                number=await next_number(self.session, self.scope, "order"),
                customer_id=quote.customer_id,
                quote_id=quote.id,
                source="quote",
                currency=quote.currency,
                notes=quote.notes,
                created_by_label=self.scope.actor_label[:80],
                subtotal=quote.subtotal,
                discount_total=quote.discount_total,
                tax_rate=quote.tax_rate,
                tax_total=quote.tax_total,
                total=quote.total,
            )
        )
        variants = await CatalogService(self.session, self.scope).variants_by_ids(
            [x.variant_id for x in lines if x.variant_id]
        )
        # The accepted quote's agreed prices carry over.
        products = {
            p.id: p.offering_type
            for p in await self.session.scalars(
                WorkspaceRepository(self.session, CatalogProduct, self.scope)
                .select()
                .where(CatalogProduct.id.in_({v.product_id for v in variants.values()}))
            )
        }
        order.fulfillment_type = fulfillment_type(
            [
                products.get(variants[x.variant_id].product_id, "service")
                if x.variant_id in variants
                else "service"
                for x in lines
            ]
        )
        for line in lines:
            variant = variants.get(line.variant_id) if line.variant_id else None
            self.session.add(
                self.lines.new(
                    order_id=order.id,
                    variant_id=line.variant_id,
                    position=line.position,
                    sku=variant.sku if variant else None,
                    description=line.description,
                    quantity=int(line.quantity),
                    unit_price=line.unit_price,
                    discount=line.discount,
                    line_total=line.line_total,
                )
            )
        quote.order_id = order.id
        await self.session.flush()
        await log_activity(
            self.session,
            self.scope,
            order.customer_id,
            "order",
            f"Order {order.number} created from quote {quote.number}",
            "order",
            order.id,
        )
        await record(
            self.session,
            "order.created_from_quote",
            scope=self.scope,
            entity_type="order",
            entity_id=order.id,
            details={"quote": quote.number},
        )
        await emit(self.session, self.scope, "order.created", _order_payload(order), _ref(order))
        return order

    async def transition(self, order_id: UUID, action: str) -> Order:
        target = ACTION_TARGET.get(action)
        if target is None:
            raise BusinessRuleViolation("UNKNOWN_ACTION", "Unknown order action")
        self.scope.require("orders.cancel" if action == "cancel" else "orders.write")
        order = await self.orders.get(order_id, for_update=True)
        if not action_applies(order, action):
            raise BusinessRuleViolation(
                "FULFILLMENT_ACTION_INVALID",
                "This action does not apply to this order's fulfillment",
            )
        ORDER_STATES.ensure(order.status, target)
        previous = order.status
        lines = await self.lines_for(order.id)
        if target == "confirmed":
            await self._confirm_effects(order, lines)
        if target == "cancelled":
            await self._cancel_effects(order, previous, lines)
        order.status = target
        await self.session.flush()
        await log_activity(
            self.session,
            self.scope,
            order.customer_id,
            "order",
            f"Order {order.number}: {previous} → {target}",
            "order",
            order.id,
        )
        await record(
            self.session,
            f"order.{action}",
            scope=self.scope,
            entity_type="order",
            entity_id=order.id,
            details={"from": previous, "to": target, "total": str(order.total)},
        )
        event = ORDER_EVENTS.get(target)
        if event:
            await emit(self.session, self.scope, event, _order_payload(order), _ref(order))
        return order

    async def _confirm_effects(self, order: Order, lines: list[OrderLine]) -> None:
        if not lines:
            raise BusinessRuleViolation("EMPTY_ORDER", "An order needs at least one item")
        catalog = CatalogService(self.session, self.scope)
        inventory = InventoryService(self.session, self.scope)
        for line in lines:
            if line.variant_id is None:
                continue
            variant, _product = await catalog.sellable_variant(line.variant_id)
            # A draft never silently confirms at a price the customer did not see.
            if order.source != "quote" and variant.price != line.unit_price:
                raise BusinessRuleViolation(
                    "PRICE_CHANGED", "A price changed since this draft; review the order"
                )
            if variant.track_inventory:
                await inventory.move(
                    variant.id,
                    -line.quantity,
                    "sale",
                    f"Order {order.number}",
                    ref_type="order",
                    ref_id=order.id,
                    idempotency_key=f"order:{order.id}:line:{line.id}:sale",
                )
        order.confirmed_at = datetime.now(UTC)
        settings = await get_settings_row(self.session, self.scope)
        if settings.auto_invoice_on_order_confirm:
            await BillingService(self.session, self.scope).create_from_order(order, lines)

    async def _cancel_effects(self, order: Order, previous: str, lines: list[OrderLine]) -> None:
        billing = BillingService(self.session, self.scope)
        await billing.void_for_order(order.id)  # raises when payments exist
        if previous in STOCK_DEDUCTED:
            inventory = InventoryService(self.session, self.scope)
            for line in lines:
                if line.variant_id is None:
                    continue
                sale = await inventory.movements.find(
                    inventory.movements.model.idempotency_key
                    == f"order:{order.id}:line:{line.id}:sale"
                )
                if sale is None:
                    continue
                await inventory.move(
                    line.variant_id,
                    line.quantity,
                    "return",
                    f"Cancelled order {order.number}",
                    location_id=sale.location_id,
                    ref_type="order",
                    ref_id=order.id,
                    idempotency_key=f"order:{order.id}:line:{line.id}:return",
                )
        order.cancelled_at = datetime.now(UTC)
