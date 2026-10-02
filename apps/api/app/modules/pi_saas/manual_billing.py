"""PKR bank/cash collection. A customer claim never grants paid entitlement.

Amounts/instructions are immutable snapshots. An authorized operator verifies receipt
of money; the payment, invoice, subscription extension and audit commit together. Locks
serialize reviews and renewals. Unique references prevent reuse across businesses.
"""

import calendar
import hashlib
import html
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.pi_saas.billing import account_name, send_billing_email, subscription_for
from app.modules.pi_saas.models import PiBusinessAccount, PiPlan, PiPlatformInvoice
from app.modules.pi_saas.payment_models import (
    PiCheckoutAttempt,
    PiCollectionSettings,
    PiManualPayment,
)
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

PENDING = ("awaiting_payment", "submitted")


class CollectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    seller_name: str = Field(default="", max_length=160)
    seller_address: str = Field(default="", max_length=400)
    support_email: str = Field(default="", max_length=200)
    bank_enabled: bool = False
    bank_name: str = Field(default="", max_length=120)
    account_title: str = Field(default="", max_length=160)
    iban: str = Field(default="", max_length=40)
    bank_instructions: str = Field(default="", max_length=500)
    cash_enabled: bool = False
    cash_instructions: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_details(self) -> "CollectionConfig":
        self.iban = re.sub(r"\s+", "", self.iban).upper()
        if self.iban:
            if not re.fullmatch(r"PK[0-9]{2}[A-Z]{4}[A-Z0-9]{16}", self.iban):
                raise ValueError("Enter a 24-character Pakistan IBAN")
            rearranged = self.iban[4:] + self.iban[:4]
            digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
            if int(digits) % 97 != 1:
                raise ValueError("The IBAN checksum is invalid")
        if (self.bank_enabled or self.cash_enabled) and not self.seller_name:
            raise ValueError("Enter the business name that collects payments")
        if self.bank_enabled and not all((self.bank_name, self.account_title, self.iban)):
            raise ValueError("Bank name, account title and a valid Pakistan IBAN are required")
        if self.cash_enabled and not self.cash_instructions:
            raise ValueError("Explain where and to whom customers should pay cash")
        return self


class PaymentChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_key: UUID
    plan: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")
    method: Literal["bank_transfer", "cash"]
    months: Literal[1, 3, 6, 12] = 1


class PaymentSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    payer_name: str = Field(min_length=2, max_length=160)
    reference: str = Field(default="", max_length=120)
    paid_on: date
    note: str = Field(default="", max_length=500)


async def collection_config(session: AsyncSession) -> CollectionConfig:
    row = await session.scalar(
        select(PiCollectionSettings).where(PiCollectionSettings.key == "platform")
    )
    return CollectionConfig.model_validate(row.config if row else {})


async def payment_for(
    session: AsyncSession, tenant_id: UUID, payment_id: UUID, *, lock: bool = False
) -> PiManualPayment:
    query = select(PiManualPayment).where(
        PiManualPayment.id == payment_id, PiManualPayment.tenant_id == tenant_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(query)
    if row is None:
        raise ResourceNotFound
    return row


def payment_view(row: PiManualPayment) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "plan": row.plan_key,
        "plan_name": row.plan_name,
        "method": row.method,
        "status": row.status,
        "months": row.months,
        "amount": str(row.amount),
        "currency": row.currency,
        "instructions": row.instructions,
        "payer_name": row.payer_name,
        "reference": row.reference,
        "paid_on": row.paid_on,
        "note": row.note,
        "has_proof": bool(row.proof_type),
        "review_note": row.review_note,
        "receipt_number": row.receipt_number,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "refunded_at": row.refunded_at,
        "refund_reference": row.refund_reference,
        "refund_reason": row.refund_reason,
    }


async def audit(
    session: AsyncSession, row: PiManualPayment, actor: UUID | None, action: str, **details: Any
) -> None:
    await record(
        session,
        f"pi_billing.{action}",
        tenant_id=row.tenant_id,
        actor_user_id=actor,
        entity_type="pi_manual_payment",
        entity_id=row.id,
        include_environment=False,
        details={
            "method": row.method,
            "amount": str(row.amount),
            "currency": row.currency,
            **details,
        },
    )


async def create_payment(
    session: AsyncSession, account: PiBusinessAccount, actor: UUID, data: PaymentChoice
) -> PiManualPayment:
    sub = await subscription_for(session, account.tenant_id)
    existing = await session.scalar(
        select(PiManualPayment).where(
            PiManualPayment.tenant_id == account.tenant_id,
            PiManualPayment.request_key == data.request_key,
        )
    )
    if existing:
        if (existing.plan_key, existing.method, existing.months) != (
            data.plan,
            data.method,
            data.months,
        ):
            raise BusinessRuleViolation(
                "IDEMPOTENCY_CONFLICT", "This request was already used for a different payment", 409
            )
        return existing
    now = datetime.now(UTC)
    if sub.external_subscription_id and sub.status != "canceled":
        raise BusinessRuleViolation(
            "STRIPE_SUBSCRIPTION_EXISTS",
            "Manage your existing card subscription before switching payment methods",
            409,
        )
    attempt = await session.scalar(
        select(PiCheckoutAttempt.id).where(
            PiCheckoutAttempt.tenant_id == account.tenant_id,
            PiCheckoutAttempt.status.in_(
                ["creating", "open"]
                if sub.external_subscription_id and sub.status == "canceled"
                else ["creating", "open", "complete"]
            ),
        )
    )
    if attempt:
        raise BusinessRuleViolation(
            "CHECKOUT_PENDING",
            "A card checkout is pending. Reopen it to finish or confirm its expiry first",
            409,
        )
    pending = await session.scalar(
        select(PiManualPayment.id).where(
            PiManualPayment.tenant_id == account.tenant_id, PiManualPayment.status.in_(PENDING)
        )
    )
    if pending:
        raise BusinessRuleViolation(
            "PAYMENT_PENDING",
            "You have a pending payment. Open it below or cancel it before creating another",
            409,
        )
    plan = await session.scalar(
        select(PiPlan).where(PiPlan.key == data.plan, PiPlan.status == "available")
    )
    if plan is None or plan.manual_monthly_price_pkr is None or plan.manual_monthly_price_pkr <= 0:
        raise BusinessRuleViolation(
            "PKR_PRICE_MISSING", "A PKR price has not been set for this plan", 409
        )
    if (
        sub.status == "active"
        and sub.current_period_end
        and sub.current_period_end > now
        and sub.plan_key != data.plan
    ):
        raise BusinessRuleViolation(
            "PAID_PLAN_CHANGE",
            "Renew your current plan, or change plans after your paid period ends",
            409,
        )
    config = await collection_config(session)
    if not (config.bank_enabled if data.method == "bank_transfer" else config.cash_enabled):
        raise BusinessRuleViolation(
            "METHOD_UNAVAILABLE", "This payment method is not available yet", 409
        )
    instructions = {
        k: v
        for k, v in config.model_dump().items()
        if k in {"seller_name", "seller_address", "support_email"}
        or k
        in (
            {"bank_name", "account_title", "iban", "bank_instructions"}
            if data.method == "bank_transfer"
            else {"cash_instructions"}
        )
    }
    amount = plan.manual_monthly_price_pkr * data.months
    if amount > Decimal("9999999999.99"):
        raise BusinessRuleViolation("AMOUNT_TOO_LARGE", "This payment exceeds the supported amount")
    invoice = PiPlatformInvoice(
        tenant_id=account.tenant_id,
        number=f"PI-INV-{uuid4().hex[:16].upper()}",
        status="open",
        amount_due=amount,
        amount_paid=Decimal(0),
        currency="PKR",
    )
    session.add(invoice)
    await session.flush()
    row = PiManualPayment(
        tenant_id=account.tenant_id,
        request_key=data.request_key,
        plan_key=plan.key,
        plan_name=plan.name,
        method=data.method,
        months=data.months,
        amount=amount,
        currency="PKR",
        instructions=instructions,
        created_by=actor,
        invoice_id=invoice.id,
    )
    session.add(row)
    await session.flush()
    await audit(session, row, actor, "payment_requested", plan=plan.key, months=data.months)
    return row


async def submit_payment(
    session: AsyncSession,
    tenant_id: UUID,
    payment_id: UUID,
    actor: UUID | None,
    data: PaymentSubmission,
) -> PiManualPayment:
    await subscription_for(session, tenant_id)
    row = await payment_for(session, tenant_id, payment_id, lock=True)
    if row.status == "submitted":
        if (row.payer_name, row.reference, row.paid_on, row.note) == (
            data.payer_name,
            data.reference,
            data.paid_on,
            data.note,
        ):
            return row
        raise BusinessRuleViolation(
            "ALREADY_SUBMITTED", "This payment is already under review", 409
        )
    if row.status != "awaiting_payment":
        raise BusinessRuleViolation("PAYMENT_CLOSED", "This payment request is closed", 409)
    if data.paid_on > datetime.now(UTC).date() or data.paid_on < row.created_at.date() - timedelta(
        days=7
    ):
        raise BusinessRuleViolation("INVALID_PAYMENT_DATE", "Enter the actual recent payment date")
    if row.method == "bank_transfer":
        if len(data.reference) < 3:
            raise BusinessRuleViolation(
                "REFERENCE_REQUIRED", "Enter the bank transaction reference"
            )
        if not row.proof_type:
            raise BusinessRuleViolation(
                "PROOF_REQUIRED", "Upload the bank receipt before submitting"
            )
        normalized = re.sub(r"[^a-z0-9]", "", data.reference.casefold())
        if len(normalized) < 3:
            raise BusinessRuleViolation(
                "REFERENCE_REQUIRED", "Enter the bank transaction reference"
            )
        digest = hashlib.sha256(
            f"{row.instructions.get('iban', '')}:{normalized}".encode()
        ).hexdigest()
        # A transaction reference can only be submitted once, including across tenants.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest[:15], 16)}
        )
        if await session.scalar(
            select(PiManualPayment.id).where(PiManualPayment.reference_key == digest)
        ):
            raise BusinessRuleViolation(
                "REFERENCE_ALREADY_USED",
                "This transaction reference has already been submitted. Contact billing support",
                409,
            )
        row.reference_key = digest
    row.payer_name, row.reference, row.paid_on, row.note = (
        data.payer_name,
        data.reference,
        data.paid_on,
        data.note,
    )
    row.status, row.submitted_at = "submitted", datetime.now(UTC)
    await audit(session, row, actor, "payment_submitted")
    return row


def add_months(value: datetime, count: int) -> datetime:
    month = value.month - 1 + count
    year = value.year + month // 12
    month = month % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


async def decide_payment(
    session: AsyncSession,
    tenant_id: UUID,
    payment_id: UUID,
    actor: UUID,
    action: str,
    note: str,
    *,
    settings: Settings | None = None,
    http: httpx.AsyncClient | None = None,
) -> PiManualPayment:
    sub = await subscription_for(session, tenant_id)
    row = await payment_for(session, tenant_id, payment_id, lock=True)
    target = "approved" if action == "approve" else "rejected"
    if row.status == target:
        return row
    if row.status != "submitted":
        raise BusinessRuleViolation(
            "PAYMENT_NOT_SUBMITTED", "Only a submitted payment can be reviewed", 409
        )
    invoice = await session.get(PiPlatformInvoice, row.invoice_id)
    assert invoice is not None
    if action == "approve":
        if sub.external_subscription_id and sub.status != "canceled":
            raise BusinessRuleViolation(
                "STRIPE_SUBSCRIPTION_EXISTS",
                "Resolve the existing card subscription before approving a manual payment",
                409,
            )
        now = datetime.now(UTC)
        current_end = sub.current_period_end if sub.status == "active" else None
        if current_end and current_end > now and sub.plan_key != row.plan_key:
            raise BusinessRuleViolation(
                "PAID_PLAN_CHANGE",
                "The paid plan changed while this payment was being reviewed",
                409,
            )
        start = max(now, current_end or now)
        row.previous_period_end = current_end
        row.period_start, row.period_end = start, add_months(start, row.months)
        row.receipt_number = f"PI-RCPT-{row.id.hex[:16].upper()}"
        sub.plan_key, sub.pending_plan_key = row.plan_key, None
        sub.status, sub.billing_provider, sub.currency = "active", "manual", "PKR"
        sub.current_period_start = (
            sub.current_period_start if current_end and current_end > now else start
        )
        sub.current_period_end, sub.grace_ends_at = row.period_end, row.period_end
        sub.cancel_at_period_end, sub.canceled_at = False, None
        # Fence delayed Stripe events from a previous, canceled subscription.
        sub.last_event_at = now
        invoice.status, invoice.amount_paid = "paid", row.amount
        invoice.period_start, invoice.period_end = row.period_start, row.period_end
    else:
        invoice.status = "void"
    row.status, row.review_note, row.reviewed_at, row.reviewed_by = (
        target,
        note,
        datetime.now(UTC),
        actor,
    )
    await audit(session, row, actor, f"payment_{target}", reason=note)
    if action == "approve" and settings is not None:
        business = await account_name(session, tenant_id)
        await send_billing_email(
            session,
            settings,
            http,
            tenant_id,
            "pi_payment_receipt",
            {
                "business": business,
                "plan": row.plan_name,
                "amount": f"PKR {row.amount:,.2f}",
                "receipt": row.receipt_number or "",
                "period": (
                    f"{row.period_start:%d %b %Y} to {row.period_end:%d %b %Y}"
                    if row.period_start and row.period_end
                    else ""
                ),
            },
        )
    return row


async def cancel_payment(
    session: AsyncSession, tenant_id: UUID, payment_id: UUID, actor: UUID
) -> PiManualPayment:
    await subscription_for(session, tenant_id)
    row = await payment_for(session, tenant_id, payment_id, lock=True)
    if row.status == "cancelled":
        return row
    if row.status != "awaiting_payment":
        raise BusinessRuleViolation(
            "PAYMENT_UNDER_REVIEW", "A submitted payment must be reviewed by the billing team", 409
        )
    row.status = "cancelled"
    invoice = await session.get(PiPlatformInvoice, row.invoice_id)
    assert invoice is not None
    invoice.status = "void"
    await audit(session, row, actor, "payment_cancelled")
    return row


async def refund_payment(
    session: AsyncSession,
    tenant_id: UUID,
    payment_id: UUID,
    actor: UUID,
    reference: str,
    reason: str,
) -> PiManualPayment:
    """Record a full cash/bank refund already paid outside the app; sends no money."""
    sub = await subscription_for(session, tenant_id)
    row = await payment_for(session, tenant_id, payment_id, lock=True)
    if row.status == "refunded":
        if row.refund_reference != reference:
            raise BusinessRuleViolation(
                "ALREADY_REFUNDED", "This refund has already been recorded", 409
            )
        return row
    if row.status != "approved":
        raise BusinessRuleViolation("NOT_PAID", "Only a verified payment can be refunded", 409)
    if sub.billing_provider != "manual" or sub.current_period_end != row.period_end:
        raise BusinessRuleViolation(
            "LATER_RENEWAL_EXISTS", "Resolve later renewals before refunding this payment", 409
        )
    now = datetime.now(UTC)
    sub.current_period_end = row.previous_period_end or now
    sub.grace_ends_at = sub.current_period_end
    sub.status = "active" if sub.current_period_end > now else "past_due"
    row.status, row.refunded_at = "refunded", now
    row.refund_reference, row.refund_reason = reference, reason
    await audit(session, row, actor, "refund_recorded", reason=reason)
    return row


def receipt_html(row: PiManualPayment, business_name: str) -> str:
    if row.status not in {"approved", "refunded"}:
        raise BusinessRuleViolation(
            "RECEIPT_NOT_READY", "A receipt is available after payment verification", 409
        )

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    fields = [
        ("Receipt", row.receipt_number),
        ("Business", business_name),
        ("Plan", row.plan_name),
        ("Amount received", f"PKR {row.amount:,.2f}"),
        ("Method", row.method.replace("_", " ")),
        ("Payer", row.payer_name),
        ("Payment reference", row.reference or "Cash receipt"),
        ("Payment date", row.paid_on),
        ("Verified", row.reviewed_at),
        ("Service period", f"{row.period_start:%d %b %Y} to {row.period_end:%d %b %Y}"),
        ("Status", row.status),
        ("Refund reference", row.refund_reference),
    ]
    rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in fields if v)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pi receipt {esc(row.receipt_number)}</title><style>
body{{font:16px system-ui;color:#1f2320;max-width:760px;margin:48px auto;padding:24px}}
h1{{color:#245d49}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}}
th{{width:34%}}.hint{{color:#666;font-size:13px}}
@media print{{.hint{{display:none}}body{{margin:0}}}}</style>
<h1>Payment receipt</h1><h2>{esc(row.instructions.get("seller_name"))}</h2>
<p>{esc(row.instructions.get("seller_address"))}</p><table>{rows}</table>
<p>{esc(row.instructions.get("support_email"))}</p>
<p class="hint">Use your browser's Print option to print or save this receipt as a PDF.</p>
</html>"""
