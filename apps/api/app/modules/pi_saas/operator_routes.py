"""Owner OS operator API for the Pi SaaS (/api/v1/operator/pi). Owner OS sessions only.

Every route re-checks the operator's active membership and capabilities, limits results
to assigned businesses where the role requires it, and is audited. Customer content is
available only through a business-approved support grant.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from app.core.rate_limit import hit
from app.modules.access.dependencies import Session
from app.modules.audit.service import record
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas import agenta, connections, onboarding
from app.modules.pi_saas.entitlement import entitlement, usage_for
from app.modules.pi_saas.kapso import Kapso
from app.modules.pi_saas.models import (
    PiBusinessAccount,
    PiOperatorAssignment,
    PiOperatorMember,
    PiPlan,
    PiPlatformInvoice,
    PiProviderConnection,
    PiProviderEvent,
    PiSubscription,
    PiSupportGrant,
)
from app.modules.pi_saas.operator import (
    CAPABILITIES,
    ROLE_PRESETS,
    Operator,
    OperatorContext,
    account_for,
    active_grant,
    capabilities_for,
    health,
    list_accounts,
)
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, PermissionDenied, ResourceNotFound
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/operator/pi", tags=["pi-operator"])


async def _audit(
    session: Any,
    operator: OperatorContext,
    action: str,
    tenant_id: UUID | None,
    details: dict[str, Any] | None = None,
) -> None:
    await record(
        session,
        f"pi_operator.{action}",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="pi_business_account" if tenant_id else "pi_operator",
        entity_id=tenant_id,
        details={"role": operator.role, **(details or {})},
        include_environment=False,
    )


@router.get("/me")
async def me(operator: Operator) -> dict[str, Any]:
    return {
        "role": operator.role,
        "role_name": ROLE_PRESETS[operator.role][0],
        "capabilities": sorted(operator.capabilities),
    }


@router.get("/accounts")
async def accounts(
    operator: Operator,
    session: Session,
    search: str | None = Query(None, max_length=100),
    state: str | None = Query(None, max_length=20),
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    items, total = await list_accounts(
        session, operator, search=search, state=state, page=page, page_size=page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/accounts/{tenant_id}")
async def account_detail(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    """Operational view. No customer names, messages or memory."""
    account = await account_for(session, operator, tenant_id)
    subscription = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant_id)
    )
    connections_rows = list(
        await session.scalars(
            select(PiProviderConnection).where(PiProviderConnection.tenant_id == tenant_id)
        )
    )
    now = datetime.now(UTC)
    grants = list(
        await session.scalars(
            select(PiSupportGrant)
            .where(PiSupportGrant.tenant_id == tenant_id)
            .order_by(PiSupportGrant.created_at.desc())
            .limit(20)
        )
    )
    result: dict[str, Any] = {
        "tenant_id": tenant_id,
        "name": account.name,
        "status": account.status,
        "setup_state": account.setup_state,
        "onboarding_step": account.onboarding_step,
        "offer_type": account.offer_type,
        "language": account.language,
        "timezone": account.timezone,
        "country": account.country,
        "help_requested_at": account.help_requested_at,
        "launched_at": account.launched_at,
        "readiness": await onboarding.readiness(session, account),
        "connections": [
            {
                "environment": "test"
                if c.environment_id == account.test_environment_id
                else "production",
                "provider": c.provider,
                "status": c.status,
                "display_phone_number": c.display_phone_number,
                "connection_type": c.connection_type,
                "health": c.health or None,
                "problem": c.last_error_code,
                "number_request": c.number_request or None,
                "last_event_at": c.last_event_at,
            }
            for c in connections_rows
        ],
        "support_grants": [
            {
                "id": g.id,
                "scope": g.scope,
                "status": "expired"
                if g.status == "active" and g.expires_at and g.expires_at <= now
                else g.status,
                "expires_at": g.expires_at,
                "requested_by": g.requested_by,
            }
            for g in grants
        ],
    }
    if operator.can("operator.billing.read"):
        result["subscription"] = (
            {
                "plan": subscription.plan_key,
                "status": subscription.status,
                "trial_ends_at": subscription.trial_ends_at,
                "current_period_end": subscription.current_period_end,
                "grace_ends_at": subscription.grace_ends_at,
                "billing_provider": subscription.billing_provider,
                "spend_limit": str(subscription.spend_limit)
                if subscription.spend_limit is not None
                else None,
            }
            if subscription
            else None
        )
        invoices = await session.scalars(
            select(PiPlatformInvoice)
            .where(PiPlatformInvoice.tenant_id == tenant_id)
            .order_by(PiPlatformInvoice.created_at.desc())
            .limit(12)
        )
        result["invoices"] = [
            {
                "number": i.number,
                "status": i.status,
                "amount_due": str(i.amount_due),
                "currency": i.currency,
            }
            for i in invoices
        ]
    from app.modules.pi_saas.customer_payment_models import PiCustomerPaymentSettings

    collection = await session.scalar(
        select(PiCustomerPaymentSettings).where(
            PiCustomerPaymentSettings.tenant_id == tenant_id,
            PiCustomerPaymentSettings.environment_id == account.production_environment_id,
        )
    )
    # Which ways the business collects from its own customers (never balances or accounts).
    result["customer_payment_methods"] = (
        [
            m
            for m, on in (
                ("stripe", collection.stripe_enabled),
                ("bank_transfer", collection.bank_enabled),
                ("mobile_wallet", collection.wallet_enabled),
                ("cash", collection.cash_enabled),
            )
            if on
        ]
        if collection
        else []
    )
    if operator.can("operator.analytics.read") or operator.can("operator.billing.read"):
        result["usage"] = {
            "production": {
                k: str(v)
                for k, v in (
                    await usage_for(session, tenant_id, account.production_environment_id)
                ).items()
            },
            "test": {
                k: str(v)
                for k, v in (
                    await usage_for(session, tenant_id, account.test_environment_id)
                ).items()
            },
        }
    await _audit(session, operator, "account_viewed", tenant_id)
    await session.commit()
    return result


class PauseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=200)


def _operator_scope(
    operator: OperatorContext, account: PiBusinessAccount, permissions: frozenset[str]
) -> WorkspaceScope:
    return WorkspaceScope.system(
        account.tenant_id,
        account.production_environment_id,
        permissions,
        f"Operator: {operator.label}"[:80],
    )


@router.post("/accounts/{tenant_id}/pause")
async def pause_account(
    tenant_id: UUID, data: PauseInput, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.accounts.manage")
    account = await account_for(session, operator, tenant_id)
    await onboarding.pause(
        session,
        _operator_scope(operator, account, frozenset({"pi.settings.manage"})),
        account,
        data.reason,
    )
    await _audit(session, operator, "account_paused", tenant_id, {"reason": data.reason})
    await session.commit()
    return {"setup_state": account.setup_state}


@router.post("/accounts/{tenant_id}/resume")
async def resume_account(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    """Resuming uses the same readiness checks as the customer's own launch."""
    operator.require("operator.accounts.manage")
    account = await account_for(session, operator, tenant_id)
    await onboarding.launch(
        session, _operator_scope(operator, account, frozenset({"pi.settings.manage"})), account
    )
    await _audit(session, operator, "account_resumed", tenant_id)
    await session.commit()
    return {"setup_state": account.setup_state}


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=200)


@router.post("/accounts/{tenant_id}/status")
async def account_status(
    tenant_id: UUID, data: StatusInput, operator: Operator, session: Session
) -> dict[str, Any]:
    """Suspend or reinstate a business (e.g. abuse). Suspension stops all sending;
    data is retained."""
    operator.require("operator.accounts.manage")
    account = await account_for(session, operator, tenant_id)
    account.status, account.suspended_by_workspace = data.status, False
    await _audit(session, operator, f"account_{data.status}", tenant_id, {"reason": data.reason})
    await session.commit()
    return {"status": account.status}


class SupportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scope: Literal["configuration", "conversations", "full_support"]
    reason: str = Field(min_length=5, max_length=300)
    days: int = Field(default=7, ge=1, le=30)


@router.post("/accounts/{tenant_id}/support-requests", status_code=201)
async def request_support_access(
    tenant_id: UUID, data: SupportRequest, operator: Operator, session: Session
) -> dict[str, Any]:
    """Ask the business for access. Nothing is granted until the business approves."""
    operator.require("operator.support.request")
    account = await account_for(session, operator, tenant_id)
    grant = PiSupportGrant(
        tenant_id=account.tenant_id,
        operator_user_id=operator.user_id,
        scope=data.scope,
        status="requested",
        reason=data.reason,
        requested_by="operator",
        expires_at=datetime.now(UTC) + timedelta(days=data.days),
    )
    session.add(grant)
    await session.flush()
    from app.modules.notifications.service import notify

    await notify(
        session,
        _operator_scope(operator, account, frozenset()),
        "pi.support_access_requested",
        "Our support team asked for access",
        data.reason,
        link="/settings/team?tab=support",
        permission="pi.support.grant",
        dedupe_key=f"pi-grant:{grant.id}",
    )
    await _audit(session, operator, "support_requested", tenant_id, {"scope": data.scope})
    await session.commit()
    return {"id": grant.id, "status": grant.status}


@router.put("/accounts/{tenant_id}/setup/{step}")
async def prepare_setup(
    tenant_id: UUID, step: int, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """ "Help me set up": prepare business details/offer/behaviour under a configuration
    grant. WhatsApp and payment authorization always remain with the business."""
    operator.require("operator.onboarding.assist")
    account = await account_for(session, operator, tenant_id)
    if await active_grant(session, operator, tenant_id, {"configuration", "full_support"}) is None:
        raise PermissionDenied
    from app.modules.pi_saas.app_routes import STEP_MODELS

    model = STEP_MODELS.get(step)
    if model is None or step == 3:
        raise BusinessRuleViolation("INVALID_STEP", "This step belongs to the business", 404)
    try:
        data = model.model_validate(await request.json())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    scope = _operator_scope(
        operator,
        account,
        frozenset({"pi.settings.manage", "pi.knowledge.manage", "catalog.write", "catalog.read"}),
    )
    await onboarding.save_step(session, scope, account, step, data)
    await _audit(session, operator, "setup_prepared", tenant_id, {"step": step})
    await session.commit()
    return {"setup_state": account.setup_state, "onboarding_step": account.onboarding_step}


@router.get("/accounts/{tenant_id}/conversations")
async def support_conversations(
    tenant_id: UUID, operator: Operator, session: Session, limit: int = Query(25, ge=1, le=100)
) -> list[dict[str, Any]]:
    """Customer content, only under an active conversation grant; every read is audited."""
    account = await account_for(session, operator, tenant_id)
    grant = await active_grant(session, operator, tenant_id, {"conversations", "full_support"})
    if grant is None:
        raise PermissionDenied
    rows = await session.scalars(
        select(PiConversation)
        .where(
            PiConversation.tenant_id == tenant_id,
            PiConversation.environment_id == account.production_environment_id,
        )
        .order_by(PiConversation.last_message_at.desc())
        .limit(limit)
    )
    await _audit(session, operator, "conversations_read", tenant_id, {"grant": str(grant.id)})
    await session.commit()
    return [
        {
            "id": c.id,
            "status": c.status,
            "mode": c.mode,
            "last_message_at": c.last_message_at,
            "preview": c.last_message_preview,
        }
        for c in rows
    ]


@router.get("/accounts/{tenant_id}/conversations/{conversation_id}/messages")
async def support_messages(
    tenant_id: UUID, conversation_id: UUID, operator: Operator, session: Session
) -> list[dict[str, Any]]:
    account = await account_for(session, operator, tenant_id)
    grant = await active_grant(session, operator, tenant_id, {"conversations", "full_support"})
    if grant is None:
        raise PermissionDenied
    rows = await session.scalars(
        select(PiMessage)
        .where(
            PiMessage.tenant_id == tenant_id,
            PiMessage.environment_id == account.production_environment_id,
            PiMessage.conversation_id == conversation_id,
        )
        .order_by(PiMessage.created_at.desc())
        .limit(100)
    )
    messages = [
        {
            "id": m.id,
            "sender": m.sender_type,
            "body": m.body,
            "status": m.status,
            "at": m.created_at,
        }
        for m in rows
    ]
    await _audit(
        session,
        operator,
        "messages_read",
        tenant_id,
        {"grant": str(grant.id), "conversation": str(conversation_id)},
    )
    await session.commit()
    return list(reversed(messages))


class NumberQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    environment: Literal["production", "test"] = "production"
    monthly_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    setup_fee: Decimal = Field(default=Decimal(0), ge=0, max_digits=10, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    phone_number_preview: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=300)


@router.post("/accounts/{tenant_id}/number-quote")
async def quote_number(
    tenant_id: UUID, data: NumberQuote, operator: Operator, session: Session
) -> dict[str, Any]:
    """Record the real price/availability obtained from the provider for a requested
    number. The business must confirm it before any provisioning link is prepared."""
    operator.require("operator.numbers.manage")
    account = await account_for(session, operator, tenant_id)
    row = await connections.connection_for(session, account, data.environment)
    request = dict(row.number_request or {})
    if request.get("status") not in {"requested", "quoted"}:
        raise BusinessRuleViolation("NO_REQUEST", "There is no open number request", 409)
    request.update(
        status="quoted",
        quote={
            "monthly_price": str(data.monthly_price),
            "setup_fee": str(data.setup_fee),
            "currency": data.currency,
            "number": data.phone_number_preview,
            "note": data.note,
            "quoted_at": datetime.now(UTC).isoformat(),
        },
    )
    row.number_request = request
    await _audit(session, operator, "number_quoted", tenant_id, {"quote": request["quote"]})
    await session.commit()
    return {"number_request": request}


@router.post("/accounts/{tenant_id}/number-link")
async def number_link(
    tenant_id: UUID,
    request: Request,
    operator: Operator,
    session: Session,
    environment: Literal["production", "test"] = "production",
) -> dict[str, Any]:
    """After the business confirmed the quote: create a provisioning setup link. The
    business still completes Meta authorization itself on the hosted page."""
    operator.require("operator.numbers.manage")
    account = await account_for(session, operator, tenant_id)
    row = await connections.connection_for(session, account, environment)
    number_request = dict(row.number_request or {})
    if number_request.get("status") != "confirmed":
        raise BusinessRuleViolation(
            "NOT_CONFIRMED", "The business has not confirmed the number price yet", 409
        )
    settings = request.app.state.settings
    kapso = Kapso(settings, request.app.state.http)
    if not row.external_customer_id:
        row.external_customer_id = await kapso.create_customer(
            account.name, f"{account.tenant_id}:{environment}"
        )
    base = settings.pi_app_public_url.rstrip("/")
    link = await kapso.create_setup_link(
        row.external_customer_id,
        success_url=f"{base}/settings/whatsapp/connected?environment={environment}",
        failure_url=f"{base}/settings/whatsapp/connected?environment={environment}&failed=1",
        connection_types=("dedicated",),
        provision_country=str(number_request.get("country") or ""),
    )
    row.setup_link_id, row.setup_link_url, row.status = link.id, link.url, "setup_pending"
    number_request["status"] = "link_ready"
    row.number_request = number_request
    await _audit(session, operator, "number_link_created", tenant_id)
    await session.commit()
    return {"status": row.status}


class SubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,32}$")
    status: Literal["trialing", "active", "past_due", "canceled", "suspended"] | None = None
    extend_trial_days: int | None = Field(default=None, ge=1, le=90)
    reason: str = Field(min_length=3, max_length=200)


@router.post("/accounts/{tenant_id}/subscription")
async def manage_subscription(
    tenant_id: UUID,
    data: SubscriptionInput,
    request: Request,
    operator: Operator,
    session: Session,
) -> dict[str, Any]:
    """Manual plan management (invoiced customers, goodwill trials). Audited."""
    operator.require("operator.billing.manage")
    await account_for(session, operator, tenant_id)
    subscription = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == tenant_id).with_for_update()
    )
    if subscription is None:
        raise ResourceNotFound
    before = {"plan": subscription.plan_key, "status": subscription.status}
    if data.plan:
        if await session.scalar(select(PiPlan.id).where(PiPlan.key == data.plan)) is None:
            raise BusinessRuleViolation("UNKNOWN_PLAN", "Unknown plan")
        subscription.plan_key = data.plan
    plan = await session.scalar(select(PiPlan).where(PiPlan.key == subscription.plan_key))
    free = plan is not None and plan.monthly_price is not None and plan.monthly_price == 0
    if data.status:
        subscription.status = data.status
        if data.status == "active" and free:
            # A free plan from the operator never expires (no billing period).
            subscription.billing_provider = "manual"
            subscription.current_period_start = datetime.now(UTC)
            subscription.current_period_end = subscription.grace_ends_at = None
        elif data.status == "active" and subscription.billing_provider == "manual":
            now = datetime.now(UTC)
            subscription.current_period_start = now
            subscription.current_period_end = now + timedelta(days=30)
            subscription.grace_ends_at = subscription.current_period_end + timedelta(days=7)
    if data.extend_trial_days:
        base = max(subscription.trial_ends_at or datetime.now(UTC), datetime.now(UTC))
        subscription.trial_ends_at = base + timedelta(days=data.extend_trial_days)
    await _audit(
        session,
        operator,
        "subscription_changed",
        tenant_id,
        {
            "before": before,
            "after": {"plan": subscription.plan_key, "status": subscription.status},
            "reason": data.reason,
        },
    )
    await session.flush()
    from app.modules.pi_saas import lifecycle_notify

    account = await account_for(session, operator, tenant_id)
    await lifecycle_notify.check(
        session, request.app.state.settings, request.app.state.http, account
    )
    await session.commit()
    current = await entitlement(session, tenant_id)
    return {
        "plan": subscription.plan_key,
        "status": subscription.status,
        "entitled": current.sending,
    }


@router.get("/plans")
async def plans(operator: Operator, session: Session) -> list[dict[str, Any]]:
    operator.require("operator.accounts.read")
    rows = await session.scalars(select(PiPlan).order_by(PiPlan.sort_order))
    return [
        {
            "key": p.key,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "monthly_price": str(p.monthly_price) if p.monthly_price is not None else None,
            "currency": p.currency,
            "trial_days": p.trial_days,
            "allowances": p.allowances,
            "features": p.features,
            "visibility": p.visibility,
            "sort_order": p.sort_order,
            "free": p.monthly_price is not None and p.monthly_price == 0,
            "stripe_price_configured": bool(p.stripe_price_id),
            "stripe_price_id": p.stripe_price_id if operator.can("operator.plans.manage") else None,
            "manual_monthly_price_pkr": str(p.manual_monthly_price_pkr)
            if p.manual_monthly_price_pkr is not None
            else None,
        }
        for p in rows
    ]


class PlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    status: Literal["draft", "available", "retired"] | None = None
    monthly_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    trial_days: int | None = Field(default=None, ge=0, le=90)
    manual_monthly_price_pkr: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    allowances: dict[str, int | None] | None = None
    stripe_price_id: str | None = Field(default=None, pattern=r"^price_[A-Za-z0-9]{6,100}$")
    visibility: Literal["public", "private"] | None = None
    features: list[str] | None = Field(default=None, max_length=20)
    sort_order: int | None = Field(default=None, ge=0, le=1000)


class PlanCreate(PlanUpdate):
    key: str = Field(pattern=r"^[a-z0-9_-]{2,32}$")
    name: str = Field(min_length=1, max_length=80)


ALLOWANCE_KEYS = {"messages", "ai_tokens", "media_items", "storage_mb", "seats", "numbers"}
# What a plan can include. "campaigns" is checked at send time; the rest are shown to
# businesses on the pricing page.
PLAN_FEATURES = (
    "inbox",
    "knowledge",
    "followups",
    "tools",
    "campaigns",
    "bookings",
    "payments",
    "forms",
    "digests",
    "priority_support",
)


def _check_plan(values: dict[str, Any]) -> None:
    if values.get("allowances") is not None:
        if set(values["allowances"]) - ALLOWANCE_KEYS or any(
            v is not None and v < 0 for v in values["allowances"].values()
        ):
            raise BusinessRuleViolation("INVALID_ALLOWANCES", "Unknown or negative allowance")
    if values.get("features") is not None:
        unknown = set(values["features"]) - set(PLAN_FEATURES)
        if unknown:
            raise BusinessRuleViolation(
                "INVALID_FEATURES", "Unknown feature: " + ", ".join(unknown)
            )
        values["features"] = [f for f in PLAN_FEATURES if f in values["features"]]


@router.get("/plan-features")
async def plan_features(operator: Operator) -> dict[str, Any]:
    operator.require("operator.accounts.read")
    return {"features": list(PLAN_FEATURES), "allowances": sorted(ALLOWANCE_KEYS)}


@router.post("/plans", status_code=201)
async def create_plan(data: PlanCreate, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.plans.manage")
    if await session.scalar(select(PiPlan.id).where(PiPlan.key == data.key)) is not None:
        raise BusinessRuleViolation("PLAN_EXISTS", "A plan with this key already exists", 409)
    values = data.model_dump(exclude_unset=True)
    _check_plan(values)
    plan = PiPlan(
        key=data.key,
        name=data.name,
        status="draft",
        allowances={},
        features=[],
        trial_days=0,
        sort_order=int(
            await session.scalar(select(func.coalesce(func.max(PiPlan.sort_order), 0))) or 0
        )
        + 10,
    )
    for field, value in values.items():
        if field != "key":
            setattr(plan, field, value)
    session.add(plan)
    await _audit(session, operator, "plan_created", None, {"plan": data.key})
    await session.commit()
    return next(p for p in await plans(operator, session) if p["key"] == data.key)


@router.delete("/plans/{key}")
async def delete_plan(
    key: str, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """Delete a plan nobody ever used; a used plan is retired instead (kept for history)."""
    operator.require("operator.plans.manage")
    plan = await session.scalar(select(PiPlan).where(PiPlan.key == key).with_for_update())
    if plan is None:
        raise ResourceNotFound
    if key == request.app.state.settings.pi_trial_plan:
        raise BusinessRuleViolation(
            "TRIAL_PLAN", "New businesses start on this plan. Choose another trial plan first."
        )
    used = await session.scalar(
        select(func.count()).select_from(PiSubscription).where(PiSubscription.plan_key == key)
    )
    from app.modules.pi_saas.payment_models import PiManualPayment

    paid = await session.scalar(
        select(func.count()).select_from(PiManualPayment).where(PiManualPayment.plan_key == key)
    )
    if used or paid:
        plan.status = "retired"
        outcome = "retired"
    else:
        await session.delete(plan)
        outcome = "deleted"
    await _audit(session, operator, f"plan_{outcome}", None, {"plan": key})
    await session.commit()
    return {"key": key, "result": outcome}


@router.put("/plans/{key}")
async def update_plan(
    key: str, data: PlanUpdate, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.plans.manage")
    plan = await session.scalar(select(PiPlan).where(PiPlan.key == key).with_for_update())
    if plan is None:
        raise ResourceNotFound
    values = data.model_dump(exclude_unset=True)
    _check_plan(values)
    for field, value in values.items():
        setattr(plan, field, value)
    await _audit(session, operator, "plan_updated", None, {"plan": key, "fields": sorted(values)})
    await session.commit()
    return next(p for p in await plans(operator, session) if p["key"] == key)


@router.get("/health")
async def operations_health(
    request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        **(await health(session, operator)),
        "configuration": {
            "whatsapp_provider": settings.kapso_api_key is not None,
            "provider_webhook_secret": settings.kapso_webhook_secret is not None,
            "billing": settings.pi_billing_stripe_secret_key is not None,
            "billing_webhook_secret": settings.pi_billing_stripe_webhook_secret is not None,
            "job_queue": settings.job_queue_mode,
            "ai_providers": [
                p for p in settings.provider_order() if getattr(settings, f"{p}_api_key")
            ],
        },
    }


@router.get("/events/failed")
async def failed_events(operator: Operator, session: Session) -> list[dict[str, Any]]:
    operator.require("operator.health.read")
    query = select(PiProviderEvent).where(PiProviderEvent.status == "failed")
    if not operator.can("operator.accounts.all"):
        query = query.where(
            PiProviderEvent.tenant_id.in_(
                select(PiOperatorAssignment.tenant_id).where(
                    PiOperatorAssignment.operator_id == operator.member_id
                )
            )
        )
    rows = await session.scalars(query.order_by(PiProviderEvent.created_at.desc()).limit(100))
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "tenant_id": e.tenant_id,
            "attempts": e.attempts,
            "error_code": e.error_code,
            "created_at": e.created_at,
        }
        for e in rows
    ]


@router.post("/events/{event_id}/replay")
async def replay_event(
    event_id: UUID, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """Controlled replay of a failed provider event (processing is idempotent)."""
    operator.require("operator.jobs.replay")
    event = await session.get(PiProviderEvent, event_id, with_for_update=True)
    if event is None or event.status != "failed":
        raise ResourceNotFound
    if event.tenant_id is not None:
        await account_for(session, operator, event.tenant_id)
    elif not operator.can("operator.accounts.all"):
        raise ResourceNotFound
    event.status, event.attempts, event.error_code = "received", 0, None
    await _audit(session, operator, "event_replayed", event.tenant_id, {"event": str(event_id)})
    await session.commit()
    await request.app.state.queue.enqueue(
        "process_pi_provider_event", str(event.id), job_id=f"pi-provider:{event.id}:replay"
    )
    return {"status": "queued"}


class TeamMemberInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    role: Literal[
        "owner", "operations_admin", "onboarding_specialist", "support", "billing", "analyst"
    ]
    overrides: list[str] = Field(default_factory=list, max_length=20)


@router.get("/team")
async def operator_team(operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.team.manage")
    rows = await session.execute(
        select(PiOperatorMember, PlatformUser)
        .join(PlatformUser, PlatformUser.id == PiOperatorMember.user_id)
        .order_by(PlatformUser.display_name)
    )
    return {
        "members": [
            {
                "id": m.id,
                "email": u.email,
                "name": u.display_name,
                "role": m.role,
                "status": m.status,
                "capabilities": sorted(capabilities_for(m)),
            }
            for m, u in rows
        ],
        "roles": {
            k: {"name": v[0], "description": v[1], "capabilities": sorted(v[2])}
            for k, v in ROLE_PRESETS.items()
        },
        "capabilities": list(CAPABILITIES),
    }


@router.post("/team", status_code=201)
async def add_operator(
    data: TeamMemberInput, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.team.manage")
    if set(o.lstrip("-") for o in data.overrides) - set(CAPABILITIES):
        raise BusinessRuleViolation("UNKNOWN_CAPABILITY", "Unknown capability")
    if data.role == "owner" and operator.role != "owner":
        raise PermissionDenied
    user = await session.scalar(
        select(PlatformUser).where(PlatformUser.email == data.email.strip().lower())
    )
    if user is None:
        raise BusinessRuleViolation(
            "USER_NOT_FOUND", "This person needs an Owner OS account first", 404
        )
    if user.id == operator.user_id:
        raise BusinessRuleViolation("OWN_ROLE", "Ask another operator owner to change your role")
    member = await session.scalar(
        select(PiOperatorMember).where(PiOperatorMember.user_id == user.id).with_for_update()
    )
    if operator.role != "owner":
        if member is not None and member.role == "owner":
            raise PermissionDenied  # Only owners change owners.
        # Nobody can hand out access they don't have themselves.
        wanted = capabilities_for(
            PiOperatorMember(user_id=user.id, role=data.role, overrides=data.overrides)
        )
        if not wanted <= operator.capabilities:
            raise BusinessRuleViolation(
                "CAPABILITY_NOT_HELD", "You can only grant access you have yourself", 403
            )
    if member is not None and member.role == "owner" and data.role != "owner":
        owners = await session.scalar(
            select(func.count())
            .select_from(PiOperatorMember)
            .where(PiOperatorMember.role == "owner", PiOperatorMember.status == "active")
        )
        if int(owners or 0) <= 1:
            raise BusinessRuleViolation("LAST_OWNER", "Keep at least one operator owner")
    if member is None:
        member = PiOperatorMember(
            user_id=user.id, role=data.role, added_by_user_id=operator.user_id
        )
        session.add(member)
    member.role, member.status, member.overrides = data.role, "active", data.overrides
    await session.flush()
    await _audit(
        session, operator, "operator_added", None, {"member": str(member.id), "new_role": data.role}
    )
    await session.commit()
    return {"id": member.id, "role": member.role, "capabilities": sorted(capabilities_for(member))}


@router.delete("/team/{member_id}", status_code=204)
async def revoke_operator(member_id: UUID, operator: Operator, session: Session) -> None:
    operator.require("operator.team.manage")
    member = await session.get(PiOperatorMember, member_id, with_for_update=True)
    if member is None:
        raise ResourceNotFound
    if member.role == "owner" and operator.role != "owner":
        raise PermissionDenied
    if member.role == "owner":
        owners = await session.scalar(
            select(func.count())
            .select_from(PiOperatorMember)
            .where(PiOperatorMember.role == "owner", PiOperatorMember.status == "active")
        )
        if int(owners or 0) <= 1:
            raise BusinessRuleViolation("LAST_OWNER", "Keep at least one operator owner")
    member.status = "revoked"
    await _audit(session, operator, "operator_revoked", None, {"member": str(member_id)})
    await session.commit()


class AssignmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: UUID


@router.post("/accounts/{tenant_id}/assignments", status_code=201)
async def assign_operator(
    tenant_id: UUID, data: AssignmentInput, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.team.manage")
    await account_for(session, operator, tenant_id)
    if await session.get(PiOperatorMember, data.operator_id) is None:
        raise ResourceNotFound
    exists = await session.scalar(
        select(PiOperatorAssignment.id).where(
            PiOperatorAssignment.operator_id == data.operator_id,
            PiOperatorAssignment.tenant_id == tenant_id,
        )
    )
    if exists is None:
        session.add(PiOperatorAssignment(operator_id=data.operator_id, tenant_id=tenant_id))
    await _audit(
        session, operator, "operator_assigned", tenant_id, {"operator": str(data.operator_id)}
    )
    await session.commit()
    return {"assigned": True}


@router.post("/agenta/ask")
async def agenta_ask(
    data: agenta.AskInput, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """Pi (Agenta): answers from the same operator functions and capabilities as the
    console. Never customer conversations."""
    if not await hit(request, "pi-agenta", str(operator.user_id), 30, 3600):
        raise HTTPException(status_code=429)
    from app.ai.manager import build_llm_manager

    # Without a configured model the gateway raises and the template answer is used.
    manager = build_llm_manager(
        request.app.state.settings, request.app.state.http, request.app.state.sessions
    )
    result = await agenta.ask(session, operator, data, manager)
    await session.commit()
    return result


@router.get("/summary")
async def summary(operator: Operator, session: Session) -> dict[str, Any]:
    """Pi Agenta's operator summary. Built only from the functions above, so it covers
    exactly the businesses and signals this operator may see (no customer content)."""
    operator.require("operator.accounts.read")
    items, total = await list_accounts(
        session, operator, search=None, state=None, page=1, page_size=100
    )
    by_state: dict[str, int] = {}
    for item in items:
        by_state[item["setup_state"]] = by_state.get(item["setup_state"], 0) + 1
    signals = await health(session, operator) if operator.can("operator.health.read") else None
    return {
        "businesses": total,
        "by_state": by_state,
        "needs_attention": [
            {"tenant_id": i["tenant_id"], "name": i["name"], "state": i["setup_state"]}
            for i in items
            if i["setup_state"] == "action_required"
            or i["subscription_status"] in {"past_due", "suspended"}
            or i["help_requested"]
        ][:20],
        "signals": signals,
        "generated_at": datetime.now(UTC),
    }
