"""Separate customer and platform-operator billing boundaries."""

import hashlib
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.ai.registry import ModelRegistry
from app.core import rate_limit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_saas import manual_billing as manual
from app.modules.pi_saas import pay_links, qr
from app.modules.pi_saas.billing import change_plan, preview_change_plan, subscription_for
from app.modules.pi_saas.models import PiBusinessAccount, PiPlatformInvoice
from app.modules.pi_saas.operator import Operator, account_for, visible_tenants
from app.modules.pi_saas.payment_models import PiCollectionSettings, PiManualPayment
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound

client_router = APIRouter(prefix="/billing", tags=["pi-payments"])
operator_router = APIRouter(prefix="/operator/pi/billing", tags=["pi-operator-billing"])
# Public, token-authenticated: the token itself is the credential, so these carry no
# Scope/auth dependency at all (see app/modules/pi_saas/pay_links.py).
public_router = APIRouter(prefix="/pay", tags=["pi-pay-link"])

MANUAL_PAYMENT_LIVE = frozenset({"awaiting_payment", "submitted"})


def _pay_url(request: Request, token: str) -> str:
    base = request.app.state.settings.pi_app_public_url.rstrip("/")
    return f"{base}/pay/{token}"


async def client_account(
    scope: Scope, session: Session, permission: str, *, mutation: bool = False
) -> PiBusinessAccount:
    scope.require(permission)
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == scope.tenant_id)
    )
    if account is None:
        raise ResourceNotFound
    if mutation and scope.environment_id != account.production_environment_id:
        raise BusinessRuleViolation(
            "TEST_BILLING_DISABLED", "Payment requests are unavailable in the test workspace", 409
        )
    return account


@client_router.get("/payment-methods")
async def payment_methods(scope: Scope, session: Session) -> dict[str, Any]:
    await client_account(scope, session, "pi.billing.read")
    config = await manual.collection_config(session)
    return {
        "currency": "PKR",
        "bank_transfer": config.bank_enabled,
        "cash": config.cash_enabled,
        "support_email": config.support_email,
    }


@client_router.get("/change-plan/preview")
async def change_plan_preview(
    request: Request,
    scope: Scope,
    session: Session,
    plan: str = Query(pattern=r"^[a-z0-9_-]{1,32}$"),
) -> dict[str, Any]:
    """The prorated "you'll be charged $X now" preview before confirming a plan change
    on the existing Stripe subscription. Read-only: calls Stripe but changes nothing."""
    account = await client_account(scope, session, "pi.billing.manage")
    return await preview_change_plan(
        session, request.app.state.settings, request.app.state.http, scope, account, plan
    )


class PlanChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")


@client_router.post("/change-plan")
async def change_plan_commit(
    data: PlanChange, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Switch the existing Stripe subscription to a new plan (saved card, no new
    checkout). Applied optimistically; confirmed by the subscription-updated webhook."""
    account = await client_account(scope, session, "pi.billing.manage", mutation=True)
    subscription = await change_plan(
        session, request.app.state.settings, request.app.state.http, scope, account, data.plan
    )
    await session.commit()
    return {
        "plan": subscription.plan_key,
        "pending_plan": subscription.pending_plan_key,
        "status": subscription.status,
    }


@client_router.get("/payments")
async def my_payments(
    scope: Scope,
    session: Session,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    await client_account(scope, session, "pi.billing.read")
    query = select(PiManualPayment).where(PiManualPayment.tenant_id == scope.tenant_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(PiManualPayment.created_at.desc(), PiManualPayment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [manual.payment_view(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@client_router.post("/payments", status_code=201)
async def request_payment(
    data: manual.PaymentChoice, scope: Scope, session: Session
) -> dict[str, Any]:
    account = await client_account(scope, session, "pi.billing.manage", mutation=True)
    assert scope.user_id is not None
    row = await manual.create_payment(session, account, scope.user_id, data)
    await session.commit()
    return manual.payment_view(row)


@client_router.post("/payments/{payment_id}/submit")
async def submit_payment(
    payment_id: UUID, data: manual.PaymentSubmission, scope: Scope, session: Session
) -> dict[str, Any]:
    await client_account(scope, session, "pi.billing.manage", mutation=True)
    assert scope.user_id is not None
    row = await manual.submit_payment(session, scope.tenant_id, payment_id, scope.user_id, data)
    await session.commit()
    return manual.payment_view(row)


@client_router.post("/payments/{payment_id}/cancel")
async def cancel_payment(payment_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await client_account(scope, session, "pi.billing.manage", mutation=True)
    assert scope.user_id is not None
    row = await manual.cancel_payment(session, scope.tenant_id, payment_id, scope.user_id)
    await session.commit()
    return manual.payment_view(row)


async def read_proof_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """Validated receipt upload: a size cap plus magic-byte sniffing (never trusting the
    browser-supplied content type). Shared by the authenticated and public-link routes."""
    try:
        data = await file.read(5 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if len(data) > 5 * 1024 * 1024:
        raise BusinessRuleViolation("FILE_TOO_LARGE", "Use a receipt smaller than 5 MB", 413)
    mime = (
        "application/pdf"
        if data.startswith(b"%PDF-")
        else "image/png"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else "image/jpeg"
        if data.startswith(b"\xff\xd8\xff")
        else None
    )
    if mime is None:
        raise BusinessRuleViolation("INVALID_FILE", "Upload a PDF, PNG or JPEG bank receipt", 415)
    return data, mime, hashlib.sha256(data).hexdigest()


@client_router.post("/payments/{payment_id}/proof")
async def upload_proof(
    payment_id: UUID, file: UploadFile, scope: Scope, session: Session
) -> dict[str, Any]:
    await client_account(scope, session, "pi.billing.manage", mutation=True)
    await subscription_for(session, scope.tenant_id)
    row = await manual.payment_for(session, scope.tenant_id, payment_id, lock=True)
    if row.status != "awaiting_payment":
        raise BusinessRuleViolation(
            "PAYMENT_CLOSED", "Receipts cannot be changed after submission", 409
        )
    data, mime, sha256 = await read_proof_upload(file)
    row.proof, row.proof_type, row.proof_sha256 = data, mime, sha256
    assert scope.user_id is not None
    await manual.audit(session, row, scope.user_id, "proof_uploaded", sha256=row.proof_sha256)
    await session.commit()
    return manual.payment_view(row)


@client_router.post("/payments/{payment_id}/link")
async def create_payment_link(
    payment_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Issue (or rotate) the public pay-by-link/QR token for this payment. Replaces any
    previous token: an old link/QR stops working the moment a new one is issued."""
    await client_account(scope, session, "pi.billing.manage", mutation=True)
    row = await manual.payment_for(session, scope.tenant_id, payment_id, lock=True)
    if row.status not in MANUAL_PAYMENT_LIVE:
        raise BusinessRuleViolation("PAYMENT_CLOSED", "This payment can no longer be paid", 409)
    token = pay_links.issue(row)
    assert scope.user_id is not None
    await manual.audit(session, row, scope.user_id, "link_issued")
    await session.commit()
    return {
        "token": token,
        "url": _pay_url(request, token),
        "expires_at": row.link_expires_at,
    }


async def proof_response(session: Session, row: PiManualPayment) -> Response:
    data = await session.scalar(
        select(PiManualPayment.proof).where(
            PiManualPayment.id == row.id, PiManualPayment.tenant_id == row.tenant_id
        )
    )
    if not data or not row.proof_type:
        raise ResourceNotFound
    extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[row.proof_type]
    return Response(
        data,
        media_type=row.proof_type,
        headers={
            "Content-Disposition": f'attachment; filename="payment-{row.id}.{extension}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


def receipt_response(row: PiManualPayment, name: str) -> HTMLResponse:
    return HTMLResponse(
        manual.receipt_html(row, name),
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; "
            "style-src 'unsafe-inline'; frame-ancestors 'none'",
        },
    )


@client_router.get("/payments/{payment_id}/proof")
async def my_proof(payment_id: UUID, scope: Scope, session: Session) -> Response:
    await client_account(scope, session, "pi.billing.read")
    return await proof_response(
        session, await manual.payment_for(session, scope.tenant_id, payment_id)
    )


@client_router.get("/payments/{payment_id}/receipt")
async def my_receipt(payment_id: UUID, scope: Scope, session: Session) -> HTMLResponse:
    account = await client_account(scope, session, "pi.billing.read")
    return receipt_response(
        await manual.payment_for(session, scope.tenant_id, payment_id), account.name
    )


@operator_router.get("/settings")
async def operator_settings(
    request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.billing.read")
    config = await manual.collection_config(session)
    settings = request.app.state.settings
    models = ModelRegistry.from_settings(settings).table()
    return {
        "collection": config.model_dump(),
        "can_edit": operator.role == "owner" and operator.can("operator.plans.manage"),
        "runtime": {
            "kapso": {
                "key_configured": bool(settings.kapso_api_key),
                "webhook_configured": bool(settings.kapso_webhook_secret),
                "webhook_path": "/api/v1/webhooks/kapso",
            },
            "stripe": {
                "key_configured": bool(settings.pi_billing_stripe_secret_key),
                "webhook_configured": bool(settings.pi_billing_stripe_webhook_secret),
                "mode": "test"
                if settings.pi_billing_stripe_secret_key
                and settings.pi_billing_stripe_secret_key.get_secret_value().startswith("sk_test_")
                else "live"
                if settings.pi_billing_stripe_secret_key
                else "not_configured",
                "webhook_path": "/api/v1/webhooks/pi-billing/stripe",
            },
            "ai": [
                {
                    "provider": name,
                    "key_configured": bool(getattr(settings, f"{name}_api_key")),
                    "models": models.get(name, {}),
                }
                for name in ["openai", "gemini", "groq"]
            ],
            "provider_order": [
                p
                for p in [
                    settings.primary_llm_provider,
                    settings.fallback_llm_provider,
                    settings.secondary_fallback_llm_provider,
                ]
                if p
            ],
            "encryption_configured": bool(settings.secrets_encryption_key),
            "pi_public_url": settings.pi_app_public_url,
        },
    }


@operator_router.put("/settings")
async def save_settings(
    data: manual.CollectionConfig, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.plans.manage")
    if operator.role != "owner":
        raise PermissionDenied
    await session.execute(
        insert(PiCollectionSettings)
        .values(key="platform", config=data.model_dump())
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"config": data.model_dump(), "updated_at": datetime.now(UTC)},
        )
    )
    await record(
        session,
        "pi_billing.collection_settings_changed",
        actor_user_id=operator.user_id,
        details={"bank_enabled": data.bank_enabled, "cash_enabled": data.cash_enabled},
        include_environment=False,
    )
    await session.commit()
    return await operator_settings(request, operator, session)


@operator_router.get("/summary")
async def payment_summary(operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.billing.read")
    operator.require("operator.accounts.read")
    period = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    tenants = visible_tenants(operator)

    async def total(query: Any, model: Any) -> Any:
        if tenants is not None:
            query = query.where(model.tenant_id.in_(tenants))
        return await session.scalar(query) or 0

    received = await total(
        select(func.sum(PiManualPayment.amount)).where(
            PiManualPayment.status.in_(["approved", "refunded"]),
            PiManualPayment.reviewed_at >= period,
        ),
        PiManualPayment,
    )
    refunded = await total(
        select(func.sum(PiManualPayment.amount)).where(
            PiManualPayment.status == "refunded",
            PiManualPayment.refunded_at >= period,
        ),
        PiManualPayment,
    )
    pending = await total(
        select(func.count(PiManualPayment.id)).where(PiManualPayment.status == "submitted"),
        PiManualPayment,
    )
    stripe_query = (
        select(PiPlatformInvoice.currency, func.sum(PiPlatformInvoice.amount_paid))
        .where(
            PiPlatformInvoice.external_id.is_not(None),
            PiPlatformInvoice.status == "paid",
            PiPlatformInvoice.last_event_at >= period,
        )
        .group_by(PiPlatformInvoice.currency)
    )
    if tenants is not None:
        stripe_query = stripe_query.where(PiPlatformInvoice.tenant_id.in_(tenants))
    stripe = await session.execute(stripe_query)
    return {
        "period": period,
        "received_pkr": str(received),
        "refunded_pkr": str(refunded),
        "net_pkr": str(received - refunded),
        "pending_count": pending,
        "stripe_paid": [
            {"currency": currency, "amount": str(amount)} for currency, amount in stripe
        ],
    }


@operator_router.get("/payments")
async def operator_payments(
    operator: Operator,
    session: Session,
    status: Literal[
        "awaiting_payment", "submitted", "approved", "rejected", "cancelled", "refunded"
    ]
    | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    operator.require("operator.billing.read")
    operator.require("operator.accounts.read")
    query = select(PiManualPayment, PiBusinessAccount.name).join(
        PiBusinessAccount, PiBusinessAccount.tenant_id == PiManualPayment.tenant_id
    )
    tenants = visible_tenants(operator)
    if tenants is not None:
        query = query.where(PiManualPayment.tenant_id.in_(tenants))
    if status:
        query = query.where(PiManualPayment.status == status)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(PiManualPayment.created_at.desc(), PiManualPayment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {**manual.payment_view(row), "tenant_id": str(row.tenant_id), "business_name": name}
            for row, name in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["approve", "reject"]
    note: str = Field(min_length=3, max_length=500)
    verified_received: bool = False


@operator_router.post("/accounts/{tenant_id}/payments/{payment_id}/review")
async def review_payment(
    tenant_id: UUID,
    payment_id: UUID,
    data: ReviewInput,
    request: Request,
    operator: Operator,
    session: Session,
) -> dict[str, Any]:
    operator.require("operator.billing.manage")
    await account_for(session, operator, tenant_id)
    if data.action == "approve" and not data.verified_received:
        raise BusinessRuleViolation(
            "VERIFY_RECEIPT", "Confirm that the exact payment was received before approving"
        )
    row = await manual.decide_payment(
        session,
        tenant_id,
        payment_id,
        operator.user_id,
        data.action,
        data.note,
        settings=request.app.state.settings,
        http=request.app.state.http,
    )
    await session.commit()
    return manual.payment_view(row)


@operator_router.post("/accounts/{tenant_id}/payments/{payment_id}/link")
async def operator_create_payment_link(
    tenant_id: UUID, payment_id: UUID, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.billing.manage")
    await account_for(session, operator, tenant_id)
    row = await manual.payment_for(session, tenant_id, payment_id, lock=True)
    if row.status not in MANUAL_PAYMENT_LIVE:
        raise BusinessRuleViolation("PAYMENT_CLOSED", "This payment can no longer be paid", 409)
    token = pay_links.issue(row)
    await manual.audit(session, row, operator.user_id, "link_issued")
    await session.commit()
    return {
        "token": token,
        "url": _pay_url(request, token),
        "expires_at": row.link_expires_at,
    }


class CashRecord(manual.PaymentChoice, manual.PaymentSubmission):
    method: Literal["cash"] = "cash"
    verified_received: bool = False


@operator_router.post("/accounts/{tenant_id}/cash", status_code=201)
async def record_cash(
    tenant_id: UUID, data: CashRecord, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.billing.manage")
    account = await account_for(session, operator, tenant_id)
    if not data.verified_received:
        raise BusinessRuleViolation("VERIFY_RECEIPT", "Confirm that the cash was actually received")
    row = await manual.create_payment(
        session,
        account,
        operator.user_id,
        manual.PaymentChoice.model_validate(
            data.model_dump(include={"request_key", "plan", "method", "months"})
        ),
    )
    if row.status == "awaiting_payment":
        row = await manual.submit_payment(
            session,
            tenant_id,
            row.id,
            operator.user_id,
            manual.PaymentSubmission.model_validate(
                data.model_dump(include={"payer_name", "reference", "paid_on", "note"})
            ),
        )
    row = await manual.decide_payment(
        session,
        tenant_id,
        row.id,
        operator.user_id,
        "approve",
        data.note or "Cash received by billing operator",
        settings=request.app.state.settings,
        http=request.app.state.http,
    )
    await session.commit()
    return manual.payment_view(row)


class RefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reference: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=3, max_length=500)
    already_refunded: bool = False


@operator_router.post("/accounts/{tenant_id}/payments/{payment_id}/refund")
async def record_refund(
    tenant_id: UUID, payment_id: UUID, data: RefundInput, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.billing.manage")
    await account_for(session, operator, tenant_id)
    if not data.already_refunded:
        raise BusinessRuleViolation(
            "VERIFY_REFUND", "Confirm that the full amount was already returned outside this app"
        )
    row = await manual.refund_payment(
        session, tenant_id, payment_id, operator.user_id, data.reference, data.reason
    )
    await session.commit()
    return manual.payment_view(row)


@operator_router.get("/accounts/{tenant_id}/payments/{payment_id}/proof")
async def operator_proof(
    tenant_id: UUID, payment_id: UUID, operator: Operator, session: Session
) -> Response:
    operator.require("operator.billing.read")
    await account_for(session, operator, tenant_id)
    row = await manual.payment_for(session, tenant_id, payment_id)
    await manual.audit(session, row, operator.user_id, "proof_viewed")
    await session.commit()
    return await proof_response(session, row)


@operator_router.get("/accounts/{tenant_id}/payments/{payment_id}/receipt")
async def operator_receipt(
    tenant_id: UUID, payment_id: UUID, operator: Operator, session: Session
) -> HTMLResponse:
    operator.require("operator.billing.read")
    account = await account_for(session, operator, tenant_id)
    return receipt_response(await manual.payment_for(session, tenant_id, payment_id), account.name)


# --- Public, token-authenticated pay-by-link/QR (no Scope/auth dependency: possessing
# the raw token is the only credential) -------------------------------------------------


@public_router.get("/{token}")
async def public_pay_view(token: str, request: Request, session: Session) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-link-view", f"{token}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiManualPayment, token, live_statuses=MANUAL_PAYMENT_LIVE
    )
    if row is None:
        raise ResourceNotFound
    business = await session.scalar(
        select(PiBusinessAccount.name).where(PiBusinessAccount.tenant_id == row.tenant_id)
    )
    view = manual.payment_view(row)
    view["business_name"] = business or ""
    return view


@public_router.post("/{token}/proof")
async def public_submit_proof(
    token: str,
    request: Request,
    session: Session,
    file: UploadFile,
    payer_name: Annotated[str, Form(min_length=2, max_length=160)],
    paid_on: Annotated[date, Form()],
    reference: Annotated[str, Form(max_length=120)] = "",
    note: Annotated[str, Form(max_length=500)] = "",
) -> dict[str, Any]:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-link-proof", f"{token}:{ip}", 10, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiManualPayment, token, live_statuses=MANUAL_PAYMENT_LIVE, lock=True
    )
    if row is None:
        raise ResourceNotFound
    if row.status != "awaiting_payment":
        raise BusinessRuleViolation(
            "PAYMENT_CLOSED", "Receipts cannot be changed after submission", 409
        )
    data, mime, sha256 = await read_proof_upload(file)
    row.proof, row.proof_type, row.proof_sha256 = data, mime, sha256
    await manual.audit(session, row, None, "proof_uploaded", sha256=sha256, via="pay_link", ip=ip)
    submission = manual.PaymentSubmission(
        payer_name=payer_name, reference=reference, paid_on=paid_on, note=note
    )
    updated = await manual.submit_payment(session, row.tenant_id, row.id, None, submission)
    await session.commit()
    return manual.payment_view(updated)


@public_router.get("/{token}/qr.png")
async def public_pay_qr(token: str, request: Request, session: Session) -> Response:
    ip = rate_limit.client_ip(request)
    if not await rate_limit.hit(request, "pay-link-qr", f"{token}:{ip}", 30, 3600):
        raise HTTPException(status_code=429)
    row = await pay_links.resolve(
        session, PiManualPayment, token, live_statuses=MANUAL_PAYMENT_LIVE
    )
    if row is None:
        raise ResourceNotFound
    png = qr.png(_pay_url(request, token))
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
