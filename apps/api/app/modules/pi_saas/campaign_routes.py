"""Campaigns, customer consent and template checks (/pi/...).

Mounted for the Pi app. Viewing campaigns needs
``pi.campaigns.read``; creating, scheduling or cancelling needs ``pi.campaigns.manage``.
Recording a customer's consent needs ``customers.write``.
"""

from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.access.dependencies import Scope, Session
from app.modules.customers.models import Customer
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi.service import require_pi
from app.modules.pi_saas import campaigns as cmp
from app.modules.pi_saas.models import PiCampaign, PiCustomerConsent
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-campaigns"])


def template_checker(request: Request, session: Session) -> Any:
    settings, http = request.app.state.settings, request.app.state.http

    async def check(connection: WhatsAppConnection, template: dict[str, str]) -> str:
        from app.integrations.whatsapp_bridge import token
        from app.modules.pi.whatsapp import WhatsApp

        whatsapp = WhatsApp(settings, http, connection.provider)
        try:
            return await whatsapp.template_body(
                connection.business_account_id or "",
                template,
                await token(session, settings, connection),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise BusinessRuleViolation(
                "TEMPLATE_CHECK_UNAVAILABLE",
                "WhatsApp didn't answer. Try again in a minute.",
                503,
            ) from None

    return check


@router.get("/campaigns")
async def list_campaigns(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.campaigns.read")
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiCampaign, scope)
            .select()
            .order_by(PiCampaign.created_at.desc())
            .limit(100)
        )
    )
    return [cmp.view(row, await cmp.results(session, scope, row)) for row in rows]


@router.get("/campaigns/audience")
async def campaign_audience(
    scope: Scope, session: Session, tag: str | None = Query(None, max_length=40)
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.read")
    return {
        "count": await cmp.audience_size(session, scope, tag or None),
        "plan_allows": await cmp.plan_allows_campaigns(session, scope.tenant_id),
        "whatsapp_connected": (await cmp.production_connection(session, scope)) is not None,
    }


@router.post("/campaigns", status_code=201)
async def create_campaign(
    data: cmp.CampaignInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.manage")
    row = await cmp.create(session, scope, data)
    await session.commit()
    return cmp.view(row, await cmp.results(session, scope, row))


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.read")
    row = await WorkspaceRepository(session, PiCampaign, scope).get(campaign_id)
    return cmp.view(row, await cmp.results(session, scope, row))


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: UUID, data: cmp.CampaignInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.manage")
    row = await cmp.update(session, scope, campaign_id, data)
    await session.commit()
    return cmp.view(row)


@router.post("/campaigns/{campaign_id}/schedule")
async def schedule_campaign(
    campaign_id: UUID,
    data: cmp.ScheduleInput,
    request: Request,
    scope: Scope,
    session: Session,
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.manage")
    row = await cmp.schedule(
        session, scope, campaign_id, data.scheduled_at, template_checker(request, session)
    )
    await session.commit()
    return cmp.view(row)


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.campaigns.manage")
    row = await cmp.cancel(session, scope, campaign_id)
    await session.commit()
    return cmp.view(row, await cmp.results(session, scope, row))


class TemplateQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=cmp.TEMPLATE_NAME)
    language: str = Field(pattern=cmp.TEMPLATE_LANGUAGE)


@router.post("/whatsapp/templates/check")
async def check_template(
    data: TemplateQuery, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Is this template approved for this number? Used by campaigns and reminders."""
    await require_pi(session, scope, "pi.read")
    if not (scope.can("pi.campaigns.manage") or scope.can("pi.settings.manage")):
        await require_pi(session, scope, "pi.campaigns.manage")
    connection = await cmp.production_connection(session, scope)
    if connection is None or not connection.business_account_id:
        raise BusinessRuleViolation("WHATSAPP_NOT_CONNECTED", "Connect your WhatsApp number first")
    try:
        body = await template_checker(request, session)(connection, data.model_dump())
    except BusinessRuleViolation as exc:
        if exc.code == "TEMPLATE_CHECK_UNAVAILABLE":
            raise
        return {"approved": False, "code": exc.code, "message": exc.message}
    return {"approved": True, "body": body[:1000]}


# ------------------------------------------------------------------------ consent


def _consent_view(row: PiCustomerConsent) -> dict[str, Any]:
    return {
        "purpose": row.purpose,
        "status": row.status,
        "source": row.source,
        "updated_at": row.updated_at,
    }


@router.get("/customers/{customer_id}/consent")
async def customer_consent(
    customer_id: UUID, scope: Scope, session: Session
) -> list[dict[str, Any]]:
    await require_pi(session, scope, "customers.read")
    await WorkspaceRepository(session, Customer, scope).get(customer_id)
    rows = await session.scalars(
        WorkspaceRepository(session, PiCustomerConsent, scope)
        .select()
        .where(PiCustomerConsent.customer_id == customer_id)
    )
    return [_consent_view(r) for r in rows]


@router.put("/customers/{customer_id}/consent")
async def set_customer_consent(
    customer_id: UUID, data: cmp.ConsentInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "customers.write")
    await WorkspaceRepository(session, Customer, scope).get(customer_id)
    source = data.source or f"Withdrawn by {scope.actor_label}"
    row = await cmp.set_consent(session, scope, customer_id, data.purpose, data.granted, source)
    await session.flush()
    await session.refresh(row)  # updated_at is set by the database
    view = _consent_view(row)
    await session.commit()
    return view
