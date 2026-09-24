from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.audit.service import record
from app.modules.business_settings.service import get_settings_row
from app.modules.catalog.service import CatalogService
from app.modules.customers.models import Customer
from app.modules.customers.service import log_activity
from app.modules.quotes.models import Quote, QuoteLine
from app.modules.quotes.schemas import (
    QuoteCreate,
    QuoteDetail,
    QuoteLineInput,
    QuoteLineView,
    QuoteListItem,
    QuoteUpdate,
    QuoteView,
)
from app.modules.sales.models import SalesLead
from app.shared.errors import BusinessRuleViolation
from app.shared.money import compute_totals, quantize
from app.shared.scope import WorkspaceScope
from app.shared.sequences import next_number
from app.shared.state_machine import StateMachine
from app.shared.workspace_repository import WorkspaceRepository, like_pattern

QUOTE_STATES = StateMachine(
    "quote",
    {
        "draft": frozenset({"pending_approval", "approved", "cancelled"}),
        "pending_approval": frozenset({"approved", "draft", "cancelled"}),
        "approved": frozenset({"sent", "draft", "cancelled"}),
        "sent": frozenset({"accepted", "rejected", "expired", "cancelled"}),
        "accepted": frozenset(),
        "rejected": frozenset(),
        "expired": frozenset(),
        "cancelled": frozenset(),
    },
)
ACTIONS = {
    "draft": ["submit", "cancel"],
    "pending_approval": ["approve", "return_to_draft", "cancel"],
    "approved": ["send", "return_to_draft", "cancel"],
    "sent": ["accept", "reject", "expire", "cancel"],
    "accepted": ["convert_to_order"],
}


class QuoteService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.quotes = WorkspaceRepository(session, Quote, scope)
        self.lines = WorkspaceRepository(session, QuoteLine, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)
        self.leads = WorkspaceRepository(session, SalesLead, scope)

    async def search(
        self,
        page: Pagination,
        status: str | None = None,
        customer_id: UUID | None = None,
        search: str | None = None,
    ) -> Page[QuoteListItem]:
        statement = self.quotes.select()
        if status:
            statement = statement.where(Quote.status == status)
        if customer_id:
            statement = statement.where(Quote.customer_id == customer_id)
        if search:
            statement = statement.where(Quote.number.ilike(like_pattern(search.strip())))
        statement = statement.order_by(Quote.created_at.desc(), Quote.id)
        rows, total = await self.quotes.page(statement, page)
        names = await self._names({r.customer_id for r in rows})
        items = [
            QuoteListItem(
                **QuoteView.model_validate(r).model_dump(), customer_name=names.get(r.customer_id)
            )
            for r in rows
        ]
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    async def _names(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(
            select(Customer.id, Customer.name).where(
                self.customers.predicate(), Customer.id.in_(ids)
            )
        )
        return {i: n for i, n in rows}

    async def detail(self, quote_id: UUID) -> QuoteDetail:
        quote = await self.quotes.get(quote_id)
        lines = await self.session.scalars(
            self.lines.select().where(QuoteLine.quote_id == quote.id).order_by(QuoteLine.position)
        )
        names = await self._names({quote.customer_id})
        return QuoteDetail(
            **QuoteView.model_validate(quote).model_dump(),
            customer_name=names.get(quote.customer_id),
            lines=[QuoteLineView.model_validate(line) for line in lines],
            next_actions=[
                a
                for a in ACTIONS.get(quote.status, [])
                if not (a == "convert_to_order" and quote.order_id)
            ],
        )

    async def _price_lines(
        self, quote: Quote, inputs: list[QuoteLineInput], allow_custom: bool
    ) -> None:
        settings = await get_settings_row(self.session, self.scope)
        catalog = CatalogService(self.session, self.scope)
        priced: list[tuple[UUID | None, str, Decimal, Decimal, Decimal]] = []
        for item in inputs:
            if item.variant_id is not None:
                variant, product = await catalog.sellable_variant(item.variant_id)
                if variant.currency != quote.currency:
                    raise BusinessRuleViolation(
                        "CURRENCY_MISMATCH", "All quote items must use the quote currency"
                    )
                description = item.description or f"{product.name} — {variant.name}"
                priced.append(
                    (variant.id, description, item.quantity, variant.price, item.discount)
                )
            else:
                if not allow_custom:
                    raise BusinessRuleViolation(
                        "CUSTOM_PRICE_NOT_ALLOWED", "Custom-priced lines need a team member"
                    )
                assert item.unit_price is not None and item.description
                priced.append(
                    (None, item.description, item.quantity, item.unit_price, item.discount)
                )
        try:
            line_totals, totals = compute_totals(
                [(q, p, d) for _, _, q, p, d in priced], settings.tax_rate
            )
        except ValueError:
            raise BusinessRuleViolation("INVALID_DISCOUNT", "A discount exceeds its line") from None
        await self.session.execute(
            delete(QuoteLine).where(
                QuoteLine.tenant_id == self.scope.tenant_id,
                QuoteLine.environment_id == self.scope.environment_id,
                QuoteLine.quote_id == quote.id,
            )
        )
        for position, ((variant_id, description, qty, price, discount), total) in enumerate(
            zip(priced, line_totals, strict=True), start=1
        ):
            self.session.add(
                self.lines.new(
                    quote_id=quote.id,
                    variant_id=variant_id,
                    position=position,
                    description=description[:300],
                    quantity=qty,
                    unit_price=price,
                    discount=quantize(discount),
                    line_total=total,
                )
            )
        quote.subtotal, quote.discount_total = totals.subtotal, totals.discount_total
        quote.tax_rate, quote.tax_total, quote.total = (
            settings.tax_rate,
            totals.tax_total,
            totals.total,
        )
        discount_rate = (
            totals.discount_total / totals.subtotal if totals.subtotal > 0 else Decimal("0")
        )
        threshold = settings.quote_approval_threshold
        quote.requires_approval = (
            discount_rate > settings.max_discount_rate
            or (threshold is not None and totals.total > threshold)
            or quote.source == "pi"
        )
        await self.session.flush()

    async def create(self, data: QuoteCreate, source: str = "manual") -> Quote:
        self.scope.require("quotes.write")
        await self.customers.get(data.customer_id)
        if data.lead_id:
            await self.leads.get(data.lead_id)
        settings = await get_settings_row(self.session, self.scope)
        valid_until = data.valid_until or (
            date.today() + timedelta(days=settings.quote_validity_days)
        )
        if valid_until < date.today():
            raise BusinessRuleViolation("INVALID_VALIDITY", "Validity date must be in the future")
        quote = await self.quotes.add(
            self.quotes.new(
                number=await next_number(self.session, self.scope, "quote"),
                customer_id=data.customer_id,
                lead_id=data.lead_id,
                source=source,
                currency=settings.default_currency,
                valid_until=valid_until,
                notes=data.notes,
            )
        )
        await self._price_lines(quote, data.lines, allow_custom=source == "manual")
        await log_activity(
            self.session,
            self.scope,
            quote.customer_id,
            "quote",
            f"Quote {quote.number} drafted",
            "quote",
            quote.id,
        )
        await record(
            self.session,
            "quote.created",
            scope=self.scope,
            entity_type="quote",
            entity_id=quote.id,
            details={"number": quote.number, "total": str(quote.total), "source": source},
        )
        return quote

    async def update(self, quote_id: UUID, data: QuoteUpdate) -> Quote:
        self.scope.require("quotes.write")
        quote = await self.quotes.get(quote_id, for_update=True)
        if quote.status != "draft":
            raise BusinessRuleViolation("QUOTE_LOCKED", "Only draft quotes can be edited")
        if data.valid_until is not None:
            if data.valid_until < date.today():
                raise BusinessRuleViolation(
                    "INVALID_VALIDITY", "Validity date must be in the future"
                )
            quote.valid_until = data.valid_until
        if data.notes is not None:
            quote.notes = data.notes
        if data.lines is not None:
            await self._price_lines(quote, data.lines, allow_custom=quote.source == "manual")
        await self.session.flush()
        await record(
            self.session,
            "quote.updated",
            scope=self.scope,
            entity_type="quote",
            entity_id=quote.id,
            details={"total": str(quote.total)},
        )
        return quote

    async def transition(self, quote_id: UUID, action: str) -> Quote:
        quote = await self.quotes.get(quote_id, for_update=True)
        target = {
            "submit": "pending_approval" if quote.requires_approval else "approved",
            "approve": "approved",
            "return_to_draft": "draft",
            "send": "sent",
            "accept": "accepted",
            "reject": "rejected",
            "expire": "expired",
            "cancel": "cancelled",
        }.get(action)
        if target is None:
            raise BusinessRuleViolation("UNKNOWN_ACTION", "Unknown quote action")
        self.scope.require("quotes.approve" if action == "approve" else "quotes.write")
        if action == "submit" and quote.status != "draft":
            raise BusinessRuleViolation("INVALID_TRANSITION", "Only drafts can be submitted")
        if action == "send" and quote.valid_until < date.today():
            raise BusinessRuleViolation("QUOTE_EXPIRED", "This quote's validity date has passed")
        QUOTE_STATES.ensure(quote.status, target)
        previous, quote.status = quote.status, target
        now = datetime.now(UTC)
        if target == "approved":
            quote.approved_by_user_id, quote.approved_at = self.scope.user_id, now
        if target == "sent":
            quote.sent_at = now
        if target == "draft":
            quote.approved_by_user_id = quote.approved_at = None
        await self.session.flush()
        await log_activity(
            self.session,
            self.scope,
            quote.customer_id,
            "quote",
            f"Quote {quote.number}: {previous} → {target}",
            "quote",
            quote.id,
        )
        await record(
            self.session,
            f"quote.{action}",
            scope=self.scope,
            entity_type="quote",
            entity_id=quote.id,
            details={"from": previous, "to": target},
        )
        return quote
