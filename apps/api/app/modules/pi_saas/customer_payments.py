"""Customer payments for a business: Stripe, Pakistani bank transfer, wallets and cash.

Rules:
- The amount always comes from an issued invoice's open balance (core billing), never
  from a conversation or a model.
- Stripe uses the business's OWN Stripe connection (integrations platform); a payment
  counts only after the verified Stripe webhook settles the checkout.
- Bank transfer, wallet and cash payments count only when an authorized team member
  confirms the money arrived. A customer's "I paid" or screenshot moves a request to
  "awaiting verification", nothing more.
- Instructions are snapshotted per request, and every request has a unique reference the
  customer quotes, so transfers can be matched without trusting the customer's text.
"""

import re
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.billing.schemas import PaymentCreate
from app.modules.billing.service import BillingService
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.customer_payment_models import (
    PiCustomerPaymentSettings,
    PiPaymentRequest,
)
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

PAKISTAN_BANKS = (
    "Allied Bank",
    "Askari Bank",
    "Bank Al Habib",
    "Bank Alfalah",
    "BankIslami",
    "Faysal Bank",
    "Habib Bank Limited (HBL)",
    "Habib Metropolitan Bank",
    "JS Bank",
    "MCB Bank",
    "Meezan Bank",
    "National Bank of Pakistan",
    "Soneri Bank",
    "Standard Chartered Pakistan",
    "United Bank Limited (UBL)",
    "Other",
)
WALLETS = {
    "jazzcash": "JazzCash",
    "easypaisa": "Easypaisa",
    "sadapay": "SadaPay",
    "nayapay": "NayaPay",
}
BILLING_METHOD = {
    "stripe": "card",
    "bank_transfer": "bank_transfer",
    "mobile_wallet": "mobile_wallet",
    "cash": "cash",
}
OPEN = ("open", "awaiting_verification")
REQUEST_TTL = timedelta(days=7)
# Stripe Checkout sessions expire after 24 hours; the request expires with its link.
STRIPE_TTL = timedelta(hours=23)
# A customer saying they paid (any language we serve) or quoting a reference.
PROOF_WORDS = re.compile(
    r"\b(?:paid|sent|transferred|deposited|done|receipt|screenshot|trx|tid|transaction"
    r"|bhej\s*(?:diya|diye|di)|kar\s*(?:diya|di)|jama|ada\s*kar|payment\s*ho\s*gayi)\b"
    r"|بھیج|جمع|ادا|ارسلت|حولت|دفعت",
    re.IGNORECASE,
)
REFERENCE = re.compile(r"PAY-[A-Z0-9]{8}", re.IGNORECASE)
# Pakistani IBAN: PK + 2 check digits + 4 bank letters + 16 digits (24 characters).
PK_IBAN = re.compile(r"^PK\d{2}[A-Z]{4}\d{16}$")


def iban_valid(value: str) -> bool:
    """ISO 13616 mod-97 check (plus the Pakistani format when it starts with PK)."""
    iban = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    if iban.startswith("PK") and not PK_IBAN.fullmatch(iban):
        return False
    digits = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


class BankAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    bank: str = Field(min_length=2, max_length=80)
    account_title: str = Field(min_length=2, max_length=120)
    account_number: str = Field(default="", max_length=34, pattern=r"^[0-9 -]*$")
    iban: str = Field(default="", max_length=34)
    branch: str = Field(default="", max_length=120)

    @field_validator("iban")
    @classmethod
    def valid_iban(cls, value: str) -> str:
        value = value.replace(" ", "").upper()
        if value and not iban_valid(value):
            raise ValueError("Check the IBAN — it doesn't look right")
        return value


class Wallet(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider: Literal["jazzcash", "easypaisa", "sadapay", "nayapay"]
    account_title: str = Field(min_length=2, max_length=120)
    number: str = Field(pattern=r"^(\+92|0)3\d{9}$")


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    stripe_enabled: bool = False
    bank_enabled: bool = False
    bank_accounts: list[BankAccount] = Field(default_factory=list, max_length=5)
    wallet_enabled: bool = False
    wallets: list[Wallet] = Field(default_factory=list, max_length=5)
    cash_enabled: bool = False
    cash_instructions: str = Field(default="", max_length=1000)
    payment_note: str = Field(default="", max_length=1000)


async def settings_for(session: AsyncSession, scope: WorkspaceScope) -> PiCustomerPaymentSettings:
    repo = WorkspaceRepository(session, PiCustomerPaymentSettings, scope)
    row = await repo.find()
    if row is None:
        row = await repo.add(repo.new())
    return row


async def stripe_connected(session: AsyncSession, scope: WorkspaceScope) -> bool:
    from app.modules.integrations.models import IntegrationConnection

    found = await session.scalar(
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .with_only_columns(IntegrationConnection.id)
        .where(
            IntegrationConnection.integration_key == "stripe",
            IntegrationConnection.status.in_(["connected", "degraded"]),
        )
        .limit(1)
    )
    return found is not None


async def update_settings(
    session: AsyncSession, scope: WorkspaceScope, data: SettingsInput
) -> PiCustomerPaymentSettings:
    scope.require("pi.settings.manage")
    scope.require("billing.write")
    if data.bank_enabled and not data.bank_accounts:
        raise BusinessRuleViolation("BANK_DETAILS_REQUIRED", "Add at least one bank account")
    if data.wallet_enabled and not data.wallets:
        raise BusinessRuleViolation("WALLET_DETAILS_REQUIRED", "Add at least one wallet")
    # Card stays off while Stripe is disconnected, so the other methods can still be saved.
    stripe_on = data.stripe_enabled and await stripe_connected(session, scope)
    row = await settings_for(session, scope)
    row.stripe_enabled, row.bank_enabled = stripe_on, data.bank_enabled
    row.bank_accounts = [a.model_dump() for a in data.bank_accounts]
    row.wallet_enabled, row.wallets = data.wallet_enabled, [w.model_dump() for w in data.wallets]
    row.cash_enabled, row.cash_instructions = data.cash_enabled, data.cash_instructions
    row.payment_note = data.payment_note
    await record(
        session,
        "pi.customer_payment_settings_updated",
        scope=scope,
        entity_type="pi_customer_payment_settings",
        entity_id=row.id,
        details={
            "stripe": stripe_on,
            "bank_accounts": len(data.bank_accounts),
            "wallets": len(data.wallets),
            "cash": data.cash_enabled,
        },
    )
    return row


def enabled_methods(row: PiCustomerPaymentSettings, stripe_ready: bool = True) -> list[str]:
    """Methods customers can be offered. Card needs a live Stripe connection too."""
    return [
        method
        for method, on in (
            ("stripe", row.stripe_enabled and stripe_ready),
            ("bank_transfer", row.bank_enabled and bool(row.bank_accounts)),
            ("mobile_wallet", row.wallet_enabled and bool(row.wallets)),
            ("cash", row.cash_enabled),
        )
        if on
    ]


def _reference() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no easily confused characters
    return "PAY-" + "".join(secrets.choice(alphabet) for _ in range(8))


def _instructions(row: PiCustomerPaymentSettings, method: str) -> dict[str, Any]:
    if method == "bank_transfer":
        return {"bank_accounts": row.bank_accounts, "note": row.payment_note}
    if method == "mobile_wallet":
        return {
            "wallets": [{**w, "provider_name": WALLETS[w["provider"]]} for w in row.wallets],
            "note": row.payment_note,
        }
    if method == "cash":
        return {"cash": row.cash_instructions, "note": row.payment_note}
    return {"note": row.payment_note}


async def open_balance(session: AsyncSession, scope: WorkspaceScope, invoice_id: UUID) -> Invoice:
    invoice = await WorkspaceRepository(session, Invoice, scope).get(invoice_id, for_update=True)
    if invoice.status not in {"issued", "partially_paid"}:
        raise BusinessRuleViolation("INVOICE_NOT_OPEN", "Only an issued invoice can be paid")
    if invoice.total - invoice.amount_paid <= 0:
        raise BusinessRuleViolation("NOTHING_DUE", "This invoice is already paid")
    return invoice


async def create_request(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    invoice_id: UUID,
    method: str,
    idempotency_key: str,
    conversation_id: UUID | None = None,
    customer_id: UUID | None = None,
    stripe_checkout: Any = None,
) -> PiPaymentRequest:
    """``customer_id`` binds the request to one customer (PI tools always pass it).
    ``stripe_checkout`` is an async callable (scope, invoice_id) -> operation view."""
    scope.require("billing.write")
    repo = WorkspaceRepository(session, PiPaymentRequest, scope)
    existing = await repo.find(PiPaymentRequest.idempotency_key == idempotency_key[:200])
    if existing is not None:
        return existing
    row = await settings_for(session, scope)
    stripe_ready = method != "stripe" or await stripe_connected(session, scope)
    if method not in enabled_methods(row, stripe_ready):
        raise BusinessRuleViolation("METHOD_UNAVAILABLE", "This payment method isn't turned on")
    invoice = await open_balance(session, scope, invoice_id)
    if customer_id is not None and invoice.customer_id != customer_id:
        raise ResourceNotFound  # Never another customer's invoice.
    if conversation_id is not None:
        conversation = await WorkspaceRepository(session, PiConversation, scope).get(
            conversation_id
        )
        if conversation.customer_id != invoice.customer_id:
            # Never post one customer's amount and account details in another's chat.
            raise BusinessRuleViolation(
                "CONVERSATION_MISMATCH", "This conversation belongs to a different customer"
            )
    due = invoice.total - invoice.amount_paid
    pending = await repo.find(
        PiPaymentRequest.invoice_id == invoice.id,
        PiPaymentRequest.method == method,
        PiPaymentRequest.status.in_(OPEN),
        PiPaymentRequest.amount == due,
    )
    if pending is not None and (
        pending.expires_at is None or pending.expires_at > datetime.now(UTC)
    ):
        return pending  # One live request per invoice, method and balance.
    ttl = STRIPE_TTL if method == "stripe" else REQUEST_TTL
    request = repo.new(
        invoice_id=invoice.id,
        customer_id=invoice.customer_id,
        conversation_id=conversation_id,
        method=method,
        amount=due,
        currency=invoice.currency,
        reference=_reference(),
        instructions=_instructions(row, method),
        idempotency_key=idempotency_key[:200],
        expires_at=datetime.now(UTC) + ttl,
        created_by_label=scope.actor_label,
    )
    if method == "stripe":
        if stripe_checkout is None:
            raise BusinessRuleViolation("STRIPE_NOT_CONNECTED", "Card payments aren't available")
        # A new request gets a new Checkout session (the old one may have expired).
        view = await stripe_checkout(scope, invoice.id, request.idempotency_key)
        url = str((view.get("output") or {}).get("url") or "")
        if not url.startswith("https://"):
            raise BusinessRuleViolation("CHECKOUT_FAILED", "The payment link couldn't be created")
        request.checkout_url = url[:500]
        request.integration_operation_id = UUID(str(view["id"])) if view.get("id") else None
    await repo.add(request)
    await record(
        session,
        "pi.payment_request_created",
        scope=scope,
        entity_type="pi_payment_request",
        entity_id=request.id,
        details={"method": method, "amount": str(due), "currency": invoice.currency},
    )
    return request


async def mark_submitted(
    session: AsyncSession,
    scope: WorkspaceScope,
    request_id: UUID,
    *,
    note: str = "",
    message_id: UUID | None = None,
    customer_id: UUID | None = None,
) -> PiPaymentRequest:
    """The customer says they paid (optionally with a screenshot). Never marks paid."""
    request = await WorkspaceRepository(session, PiPaymentRequest, scope).get(
        request_id, for_update=True
    )
    if customer_id is not None and request.customer_id != customer_id:
        raise ResourceNotFound
    if request.status == "open" and request.method != "stripe":
        request.status = "awaiting_verification"
        request.proof_note = note[:2000]
        request.proof_message_id = message_id
    return request


async def note_customer_proof(
    session: AsyncSession, scope: WorkspaceScope, message: PiMessage
) -> PiPaymentRequest | None:
    """An inbound message that looks like payment proof (a screenshot, a document, "paid",
    "bhej diya", or the reference) moves the customer's open bank/wallet/cash request to
    "to verify" for staff. It never marks anything paid."""
    if message.direction != "inbound":
        return None
    looks_like_proof = message.message_type in {"image", "document"} or bool(
        PROOF_WORDS.search(message.body or "") or REFERENCE.search(message.body or "")
    )
    if not looks_like_proof:
        return None
    conversation = await WorkspaceRepository(session, PiConversation, scope).get(
        message.conversation_id
    )
    if conversation.customer_id is None:
        return None
    candidates = list(
        await session.scalars(
            WorkspaceRepository(session, PiPaymentRequest, scope)
            .select()
            .where(
                PiPaymentRequest.customer_id == conversation.customer_id,
                PiPaymentRequest.status == "open",
                PiPaymentRequest.method != "stripe",
            )
            .order_by(PiPaymentRequest.created_at.desc())
            .limit(20)
        )
    )
    if not candidates:
        return None
    quoted = {m.upper() for m in REFERENCE.findall(message.body or "")}
    chosen = next((r for r in candidates if r.reference in quoted), candidates[0])
    return await mark_submitted(
        session,
        scope,
        chosen.id,
        note=message.body or f"[{message.message_type}]",
        message_id=message.id,
        customer_id=conversation.customer_id,
    )


async def verify(
    session: AsyncSession,
    scope: WorkspaceScope,
    request_id: UUID,
    *,
    received: bool,
    reference: str = "",
    received_on: date | None = None,
) -> PiPaymentRequest:
    """A team member confirms the money arrived (or didn't). Records the payment on the
    invoice in the same transaction; a changed balance goes to review, never overpays."""
    scope.require("billing.write")
    request = await WorkspaceRepository(session, PiPaymentRequest, scope).get(
        request_id, for_update=True
    )
    if request.method == "stripe":
        raise BusinessRuleViolation(
            "STRIPE_AUTOMATIC", "Card payments are confirmed automatically by Stripe", 409
        )
    if request.status not in OPEN:
        raise Conflict("This payment request was already handled")
    if not received:
        request.status = "open"  # Customer is asked again; nothing is recorded.
        await record(
            session,
            "pi.payment_not_received",
            scope=scope,
            entity_type="pi_payment_request",
            entity_id=request.id,
        )
        return request
    invoice = await WorkspaceRepository(session, Invoice, scope).get(
        request.invoice_id, for_update=True
    )
    if (
        invoice.status not in {"issued", "partially_paid"}
        or request.amount > invoice.total - invoice.amount_paid
    ):
        request.status = "needs_review"
        return request
    payment = await BillingService(session, scope).record_payment(
        invoice.id,
        PaymentCreate(
            amount=request.amount,
            method=BILLING_METHOD[request.method],
            received_on=received_on,
            reference=(reference or request.reference)[:120],
        ),
    )
    request.status, request.payment_id = "paid", payment.id
    request.verified_by_user_id, request.verified_at = scope.user_id, datetime.now(UTC)
    await record(
        session,
        "pi.payment_verified",
        scope=scope,
        entity_type="pi_payment_request",
        entity_id=request.id,
        details={"method": request.method, "amount": str(request.amount)},
    )
    return request


async def cancel(
    session: AsyncSession, scope: WorkspaceScope, request_id: UUID
) -> PiPaymentRequest:
    scope.require("billing.write")
    request = await WorkspaceRepository(session, PiPaymentRequest, scope).get(
        request_id, for_update=True
    )
    if request.status in OPEN:
        request.status = "cancelled"
    return request


async def sync_stripe(
    session: AsyncSession, scope: WorkspaceScope, request: PiPaymentRequest
) -> None:
    """Reflect the settled Stripe checkout (settled by the verified Stripe webhook)."""
    if request.method != "stripe" or request.integration_operation_id is None:
        return
    from app.integrations.workflow_models import IntegrationOperation

    op = await session.scalar(
        WorkspaceRepository(session, IntegrationOperation, scope)
        .select()
        .where(IntegrationOperation.id == request.integration_operation_id)
    )
    state = (op.output or {}).get("payment_state") if op is not None else None
    if state == "paid" and request.status in (*OPEN, "expired", "cancelled"):
        request.status = "paid"
        request.payment_id = (
            UUID(op.output["payment_id"]) if op and op.output.get("payment_id") else None
        )
    elif state == "needs_review" and request.status in OPEN:
        request.status = "needs_review"


def customer_message(request: PiPaymentRequest) -> str:
    """Deterministic payment instructions (amounts come from the invoice)."""
    amount = f"{request.amount:,.2f} {request.currency}"
    lines = [f"Amount due: {amount}", f"Payment reference: {request.reference}"]
    info = request.instructions or {}
    if request.method == "stripe" and request.checkout_url:
        lines.append(f"Pay securely by card: {request.checkout_url}")
    for account in info.get("bank_accounts", []):
        parts = [account["bank"], f"Title: {account['account_title']}"]
        if account.get("account_number"):
            parts.append(f"Account: {account['account_number']}")
        if account.get("iban"):
            parts.append(f"IBAN: {account['iban']}")
        lines.append(" | ".join(parts))
    for wallet in info.get("wallets", []):
        lines.append(f"{wallet['provider_name']}: {wallet['number']} ({wallet['account_title']})")
    if info.get("cash"):
        lines.append(str(info["cash"]))
    if request.method in {"bank_transfer", "mobile_wallet"}:
        lines.append("Please send the reference with your payment screenshot.")
    if info.get("note"):
        lines.append(str(info["note"]))
    return "\n".join(lines)


def view(request: PiPaymentRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "invoice_id": request.invoice_id,
        "customer_id": request.customer_id,
        "conversation_id": request.conversation_id,
        "method": request.method,
        "status": request.status,
        "amount": str(request.amount),
        "currency": request.currency,
        "reference": request.reference,
        "checkout_url": request.checkout_url,
        "proof_note": request.proof_note,
        "created_at": request.created_at,
        "expires_at": request.expires_at,
        "verified_at": request.verified_at,
        "message": customer_message(request),
    }


async def expire_requests(session: AsyncSession) -> int:
    """Unanswered requests expire. One the customer already reported paying stays in the
    staff queue: the money may have arrived."""
    rows = list(
        await session.scalars(
            select(PiPaymentRequest)
            .where(
                PiPaymentRequest.status == "open",
                PiPaymentRequest.expires_at.is_not(None),
                PiPaymentRequest.expires_at <= datetime.now(UTC),
            )
            .limit(500)
        )
    )
    for row in rows:
        row.status = "expired"
    return len(rows)
