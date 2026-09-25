from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Pagination
from app.modules.billing.service import BillingService
from app.modules.business_settings.service import BusinessSettingsView, get_settings_row
from app.modules.catalog.service import CatalogService
from app.modules.customers.schemas import CustomerView
from app.modules.customers.service import CustomerService
from app.modules.finance.service import FinanceService
from app.modules.hr.service import HRService
from app.modules.inventory.service import InventoryService
from app.modules.orders.schemas import OrderCreate
from app.modules.orders.service import OrderService
from app.modules.quotes.schemas import QuoteCreate
from app.modules.quotes.service import QuoteService
from app.modules.reports.service import ReportService
from app.modules.sales.service import SalesService
from app.shared.errors import PermissionDenied
from app.shared.scope import WorkspaceScope

ActionClass = Literal["READ", "DRAFT", "RECOMMEND", "APPROVAL_REQUIRED", "WRITE", "IRREVERSIBLE"]


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchInput(EmptyInput):
    query: str = Field(min_length=1, max_length=200)


class RecordInput(EmptyInput):
    id: UUID


@dataclass(frozen=True)
class ToolContext:
    session: AsyncSession
    scope: WorkspaceScope
    customer_id: UUID | None = None
    allowed_tools: frozenset[str] | None = None


@dataclass(frozen=True)
class Tool:
    key: str
    permission: str
    action_class: ActionClass
    schema: type[BaseModel]
    handler: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]
    customer_safe: bool = False
    preview: Callable[[ToolContext, Any], Awaitable[dict[str, Any]]] | None = None
    additional_permissions: tuple[str, ...] = ()

    def available(self, scope: WorkspaceScope) -> bool:
        return all(scope.can(p) for p in (self.permission, *self.additional_permissions))

    @property
    def approval_required(self) -> bool:
        return self.action_class in {"APPROVAL_REQUIRED", "WRITE", "IRREVERSIBLE"}


async def catalog(ctx: ToolContext, data: SearchInput) -> dict[str, Any]:
    rows = await CatalogService(ctx.session, ctx.scope).search_for_assistant(data.query)
    return {
        "offerings": [
            {
                "id": str(p.id),
                "name": p.name,
                "offering_type": p.offering_type,
                "description": p.description,
                "options": [
                    {
                        "id": str(v.id),
                        "name": v.name,
                        "price": str(v.price),
                        "currency": v.currency,
                        "tracked": v.track_inventory,
                    }
                    for v in variants
                ],
            }
            for p, variants in rows
        ]
    }


async def customer(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    if ctx.customer_id is not None and data.id != ctx.customer_id:
        raise PermissionDenied
    row = await CustomerService(ctx.session, ctx.scope).get(data.id)
    return CustomerView.model_validate(row).model_dump(mode="json")


async def order(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    row = await OrderService(ctx.session, ctx.scope).detail(data.id)
    if ctx.customer_id is not None and row.customer_id != ctx.customer_id:
        raise PermissionDenied
    return row.model_dump(mode="json")


async def invoice(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    row = await BillingService(ctx.session, ctx.scope).detail(data.id)
    if ctx.customer_id is not None and row.customer_id != ctx.customer_id:
        raise PermissionDenied
    return row.model_dump(mode="json")


async def draft_quote(ctx: ToolContext, data: QuoteCreate) -> dict[str, Any]:
    if ctx.customer_id is not None:
        if data.customer_id != ctx.customer_id:
            raise PermissionDenied
        for line in data.lines:
            if line.variant_id is None or line.discount:
                raise PermissionDenied
            _, offering = await CatalogService(ctx.session, ctx.scope).sellable_variant(
                line.variant_id
            )
            if not offering.pi_visible:
                raise PermissionDenied
    service = QuoteService(ctx.session, ctx.scope)
    row = await service.create(data, source="pi" if ctx.customer_id else "manual")
    return (await service.detail(row.id)).model_dump(mode="json")


async def confirm_order(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    service = OrderService(ctx.session, ctx.scope)
    row = await service.orders.get(data.id)
    if ctx.customer_id is not None and row.customer_id != ctx.customer_id:
        raise PermissionDenied
    await service.transition(data.id, "confirm")
    return (await service.detail(data.id)).model_dump(mode="json")


async def draft_order(ctx: ToolContext, data: OrderCreate) -> dict[str, Any]:
    if ctx.customer_id is not None:
        if data.customer_id != ctx.customer_id:
            raise PermissionDenied
        for line in data.lines:
            _, offering = await CatalogService(ctx.session, ctx.scope).sellable_variant(
                line.variant_id
            )
            if line.discount or not offering.pi_visible:
                raise PermissionDenied
    service = OrderService(ctx.session, ctx.scope)
    row = await service.create_draft(data, source="pi" if ctx.customer_id else "manual")
    return (await service.detail(row.id)).model_dump(mode="json")


async def overview(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (await ReportService(ctx.session, ctx.scope).overview()).model_dump(mode="json")


async def pipeline(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return {
        "stages": [
            x.model_dump(mode="json") for x in await SalesService(ctx.session, ctx.scope).pipeline()
        ]
    }


async def revenue(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (await ReportService(ctx.session, ctx.scope).revenue()).model_dump(mode="json")


async def employees(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (await HRService(ctx.session, ctx.scope).headcount()).model_dump(mode="json")


async def quotes(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (
        await QuoteService(ctx.session, ctx.scope).search(
            Pagination(page_size=20), status="pending_approval"
        )
    ).model_dump(mode="json")


async def billing_summary(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (await BillingService(ctx.session, ctx.scope).summary()).model_dump(mode="json")


async def customer_list(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (
        await CustomerService(ctx.session, ctx.scope).search(Pagination(page_size=20))
    ).model_dump(mode="json")


async def order_preview(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    await OrderService(ctx.session, ctx.scope).orders.get(data.id, for_update=True)
    return await order(ctx, data)


async def quote_preview(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    service = QuoteService(ctx.session, ctx.scope)
    await service.quotes.get(data.id, for_update=True)
    return (await service.detail(data.id)).model_dump(mode="json")


async def invoice_preview(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    await BillingService(ctx.session, ctx.scope).invoices.get(data.id, for_update=True)
    return await invoice(ctx, data)


async def convert_quote(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
    service = OrderService(ctx.session, ctx.scope)
    row = await service.create_from_quote(data.id)
    return (await service.detail(row.id)).model_dump(mode="json")


def transition_tool(module: str, action: str, permission: str) -> Tool:
    async def execute(ctx: ToolContext, data: RecordInput) -> dict[str, Any]:
        if module == "quotes":
            quotes = QuoteService(ctx.session, ctx.scope)
            await quotes.transition(data.id, action)
            return (await quotes.detail(data.id)).model_dump(mode="json")
        if module == "orders":
            orders = OrderService(ctx.session, ctx.scope)
            await orders.transition(data.id, action)
            return (await orders.detail(data.id)).model_dump(mode="json")
        invoices = BillingService(ctx.session, ctx.scope)
        await invoices.act(data.id, action)
        return (await invoices.detail(data.id)).model_dump(mode="json")

    return Tool(
        f"{module}.{action}",
        permission,
        "APPROVAL_REQUIRED",
        RecordInput,
        execute,
        preview={"quotes": quote_preview, "orders": order_preview, "billing": invoice_preview}[
            module
        ],
    )


async def finance(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    return (
        await FinanceService(ctx.session, ctx.scope).summary(today - timedelta(days=30), today)
    ).model_dump(mode="json")


async def inventory(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return (
        await InventoryService(ctx.session, ctx.scope).list_levels(
            Pagination(page_size=20), low_only=True
        )
    ).model_dump(mode="json")


async def administration(ctx: ToolContext, data: EmptyInput) -> dict[str, Any]:
    return BusinessSettingsView.model_validate(
        await get_settings_row(ctx.session, ctx.scope)
    ).model_dump(mode="json")


TOOLS = {
    tool.key: tool
    for tool in (
        Tool("catalog.search", "catalog.read", "READ", SearchInput, catalog, True),
        Tool("customers.get", "customers.read", "READ", RecordInput, customer, True),
        Tool("orders.get", "orders.read", "READ", RecordInput, order, True),
        Tool("billing.get", "billing.read", "READ", RecordInput, invoice, True),
        Tool("quotes.draft", "quotes.write", "DRAFT", QuoteCreate, draft_quote, True),
        Tool("orders.draft", "orders.write", "DRAFT", OrderCreate, draft_order, True),
        Tool(
            "orders.confirm",
            "orders.write",
            "APPROVAL_REQUIRED",
            RecordInput,
            confirm_order,
            True,
            preview=order_preview,
        ),
        Tool("overview.summary", "overview.read", "READ", EmptyInput, overview),
        Tool("sales.pipeline", "sales.read", "READ", EmptyInput, pipeline),
        Tool("reports.revenue", "billing.read", "READ", EmptyInput, revenue),
        Tool("hr.headcount", "hr.read", "READ", EmptyInput, employees),
        Tool("quotes.pending", "quotes.read", "READ", EmptyInput, quotes),
        Tool("finance.summary", "finance.read", "READ", EmptyInput, finance),
        Tool("inventory.low_stock", "inventory.read", "READ", EmptyInput, inventory),
        Tool("administration.settings", "settings.manage", "READ", EmptyInput, administration),
        Tool("billing.summary", "billing.read", "READ", EmptyInput, billing_summary),
        Tool("customers.recent", "customers.read", "READ", EmptyInput, customer_list),
        Tool(
            "quotes.convert",
            "quotes.write",
            "APPROVAL_REQUIRED",
            RecordInput,
            convert_quote,
            preview=quote_preview,
            additional_permissions=("orders.write",),
        ),
        *(
            transition_tool(
                "quotes", action, "quotes.approve" if action == "approve" else "quotes.write"
            )
            for action in (
                "submit",
                "approve",
                "return_to_draft",
                "send",
                "accept",
                "reject",
                "expire",
                "cancel",
            )
        ),
        *(
            transition_tool(
                "orders", action, "orders.cancel" if action == "cancel" else "orders.write"
            )
            for action in ("start_processing", "complete", "ship", "deliver", "cancel")
        ),
        *(transition_tool("billing", action, "billing.write") for action in ("issue", "void")),
    )
}
