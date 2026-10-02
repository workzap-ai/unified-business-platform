"""Staff API for collecting payments from a business's own customers (/pi/...).

Mounted for the Owner OS workspace and the Pi app. Viewing needs ``billing.read``;
changing settings, creating, verifying or cancelling requests needs ``billing.write``.
"""

from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.core import rate_limit
from app.integrations import business
from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.billing.models import Invoice
from app.modules.pi.service import PiService, require_pi
from app.modules.pi_saas import customer_payments as cp
from app.modules.pi_saas import pay_links, qr
from app.modules.pi_saas.customer_payment_models import PiPaymentRequest
from app.modules.pi_saas.payment_routes import read_proof_upload
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-customer-payments"])
# Public, token-authenticated: the token itself is the credential, so these carry no
# Scope/auth dependency at all (see app/modules/pi_saas/pay_links.py).
public_router = APIRouter(prefix="/pay/request", tags=["pi-pay-link"])

PAYMENT_REQUEST_LIVE = frozenset(cp.OPEN)  # ("open", "awaiting_verification")


def _pay_request_url(request: Request, token: str) -> str:
    base = request.app.state.settings.pi_app_public_url.rstrip("/")
    return f"{base}/pay/request/{token}"


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
    """Send the payment instructions in the customer's conversation (team reply).

    Non-card requests get a fresh pay-by-link/QR token on every send: this is the
    "regenerate" case the token pattern expects, so a resend always carries a live
    link and the previous one (if any) stops working.
    """
    await require_pi(session, scope, "billing.write")
    row = await WorkspaceRepository(session, PiPaymentRequest, scope).get(request_id)
    if row.conversation_id is None:
        raise BusinessRuleViolation("NO_CONVERSATION", "Open a conversation with this customer")
    text = cp.customer_message(row)
    if row.method != "stripe":
        token = pay_links.issue(row)
        text = f"{text}\nPay online: {_pay_request_url(request, token)}"
    service = PiService(session, scope)
    conversation = await service.conversations.get(row.conversation_id)
    if conversation.mode != "human":
        await service.mode(conversation.id, "takeover")
    message = await service.human_message(conversation.id, text)
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    return {"message_id": message.id, "status": message.status}


@router.post("/payment-requests/{request_id}/link")
async def create_payment_request_link(
    request_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Issue (or rotate) the public pay-by-link/QR token without sending a message —
    for "Copy payment link" / "Download QR" actions on a request."""
    await require_pi(session, scope, "billing.write")
    row = await WorkspaceRepository(session, PiPaymentRequest, scope).get(
        request_id, for_update=True
    )
    if row.status not in cp.OPEN:
        raise BusinessRuleViolation("REQUEST_CLOSED", "This payment request is closed", 409)
    token = pay_links.issue(row)
    await session.commit()
    return {
        "token": token,
        "url": _pay_request_url(request, token),
        "expires_at": row.link_expires_at,
    }


# --- Public, token-authenticated pay-by-link/QR (no Scope/auth dependency: possessing
# the raw token is the only credential) -------------------------------------------------


@public_router.get("/{token}")
async def public_request_view(token: str, request: Request, session: Session) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-request-link-view", f"{token}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiPaymentRequest, token, live_statuses=PAYMENT_REQUEST_LIVE
    )
    if row is None:
        raise ResourceNotFound
    return cp.view(row)


@public_router.post("/{token}/proof")
async def public_request_proof(
    token: str,
    request: Request,
    session: Session,
    note: Annotated[str, Form(max_length=2000)] = "",
    reference: Annotated[str, Form(max_length=120)] = "",
    file: UploadFile | None = None,
) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-request-link-proof", f"{token}:{ip}", 10, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiPaymentRequest, token, live_statuses=PAYMENT_REQUEST_LIVE, lock=True
    )
    if row is None:
        raise ResourceNotFound
    if row.method == "stripe":
        raise BusinessRuleViolation(
            "STRIPE_AUTOMATIC", "Card payments are confirmed automatically by Stripe", 409
        )
    parts = [note.strip()]
    if reference.strip():
        parts.append(f"Reference: {reference.strip()}")
    if file is not None:
        # PiPaymentRequest has no binary proof column (WhatsApp proof images live on
        # the PiMessage they arrived as); validate the upload the same way, but only
        # its hash is kept, as a record that something was attached.
        _, _, sha256 = await read_proof_upload(file)
        parts.append(f"[receipt uploaded, sha256:{sha256[:16]}]")
    scope = WorkspaceScope.system(row.tenant_id, row.environment_id, frozenset(), "PayLink")
    updated = await cp.mark_submitted(
        session, scope, row.id, note="\n".join(p for p in parts if p) or "[submitted via pay link]"
    )
    await record(
        session,
        "pi.payment_proof_submitted_via_link",
        tenant_id=row.tenant_id,
        environment_id=row.environment_id,
        actor_user_id=None,
        entity_type="pi_payment_request",
        entity_id=row.id,
        details={"ip": ip},
    )
    await session.commit()
    return cp.view(updated)


@public_router.get("/{token}/qr.png")
async def public_request_qr(token: str, request: Request, session: Session) -> Response:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-request-link-qr", f"{token}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiPaymentRequest, token, live_statuses=PAYMENT_REQUEST_LIVE
    )
    if row is None:
        raise ResourceNotFound
    png = qr.png(_pay_request_url(request, token))
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
