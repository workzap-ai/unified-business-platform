"""Business review and notification settings (Pi app), and the operator's review queue
and "needs you" list."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.modules.access.dependencies import Scope, Session
from app.modules.pi_saas import lifecycle_notify, onboarding, verification
from app.modules.pi_saas.models import PiBusinessVerification, PiPoolNumber
from app.modules.pi_saas.operator import Operator, account_for, visible_tenants

router = APIRouter(tags=["pi-app-review"])
operator_router = APIRouter(prefix="/operator/pi", tags=["pi-operator-review"])


# ------------------------------------------------------------------ Pi app


@router.get("/business-review")
async def my_review(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    account = await onboarding.current_account(session, scope.tenant_id)
    row = await verification.for_tenant(session, account.tenant_id)
    await session.commit()
    return verification.view(row)


@router.put("/business-review")
async def save_review(data: verification.Details, scope: Scope, session: Session) -> dict[str, Any]:
    account = await onboarding.current_account(session, scope.tenant_id)
    row = await verification.save_details(session, scope, account, data)
    await session.commit()
    return verification.view(row)


@router.post("/business-review/submit")
async def submit_review(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    account = await onboarding.current_account(session, scope.tenant_id)
    row = await verification.submit(session, scope, account)
    await session.commit()
    return verification.view(row)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: dict[str, bool]


@router.get("/notification-settings")
async def notification_settings(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    account = await onboarding.current_account(session, scope.tenant_id)
    return {"categories": lifecycle_notify.preferences(account)}


@router.put("/notification-settings")
async def save_notification_settings(
    data: Preferences, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("pi.settings.manage")
    account = await onboarding.current_account(session, scope.tenant_id)
    prefs = dict(account.notification_prefs or {})
    for key, value in data.email.items():
        if key in lifecycle_notify.CATEGORIES:
            prefs[key] = bool(value)
    account.notification_prefs = prefs
    await session.commit()
    return {"categories": lifecycle_notify.preferences(account)}


# ------------------------------------------------------------------ operator


@operator_router.get("/reviews")
async def review_queue(
    operator: Operator,
    session: Session,
    status: str | None = Query(None, pattern=r"^(submitted|changes_requested|approved|rejected)$"),
    page: int = Query(1, ge=1, le=1000),
) -> dict[str, Any]:
    operator.require("operator.onboarding.assist")
    result = await verification.queue(session, status, page, 25, visible_tenants(operator))
    return result


@operator_router.get("/accounts/{tenant_id}/review")
async def account_review(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.onboarding.assist")
    account = await account_for(session, operator, tenant_id)
    row = await verification.for_tenant(session, account.tenant_id)
    await session.commit()
    return {"business": account.name, "tenant_id": account.tenant_id, **verification.view(row)}


@operator_router.post("/accounts/{tenant_id}/review")
async def decide_review(
    tenant_id: UUID,
    data: verification.Decision,
    request: Request,
    operator: Operator,
    session: Session,
) -> dict[str, Any]:
    operator.require("operator.accounts.manage")
    account = await account_for(session, operator, tenant_id)
    row = await verification.decide(session, operator.user_id, account.tenant_id, data)
    await lifecycle_notify.check(
        session, request.app.state.settings, request.app.state.http, account
    )
    await session.commit()
    return {"business": account.name, "tenant_id": account.tenant_id, **verification.view(row)}


@operator_router.get("/needs-you")
async def needs_you(operator: Operator, session: Session) -> dict[str, Any]:
    """What is waiting for the operator team right now (counts and links only)."""
    operator.require("operator.accounts.read")
    assigned = visible_tenants(operator)
    items: list[dict[str, Any]] = []

    def scoped(column: Any, statement: Any) -> Any:
        return statement if assigned is None else statement.where(column.in_(assigned))

    if operator.can("operator.onboarding.assist"):
        reviews = await session.scalar(
            scoped(
                PiBusinessVerification.tenant_id,
                select(func.count())
                .select_from(PiBusinessVerification)
                .where(PiBusinessVerification.status == "submitted"),
            )
        )
        if reviews:
            items.append(
                {
                    "kind": "reviews",
                    "count": int(reviews),
                    "label": "Businesses waiting for review",
                    "href": "/operator/reviews",
                }
            )
    if operator.can("operator.billing.read"):
        from app.modules.pi_saas.payment_models import PiManualPayment

        payments = await session.scalar(
            scoped(
                PiManualPayment.tenant_id,
                select(func.count())
                .select_from(PiManualPayment)
                .where(PiManualPayment.status == "submitted"),
            )
        )
        if payments:
            items.append(
                {
                    "kind": "payments",
                    "count": int(payments),
                    "label": "Bank or cash payments to verify",
                    "href": "/settings/pi-billing",
                }
            )
    held = await session.scalar(
        scoped(
            PiPoolNumber.assigned_tenant_id,
            select(func.count())
            .select_from(PiPoolNumber)
            .where(
                PiPoolNumber.status == "reserved",
                PiPoolNumber.held_until.is_not(None),
                PiPoolNumber.held_until > datetime.now(UTC),
            ),
        )
    )
    if held:
        items.append(
            {
                "kind": "held_numbers",
                "count": int(held),
                "label": "Numbers held until approval or payment",
                "href": "/operator/numbers",
            }
        )
    return {"items": items, "total": sum(i["count"] for i in items)}
