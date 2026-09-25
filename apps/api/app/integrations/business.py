"""Invoice checkout, invoice email and record attachments backed by real adapters."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import EmailStr, TypeAdapter
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.email import EMAIL_KEYS
from app.integrations.errors import IntegrationError
from app.integrations.http import CallContext, OutboundClient
from app.integrations.providers.s3 import S3Provider, scoped_key
from app.integrations.providers.stripe import StripeProvider
from app.integrations.runtime import ConnectionRuntime
from app.integrations.workflow_models import IntegrationOperation
from app.integrations.workflows import operation_view
from app.modules.billing.models import Invoice
from app.modules.billing.schemas import PaymentCreate
from app.modules.billing.service import BillingService
from app.modules.customers.models import Customer
from app.modules.integrations.models import IntegrationConnection
from app.modules.orders.models import Order
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

ENTITY_TYPES = {
    "invoice": (Invoice, "billing"),
    "customer": (Customer, "customers"),
    "order": (Order, "orders"),
}
# Explicitly supported minor units; reject currencies we cannot safely convert.
TWO_DECIMAL = frozenset(
    (
        "USD EUR GBP PKR INR AED SAR CAD AUD NZD SGD HKD CNY CHF SEK NOK DKK ZAR "
        "BRL MXN MYR THB BDT LKR NPR TRY PLN CZK RON HUF"
    ).split()
)
ZERO_DECIMAL = frozenset("JPY KRW VND CLP XAF XOF RWF UGX BIF DJF GNF KMF VUV XPF MGA PYG".split())


def minor_units(amount: Decimal, currency: str) -> int:
    if currency not in TWO_DECIMAL | ZERO_DECIMAL:
        raise BusinessRuleViolation(
            "UNSUPPORTED_CURRENCY", "Online payment is not available for this currency"
        )
    value = amount * (1 if currency in ZERO_DECIMAL else 100)
    if value != value.to_integral_value() or value <= 0:
        raise BusinessRuleViolation(
            "INVALID_AMOUNT", "This amount cannot be charged in the selected currency"
        )
    return int(value)


async def entity(
    session: AsyncSession, scope: WorkspaceScope, kind: str, entity_id: UUID, *, write: bool = False
) -> Any:
    if kind not in ENTITY_TYPES:
        raise ResourceNotFound
    model, permission = ENTITY_TYPES[kind]
    scope.require(f"{permission}.{'write' if write else 'read'}")
    return await WorkspaceRepository(session, model, scope).get(entity_id)


async def connection_for(
    session: AsyncSession,
    scope: WorkspaceScope,
    keys: tuple[str, ...],
    connection_id: UUID | None = None,
) -> IntegrationConnection:
    repo = WorkspaceRepository(session, IntegrationConnection, scope)
    if connection_id:
        provided = await repo.get(connection_id)
        if provided.integration_key not in keys or provided.status not in {"connected", "degraded"}:
            raise BusinessRuleViolation("CONNECTION_NOT_READY", "Choose a verified connection")
        return provided
    row = await session.scalar(
        repo.select()
        .where(
            IntegrationConnection.integration_key.in_(keys),
            IntegrationConnection.status.in_(("connected", "degraded")),
        )
        .order_by(IntegrationConnection.connected_at.desc().nulls_last())
        .limit(1)
    )
    if row is None:
        raise BusinessRuleViolation(
            "INTEGRATION_NOT_CONFIGURED",
            "Connect and verify this provider in Settings → Integrations first",
            409,
        )
    return row


async def operation(
    session: AsyncSession,
    scope: WorkspaceScope,
    connection: IntegrationConnection,
    kind: str,
    dedupe_key: str,
    entity_type: str,
    entity_id: UUID,
    data: dict[str, Any],
) -> IntegrationOperation:
    await session.execute(
        insert(IntegrationOperation)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            connection_id=connection.id,
            kind=kind,
            dedupe_key=dedupe_key,
            entity_type=entity_type,
            entity_id=entity_id,
            input=data,
            status="pending",
        )
        .on_conflict_do_nothing(constraint="uq_integration_operations_dedupe")
    )
    row = await session.scalar(
        WorkspaceRepository(session, IntegrationOperation, scope)
        .select()
        .where(IntegrationOperation.dedupe_key == dedupe_key)
        .with_for_update()
    )
    assert row is not None
    return row


async def checkout(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    scope: WorkspaceScope,
    invoice_id: UUID,
) -> dict[str, Any]:
    scope.require("billing.write")
    invoice = await WorkspaceRepository(session, Invoice, scope).get(invoice_id, for_update=True)
    if invoice.status not in {"issued", "partially_paid"}:
        raise BusinessRuleViolation(
            "INVOICE_NOT_OPEN", "Issue the invoice before requesting payment"
        )
    balance = invoice.total - invoice.amount_paid
    amount = minor_units(balance, invoice.currency)
    connection = await connection_for(session, scope, ("stripe",))
    runtime = ConnectionRuntime(session, settings, http)
    if not runtime.context(connection).credentials.get("webhook_secret"):
        raise BusinessRuleViolation(
            "WEBHOOK_REQUIRED",
            "Configure the Stripe webhook signing secret before accepting payments",
        )
    base = (settings.integrations_public_base_url or settings.cors_origins[0]).rstrip("/")
    if settings.app_env == "production" and not base.startswith("https://"):
        raise BusinessRuleViolation("PUBLIC_URL_REQUIRED", "Configure an HTTPS application URL")
    key = f"checkout:{invoice.id}:{connection.id}:{invoice.amount_paid}:{balance}"
    op = await operation(
        session,
        scope,
        connection,
        "checkout",
        key,
        "invoice",
        invoice.id,
        {
            "amount": str(balance),
            "amount_minor": amount,
            "currency": invoice.currency,
            "number": invoice.number,
            "return_url": f"{base}/billing/invoices/{invoice.id}",
        },
    )
    if op.status == "succeeded":
        return operation_view(op)
    if (datetime.now(UTC) - op.created_at).total_seconds() > 23 * 3600:
        raise BusinessRuleViolation(
            "CHECKOUT_EXPIRED", "The payment request needs review before creating another link"
        )
    op.status, op.attempts = "running", op.attempts + 1
    await session.commit()  # Keep the same key even if the provider response is lost.
    data = op.input
    form = {
        "mode": "payment",
        "success_url": data["return_url"] + "?payment=returned",
        "cancel_url": data["return_url"],
        "client_reference_id": str(op.id),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": data["currency"].lower(),
        "line_items[0][price_data][unit_amount]": str(data["amount_minor"]),
        "line_items[0][price_data][product_data][name]": "Invoice " + data["number"],
    }
    provider = StripeProvider()
    try:
        result, _ = await runtime.call(
            connection,
            lambda ctx: provider.checkout(ctx, form, str(op.id)),
            kind="invoice_checkout",
            call=CallContext(idempotent=True),
        )
        url = urlsplit(str(result.get("url", "")))
        external_id = result.get("id")
        if (
            url.scheme != "https"
            or url.hostname != "checkout.stripe.com"
            or not isinstance(external_id, str)
            or not external_id.startswith("cs_")
        ):
            raise IntegrationError("INVALID_RESPONSE", "Stripe did not return a valid payment link")
        op.external_id, op.status = external_id, "succeeded"
        op.output = {"url": str(result["url"]), "payment_state": "unpaid", "mode": connection.mode}
        op.last_error = None
        await session.commit()
    except IntegrationError as error:
        op.status, op.last_error = "failed", error.message
        await session.commit()
        raise
    return operation_view(op)


async def settle_checkout(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    connection: IntegrationConnection,
    external_id: str,
) -> str:
    scope = WorkspaceScope.system(
        connection.tenant_id,
        connection.environment_id,
        frozenset({"billing.write"}),
        "Stripe payment",
    )
    op = await session.scalar(
        WorkspaceRepository(session, IntegrationOperation, scope)
        .select()
        .where(
            IntegrationOperation.connection_id == connection.id,
            IntegrationOperation.kind == "checkout",
            IntegrationOperation.external_id == external_id,
        )
        .with_for_update()
    )
    if op is None:
        return "ignored"  # Never trust invoice IDs from provider metadata.
    if op.output.get("payment_id"):
        return "processed"
    provider = StripeProvider()
    runtime = ConnectionRuntime(session, settings, http)
    data, _ = await runtime.call(
        connection, lambda ctx: provider.checkout_status(ctx, external_id), kind="payment_verify"
    )
    if data.get("payment_status") != "paid":
        return "ignored"
    if (
        data.get("id") != external_id
        or data.get("amount_total") != op.input["amount_minor"]
        or str(data.get("currency", "")).upper() != op.input["currency"]
        or data.get("client_reference_id") != str(op.id)
        or data.get("livemode") is not (connection.mode == "production")
    ):
        raise BusinessRuleViolation(
            "PAYMENT_MISMATCH", "Provider payment does not match the recorded invoice request"
        )
    assert op.entity_id is not None
    invoice = await WorkspaceRepository(session, Invoice, scope).get(op.entity_id, for_update=True)
    amount = Decimal(op.input["amount"])
    if (
        invoice.status not in {"issued", "partially_paid"}
        or amount > invoice.total - invoice.amount_paid
    ):
        op.output = {**op.output, "payment_state": "needs_review"}
        op.last_error = "Payment received after invoice balance changed; reconcile before recording"
        return "processed"
    payment = await BillingService(session, scope).record_payment(
        invoice.id, PaymentCreate(amount=amount, method="card", reference=external_id[:120])
    )
    op.output = {**op.output, "payment_state": "paid", "payment_id": str(payment.id)}
    return "processed"


async def email_invoice(
    session: AsyncSession, scope: WorkspaceScope, invoice_id: UUID, request_id: UUID
) -> IntegrationOperation:
    scope.require("billing.write")
    invoice = await WorkspaceRepository(session, Invoice, scope).get(invoice_id)
    if invoice.status in {"draft", "void"}:
        raise BusinessRuleViolation("INVOICE_NOT_OPEN", "Only issued invoices can be emailed")
    customer = await WorkspaceRepository(session, Customer, scope).get(invoice.customer_id)
    try:
        address = str(TypeAdapter(EmailStr).validate_python(customer.email))
    except ValueError:
        raise BusinessRuleViolation(
            "CUSTOMER_EMAIL_REQUIRED", "Add a valid email address to the customer first"
        ) from None
    connection = await connection_for(session, scope, EMAIL_KEYS)
    return await operation(
        session,
        scope,
        connection,
        "notification",
        f"invoice-email:{invoice.id}:{request_id}",
        "invoice",
        invoice.id,
        {
            "recipient": address,
            "title": f"Invoice {invoice.number}",
            "message": (
                f"Invoice {invoice.number}: total {invoice.currency} {invoice.total}; "
                f"balance due {invoice.total - invoice.amount_paid}. "
                f"Due date: {invoice.due_date or 'on receipt'}."
            ),
        },
    )


async def upload_file(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    scope: WorkspaceScope,
    kind: str,
    entity_id: UUID,
    name: str,
    content: bytes,
    mime: str,
    request_id: UUID,
) -> dict[str, Any]:
    await entity(session, scope, kind, entity_id, write=True)
    if not content or len(content) > min(settings.storage_max_upload_bytes, 25 * 1024**2):
        raise BusinessRuleViolation("FILE_SIZE", "Choose a non-empty file up to 25 MB")
    # Downloads are always attachments; never serve uploaded active content inline.
    name = (
        name.replace("\\", "/").rsplit("/", 1)[-1].replace("\r", "").replace("\n", "")[:180]
        or "file"
    )
    digest = hashlib.sha256(content).hexdigest()
    connection = await connection_for(session, scope, ("s3",))
    op = await operation(
        session,
        scope,
        connection,
        "file",
        f"file:{kind}:{entity_id}:{request_id}",
        kind,
        entity_id,
        {"name": name, "mime": "application/octet-stream", "size": len(content), "sha256": digest},
    )
    if op.input["sha256"] != digest:
        raise BusinessRuleViolation(
            "IDEMPOTENCY_CONFLICT", "This upload request already identifies a different file"
        )
    if op.status == "succeeded":
        return operation_view(op)
    if op.status == "cancelled":
        raise BusinessRuleViolation(
            "UPLOAD_CANCELLED", "Choose the file again to start a new upload"
        )
    # A retry belongs to its original bucket even if a newer storage connection exists.
    connection = await connection_for(session, scope, ("s3",), op.connection_id)
    op.status, op.attempts = "running", op.attempts + 1
    await session.commit()
    key = scoped_key(scope.tenant_id, scope.environment_id, f"attachments/{op.id}")
    runtime = ConnectionRuntime(session, settings, http)
    try:
        await runtime.call(
            connection,
            lambda ctx: S3Provider().upload(ctx, key, content, "application/octet-stream"),
            kind="file_upload",
            call=CallContext(idempotent=True),
        )
        op.status, op.output, op.last_error = (
            "succeeded",
            {"name": name, "size": len(content), "key": key},
            None,
        )
        await session.commit()
    except IntegrationError as error:
        op.status, op.last_error = "failed", error.message
        await session.commit()
        raise
    return operation_view(op)
