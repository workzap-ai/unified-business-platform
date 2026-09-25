from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.integrations.outbox import EntityRef, emit
from app.modules.audit.service import record
from app.modules.billing.models import Invoice, InvoiceLine, Payment
from app.modules.billing.schemas import (
    BillingSummary,
    InvoiceCreate,
    InvoiceDetail,
    InvoiceLineView,
    InvoiceListItem,
    InvoiceView,
    PaymentCreate,
    PaymentView,
)
from app.modules.business_settings.service import get_settings_row
from app.modules.customers.models import Customer
from app.modules.customers.service import log_activity
from app.modules.orders.models import Order, OrderLine
from app.shared.errors import BusinessRuleViolation
from app.shared.money import compute_totals, quantize
from app.shared.scope import WorkspaceScope
from app.shared.sequences import next_number
from app.shared.state_machine import StateMachine
from app.shared.workspace_repository import WorkspaceRepository, like_pattern, to_page

INVOICE_STATES = StateMachine(
    "invoice",
    {
        "draft": frozenset({"issued", "void"}),
        "issued": frozenset({"partially_paid", "paid", "void"}),
        "partially_paid": frozenset({"paid"}),
        "paid": frozenset(),
        "void": frozenset(),
    },
)
OPEN_STATUSES = ("issued", "partially_paid")


def balance(invoice: Invoice) -> Decimal:
    return quantize(invoice.total - invoice.amount_paid)


def _invoice_payload(invoice: Invoice) -> dict[str, str | None]:
    return {
        "invoice_id": str(invoice.id),
        "number": invoice.number,
        "status": invoice.status,
        "customer_id": str(invoice.customer_id) if invoice.customer_id else None,
        "order_id": str(invoice.order_id) if invoice.order_id else None,
        "total": str(invoice.total),
        "amount_paid": str(invoice.amount_paid),
        "currency": invoice.currency,
    }


class BillingService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.invoices = WorkspaceRepository(session, Invoice, scope)
        self.lines = WorkspaceRepository(session, InvoiceLine, scope)
        self.payments = WorkspaceRepository(session, Payment, scope)
        self.customers = WorkspaceRepository(session, Customer, scope)

    def _item(self, invoice: Invoice, customer_name: str | None) -> InvoiceListItem:
        overdue = (
            invoice.status in OPEN_STATUSES
            and invoice.due_date is not None
            and invoice.due_date < date.today()
        )
        return InvoiceListItem(
            **InvoiceView.model_validate(invoice).model_dump(),
            customer_name=customer_name,
            balance_due=balance(invoice),
            is_overdue=overdue,
        )

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
        overdue: bool = False,
        search: str | None = None,
    ) -> Page[InvoiceListItem]:
        statement = self.invoices.select()
        if status:
            statement = statement.where(Invoice.status == status)
        if customer_id:
            statement = statement.where(Invoice.customer_id == customer_id)
        if overdue:
            statement = statement.where(
                Invoice.status.in_(OPEN_STATUSES), Invoice.due_date < date.today()
            )
        if search:
            statement = statement.where(Invoice.number.ilike(like_pattern(search.strip())))
        statement = statement.order_by(Invoice.created_at.desc(), Invoice.id)
        rows, total = await self.invoices.page(statement, page)
        names = await self._names({r.customer_id for r in rows})
        items = [self._item(r, names.get(r.customer_id)) for r in rows]
        return Page(items=items, total=total, page=page.page, page_size=page.page_size)

    async def detail(self, invoice_id: UUID) -> InvoiceDetail:
        invoice = await self.invoices.get(invoice_id)
        lines = await self.session.scalars(
            self.lines.select()
            .where(InvoiceLine.invoice_id == invoice.id)
            .order_by(InvoiceLine.position)
        )
        payments = await self.session.scalars(
            self.payments.select()
            .where(Payment.invoice_id == invoice.id)
            .order_by(Payment.received_on, Payment.created_at)
        )
        names = await self._names({invoice.customer_id})
        actions = {
            "draft": ["issue", "void"],
            "issued": ["record_payment", "void"]
            if invoice.amount_paid == 0
            else ["record_payment"],
            "partially_paid": ["record_payment"],
        }.get(invoice.status, [])
        return InvoiceDetail(
            **self._item(invoice, names.get(invoice.customer_id)).model_dump(),
            lines=[InvoiceLineView.model_validate(x) for x in lines],
            payments=[PaymentView.model_validate(p) for p in payments],
            next_actions=actions,
        )

    async def create(self, data: InvoiceCreate) -> Invoice:
        self.scope.require("billing.write")
        await self.customers.get(data.customer_id)
        settings = await get_settings_row(self.session, self.scope)
        try:
            totals_by_line, totals = compute_totals(
                [(x.quantity, x.unit_price, x.discount) for x in data.lines], settings.tax_rate
            )
        except ValueError:
            raise BusinessRuleViolation("INVALID_DISCOUNT", "A discount exceeds its line") from None
        invoice = await self.invoices.add(
            self.invoices.new(
                number=await next_number(self.session, self.scope, "invoice"),
                customer_id=data.customer_id,
                currency=settings.default_currency,
                due_date=data.due_date,
                notes=data.notes,
                subtotal=totals.subtotal,
                discount_total=totals.discount_total,
                tax_total=totals.tax_total,
                total=totals.total,
            )
        )
        for position, (line, line_total) in enumerate(
            zip(data.lines, totals_by_line, strict=True), start=1
        ):
            self.session.add(
                self.lines.new(
                    invoice_id=invoice.id,
                    position=position,
                    description=line.description,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount=line.discount,
                    line_total=line_total,
                )
            )
        await self.session.flush()
        await record(
            self.session,
            "invoice.created",
            scope=self.scope,
            entity_type="invoice",
            entity_id=invoice.id,
            details={"number": invoice.number, "total": str(invoice.total)},
        )
        return invoice

    async def create_from_order(self, order: Order, lines: Sequence[OrderLine]) -> Invoice:
        """Issue an invoice for a confirmed order inside the order's transaction."""
        self.scope.require("billing.write")
        existing = await self.invoices.find(Invoice.order_id == order.id, Invoice.status != "void")
        if existing is not None:
            return existing
        settings = await get_settings_row(self.session, self.scope)
        today = date.today()
        invoice = await self.invoices.add(
            self.invoices.new(
                number=await next_number(self.session, self.scope, "invoice"),
                customer_id=order.customer_id,
                order_id=order.id,
                status="issued",
                issue_date=today,
                due_date=today + timedelta(days=settings.invoice_due_days),
                currency=order.currency,
                subtotal=order.subtotal,
                discount_total=order.discount_total,
                tax_total=order.tax_total,
                total=order.total,
            )
        )
        for line in lines:
            self.session.add(
                self.lines.new(
                    invoice_id=invoice.id,
                    variant_id=line.variant_id,
                    position=line.position,
                    description=line.description,
                    quantity=Decimal(line.quantity),
                    unit_price=line.unit_price,
                    discount=line.discount,
                    line_total=line.line_total,
                )
            )
        await self.session.flush()
        await log_activity(
            self.session,
            self.scope,
            order.customer_id,
            "invoice",
            f"Invoice {invoice.number} issued for {order.number}",
            "invoice",
            invoice.id,
        )
        await record(
            self.session,
            "invoice.issued_from_order",
            scope=self.scope,
            entity_type="invoice",
            entity_id=invoice.id,
            details={"order": order.number, "total": str(invoice.total)},
        )
        await emit(
            self.session,
            self.scope,
            "invoice.issued",
            _invoice_payload(invoice),
            EntityRef("invoice", invoice.id),
        )
        return invoice

    async def act(self, invoice_id: UUID, action: str) -> Invoice:
        self.scope.require("billing.write")
        invoice = await self.invoices.get(invoice_id, for_update=True)
        if action == "issue":
            INVOICE_STATES.ensure(invoice.status, "issued")
            invoice.status = "issued"
            invoice.issue_date = date.today()
            if invoice.due_date is None:
                settings = await get_settings_row(self.session, self.scope)
                invoice.due_date = date.today() + timedelta(days=settings.invoice_due_days)
        elif action == "void":
            if invoice.amount_paid > 0:
                raise BusinessRuleViolation(
                    "INVOICE_HAS_PAYMENTS", "Paid invoices cannot be voided"
                )
            INVOICE_STATES.ensure(invoice.status, "void")
            invoice.status, invoice.voided_at = "void", datetime.now(UTC)
        else:
            raise BusinessRuleViolation("UNKNOWN_ACTION", "Unknown invoice action")
        await self.session.flush()
        await record(
            self.session,
            f"invoice.{action}",
            scope=self.scope,
            entity_type="invoice",
            entity_id=invoice.id,
        )
        if action == "issue":
            await emit(
                self.session,
                self.scope,
                "invoice.issued",
                _invoice_payload(invoice),
                EntityRef("invoice", invoice.id),
            )
        return invoice

    async def void_for_order(self, order_id: UUID) -> None:
        invoice = await self.invoices.find(Invoice.order_id == order_id, Invoice.status != "void")
        if invoice is None:
            return
        await self.act(invoice.id, "void")

    async def record_payment(self, invoice_id: UUID, data: PaymentCreate) -> Payment:
        self.scope.require("billing.write")
        invoice = await self.invoices.get(invoice_id, for_update=True)
        if invoice.status not in OPEN_STATUSES:
            raise BusinessRuleViolation("INVOICE_NOT_OPEN", "Payments need an issued invoice")
        amount = quantize(data.amount)
        if amount > balance(invoice):
            raise BusinessRuleViolation("OVERPAYMENT", "Payment exceeds the balance due")
        payment = await self.payments.add(
            self.payments.new(
                invoice_id=invoice.id,
                number=await next_number(self.session, self.scope, "payment"),
                amount=amount,
                currency=invoice.currency,
                method=data.method,
                received_on=data.received_on or date.today(),
                reference=data.reference,
                recorded_by_label=self.scope.actor_label[:80],
            )
        )
        invoice.amount_paid = quantize(invoice.amount_paid + amount)
        target = "paid" if invoice.amount_paid == invoice.total else "partially_paid"
        if target != invoice.status:
            INVOICE_STATES.ensure(invoice.status, target)
            invoice.status = target
        await self.session.flush()
        await log_activity(
            self.session,
            self.scope,
            invoice.customer_id,
            "payment",
            f"Payment {payment.number} of {invoice.currency} {amount} on {invoice.number}",
            "payment",
            payment.id,
        )
        await record(
            self.session,
            "payment.recorded",
            scope=self.scope,
            entity_type="payment",
            entity_id=payment.id,
            details={"invoice": invoice.number, "amount": str(amount)},
        )
        await emit(
            self.session,
            self.scope,
            "payment.received",
            {
                "payment_id": str(payment.id),
                "number": payment.number,
                "invoice_id": str(invoice.id),
                "amount": str(amount),
                "currency": invoice.currency,
                "method": payment.method,
            },
            EntityRef("payment", payment.id),
        )
        if invoice.status == "paid":
            await emit(
                self.session,
                self.scope,
                "invoice.paid",
                _invoice_payload(invoice),
                EntityRef("invoice", invoice.id),
            )
        return payment

    async def payments_page(self, page: Pagination) -> Page[PaymentView]:
        statement = self.payments.select().order_by(Payment.received_on.desc(), Payment.id)
        rows, total = await self.payments.page(statement, page)
        return to_page(PaymentView, rows, total, page)

    async def customer_balance(self, customer_id: UUID) -> Decimal:
        value = await self.session.scalar(
            select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
                self.invoices.predicate(),
                Invoice.customer_id == customer_id,
                Invoice.status.in_(OPEN_STATUSES),
            )
        )
        return quantize(Decimal(value or 0))

    async def summary(self) -> BillingSummary:
        settings = await get_settings_row(self.session, self.scope)
        open_balance = Invoice.total - Invoice.amount_paid
        outstanding = await self.session.scalar(
            select(func.coalesce(func.sum(open_balance), 0)).where(
                self.invoices.predicate(),
                Invoice.status.in_(OPEN_STATUSES),
                Invoice.currency == settings.default_currency,
            )
        )
        overdue_row = (
            await self.session.execute(
                select(func.coalesce(func.sum(open_balance), 0), func.count()).where(
                    self.invoices.predicate(),
                    Invoice.status.in_(OPEN_STATUSES),
                    Invoice.due_date < date.today(),
                    Invoice.currency == settings.default_currency,
                )
            )
        ).one()
        month_start = date.today().replace(day=1)
        collected = await self.session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                self.payments.predicate(),
                Payment.received_on >= month_start,
                Payment.currency == settings.default_currency,
            )
        )
        drafts = await self.session.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(self.invoices.predicate(), Invoice.status == "draft")
        )
        return BillingSummary(
            currency=settings.default_currency,
            outstanding=quantize(Decimal(outstanding or 0)),
            overdue=quantize(Decimal(overdue_row[0] or 0)),
            overdue_count=int(overdue_row[1] or 0),
            collected_this_month=quantize(Decimal(collected or 0)),
            draft_count=int(drafts or 0),
        )
