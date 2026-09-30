"""Staff API for collecting payments from a business's own customers (/pi/...).

Mounted for the Owner OS workspace and the Pi app. Viewing needs ``billing.read``;
changing settings, creating, verifying or cancelling requests needs ``billing.write``.
"""

from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.integrations import business
from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Scope, Session
from app.modules.billing.models import Invoice
from app.modules.pi.service import PiService, require_pi
from app.modules.pi_saas import customer_payments as cp
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-customer-payments"])


def checkout_for(request: Request, session: Session) -> Any:
    settings = request.app.state.settings
    outbound = OutboundClient(settings, request.app.state.http)

    async def run(scope: Any, invoice_id: UUID, request_key: str = "") -> dict[str, Any]:
        return await business.checkout(session, settings, outbound, scope, invoice_id, request_key)

    return run


def _settings_view(row: Any, connected: bool) -> dict[str, Any]:
    return {
        "stripe_enabled": row.stripe_enabled,
        "stripe_connected": connected,
        "bank_enabled": row.bank_enabled,
        "bank_accounts": row.bank_accounts,
        "wallet_enabled": row.wallet_enabled,
        "wallets": row.wallets,
        "cash_enabled": row.cash_enabled,
        "cash_instructions": row.cash_instructions,
        "payment_note": row.payment_note,
        "enabled_methods": cp.enabled_methods(row, connected),
        "banks": list(cp.PAKISTAN_BANKS),
        "wallet_providers": cp.WALLETS,
    }


@router.get("/customer-payments/settings")
async def payment_settings(scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "billing.read")
    row = await cp.settings_for(session, scope)
    connected = await cp.stripe_connected(session, scope)
    await session.commit()
    return _settings_view(row, connected)


@router.put("/customer-payments/settings")
async def save_payment_settings(
    data: cp.SettingsInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "billing.write")
    row = await cp.update_settings(session, scope, data)
    connected = await cp.stripe_connected(session, scope)
    await session.commit()
    return _settings_view(row, connected)


class StripeConnect(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    secret_key: str = Field(pattern=r"^(sk|rk)_(test|live)_[A-Za-z0-9]{10,200}$")
    webhook_secret: str = Field(pattern=r"^whsec_[A-Za-z0-9]{10,200}$")


@router.post("/customer-payments/stripe")
async def connect_stripe(
    data: StripeConnect, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Connect the business's own Stripe account (keys are encrypted at rest and never
    returned). Test keys create a sandbox connection; live keys a production one."""
    await require_pi(session, scope, "billing.write")
    scope.require("integrations.manage")
    from app.modules.integrations.routes import runtime
    from app.modules.integrations.schemas import ConnectionCreate
    from app.modules.integrations.service import IntegrationService

    service = IntegrationService(session, scope, runtime(request))
    mode: Literal["sandbox", "production"] = (
        "sandbox" if "_test_" in data.secret_key else "production"
    )
    connection = await service.create(
        ConnectionCreate(
            integration_key="stripe",
            display_name="Stripe (customer payments)",
            mode=mode,
            credentials={"secret_key": data.secret_key, "webhook_secret": data.webhook_secret},
        )
    )
    await session.commit()
    connection = await service.get(connection.id, for_update=True)
    result = await service.run_test(connection)
    await session.commit()
    return {
        "connected": await cp.stripe_connected(session, scope),
        "mode": mode,
        "test": getattr(result, "status", None),
        "webhook_url": service.webhook_url(await service.get(connection.id)),
    }


@router.get("/customers/{customer_id}/open-invoices")
async def open_invoices(customer_id: UUID, scope: Scope, session: Session) -> list[dict[str, Any]]:
    await require_pi(session, scope, "billing.read")
    rows = await session.scalars(
        WorkspaceRepository(session, Invoice, scope)
        .select()
        .where(
            Invoice.customer_id == customer_id,
            Invoice.status.in_(["issued", "partially_paid"]),
        )
        .order_by(Invoice.created_at.desc())
        .limit(20)
    )
    return [
        {
            "id": i.id,
            "number": i.number,
            "total": str(i.total),
            "due": str(i.total - i.amount_paid),
            "currency": i.currency,
            "status": i.status,
        }
        for i in rows
    ]


@router.get("/payment-requests")
async def payment_requests(
    scope: Scope,
    session: Session,
    status: str | None = Query(None, max_length=24),
    customer_id: UUID | None = None,
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "billing.read")
    query = WorkspaceRepository(session, PiPaymentRequest, scope).select()
    if status == "active":  # Everything staff still need to act on.
        query = query.where(PiPaymentRequest.status.in_([*cp.OPEN, "needs_review"]))
    elif status:
        query = query.where(PiPaymentRequest.status == status)
    if customer_id:
        query = query.where(PiPaymentRequest.customer_id == customer_id)
    rows = list(
        await session.scalars(query.order_by(PiPaymentRequest.created_at.desc()).limit(200))
    )
    for row in rows:
        await cp.sync_stripe(session, scope, row)
    await session.commit()
    return [cp.view(r) for r in rows]


class RequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_id: UUID
    method: Literal["stripe", "bank_transfer", "mobile_wallet", "cash"]
    conversation_id: UUID | None = None
    request_key: UUID = Field(default_factory=uuid4)


@router.post("/payment-requests", status_code=201)
async def create_payment_request(
    data: RequestInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "billing.write")
    row = await cp.create_request(
        session,
        scope,
        invoice_id=data.invoice_id,
        method=data.method,
        idempotency_key=f"staff:{data.request_key}",
        conversation_id=data.conversation_id,
        stripe_checkout=checkout_for(request, session),
    )
    await session.commit()
    return cp.view(row)


class VerifyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    received: bool
    reference: str = Field(default="", max_length=120)


@router.post("/payment-requests/{request_id}/verify")
async def verify_payment(
    request_id: UUID, data: VerifyInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "billing.write")
    row = await cp.verify(
        session, scope, request_id, received=data.received, reference=data.reference
    )
    await session.commit()
    return cp.view(row)


@router.post("/payment-requests/{request_id}/cancel")
async def cancel_payment(request_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "billing.write")
    row = await cp.cancel(session, scope, request_id)
    await session.commit()
    return cp.view(row)


@router.post("/payment-requests/{request_id}/send")
async def send_payment_message(
    request_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Send the payment instructions in the customer's conversation (team reply)."""
    await require_pi(session, scope, "billing.write")
    row = await WorkspaceRepository(session, PiPaymentRequest, scope).get(request_id)
    if row.conversation_id is None:
        raise BusinessRuleViolation("NO_CONVERSATION", "Open a conversation with this customer")
    service = PiService(session, scope)
    conversation = await service.conversations.get(row.conversation_id)
    if conversation.mode != "human":
        await service.mode(conversation.id, "takeover")
    message = await service.human_message(conversation.id, cp.customer_message(row))
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    return {"message_id": message.id, "status": message.status}
