"""Operator console: the WhatsApp number pool and each workspace's WhatsApp.

Viewing needs ``operator.accounts.read``; changing the pool or a workspace's number needs
``operator.numbers.manage``. Every change is audited. A permanent Meta token pasted to
connect a number is forwarded to Kapso once and never stored or logged.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Session
from app.modules.audit.service import record
from app.modules.environments.models import Environment
from app.modules.pi.models import WhatsAppConnection
from app.modules.pi_saas import connections, number_pool
from app.modules.pi_saas.models import PiBusinessAccount, PiPoolNumber, PiProviderConnection
from app.modules.pi_saas.operator import Operator
from app.shared.errors import ResourceNotFound

router = APIRouter(prefix="/operator", tags=["pi-operator-numbers"])


async def _audit(session: Any, operator: Any, action: str, details: dict[str, Any]) -> None:
    await record(
        session,
        f"pi_operator.{action}",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="pi_operator",
        entity_id=operator.member_id,
        details={"role": operator.role, **details},
        include_environment=False,
    )


async def _default_environment(session: Any, tenant_id: UUID) -> UUID:
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is not None:
        environment: UUID = account.production_environment_id
        return environment
    envs = list(
        await session.scalars(
            select(Environment)
            .where(Environment.tenant_id == tenant_id)
            .order_by(Environment.created_at)
        )
    )
    chosen: Environment | None = next(
        (e for e in envs if e.key == "production"), envs[0] if envs else None
    )
    if chosen is None:
        raise ResourceNotFound
    found: UUID = chosen.id
    return found


# ------------------------------------------------------------------------ the pool


@router.get("/pi/numbers")
async def numbers(request: Request, operator: Operator, session: Session) -> dict[str, Any]:
    """Every number in the Kapso project, where it's used, and the pool (synced now)."""
    operator.require("operator.accounts.read")
    settings, http = request.app.state.settings, request.app.state.http
    kapso = await number_pool.inventory(session, settings, http)
    pool = await session.scalars(select(PiPoolNumber).order_by(PiPoolNumber.created_at.desc()))
    await session.commit()
    return {
        **kapso,
        "pool": [number_pool.view(r, operator=True) for r in pool],
        "billing_mode": settings.kapso_meta_billing_mode,
        "webhook_url": connections.webhook_url(settings) or None,
    }


@router.post("/pi/numbers/connect", status_code=201)
async def connect_number(
    data: number_pool.ConnectInput, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.numbers.manage")
    row = await number_pool.connect_existing(
        session, request.app.state.settings, request.app.state.http, data
    )
    await _audit(session, operator, "pool_number_connected", {"number": row.display_phone_number})
    await session.commit()
    return number_pool.view(row, operator=True)


class ProvisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country: str = Field(default="US", pattern=r"^[A-Z]{2}$")


@router.post("/pi/numbers/provision")
async def provision_number(
    data: ProvisionInput, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """A Kapso link that adds a new pre-verified number to the pool (Kapso credits)."""
    operator.require("operator.numbers.manage")
    url = await number_pool.provisioning_link(
        session, request.app.state.settings, request.app.state.http, data.country
    )
    await _audit(session, operator, "pool_number_provisioning", {"country": data.country})
    await session.commit()
    return {"setup_url": url}


@router.patch("/pi/numbers/{pool_id}")
async def update_number(
    pool_id: UUID, data: number_pool.PoolUpdate, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.numbers.manage")
    row = await number_pool.update(session, pool_id, data)
    await _audit(session, operator, "pool_number_updated", {"number": row.display_phone_number})
    await session.commit()
    return number_pool.view(row, operator=True)


class OfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    environment_id: UUID | None = None


@router.post("/pi/numbers/{pool_id}/offer")
async def offer_number(
    pool_id: UUID, data: OfferInput, operator: Operator, session: Session
) -> dict[str, Any]:
    """Set a number aside for one business or workspace; they accept it themselves."""
    operator.require("operator.numbers.manage")
    environment_id = data.environment_id or await _default_environment(session, data.tenant_id)
    target = await connections.workspace_target(session, data.tenant_id, environment_id)
    row = await number_pool.offer(session, operator.user_id, pool_id, target)
    await session.commit()
    return number_pool.view(row, operator=True)


@router.post("/pi/numbers/{pool_id}/withdraw")
async def withdraw_offer(pool_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.numbers.manage")
    row = await number_pool.withdraw_offer(session, operator.user_id, pool_id)
    await _audit(session, operator, "pool_offer_withdrawn", {"number": row.display_phone_number})
    await session.commit()
    return number_pool.view(row, operator=True)


# ------------------------------------------------------- one workspace's WhatsApp


async def _workspace_whatsapp(session: Any, tenant_id: UUID) -> dict[str, Any]:
    environment_id = await _default_environment(session, tenant_id)
    provider = await session.scalar(
        select(PiProviderConnection).where(
            PiProviderConnection.tenant_id == tenant_id,
            PiProviderConnection.environment_id == environment_id,
        )
    )
    numbers = list(
        await session.scalars(
            select(WhatsAppConnection).where(
                WhatsAppConnection.tenant_id == tenant_id,
                WhatsAppConnection.environment_id == environment_id,
            )
        )
    )
    offered = await session.scalars(
        select(PiPoolNumber).where(
            PiPoolNumber.assigned_tenant_id == tenant_id,
            PiPoolNumber.status.in_(["reserved", "assigned"]),
        )
    )
    return {
        "environment_id": environment_id,
        "connection": {
            "status": provider.status,
            "display_phone_number": provider.display_phone_number,
            "connection_type": provider.connection_type,
            "health": provider.health or None,
            "problem": provider.last_error_code,
            "setup_pending": provider.status == "setup_pending",
        }
        if provider
        else {"status": "draft"},
        "numbers": [
            {
                "provider": n.provider,
                "display_phone_number": n.display_phone_number,
                "status": n.status,
                "last_inbound_at": n.last_inbound_at,
                "last_error_code": n.last_error_code,
            }
            for n in numbers
        ],
        "pool": [number_pool.view(r, operator=True) for r in offered],
    }


@router.get("/workspaces/{tenant_id}/whatsapp")
async def workspace_whatsapp(
    tenant_id: UUID, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    return await _workspace_whatsapp(session, tenant_id)


@router.post("/workspaces/{tenant_id}/whatsapp/health")
async def workspace_whatsapp_health(
    tenant_id: UUID, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    environment_id = await _default_environment(session, tenant_id)
    target = await connections.workspace_target(session, tenant_id, environment_id)
    await connections.check_health(
        session, request.app.state.settings, request.app.state.http, target, "production"
    )
    await session.commit()
    return await _workspace_whatsapp(session, tenant_id)


@router.get("/pi/whatsapp-usage")
async def whatsapp_usage(request: Request, operator: Operator, session: Session) -> dict[str, Any]:
    """This month's WhatsApp messages per business, from our own metering. Meta's fees
    are charged to the platform's Kapso credits (partner billing); the exact spend and
    balance are in Kapso's dashboard, because Kapso has no documented balance API."""
    operator.require("operator.billing.read")
    from sqlalchemy import func

    from app.modules.pi_saas.entitlement import month
    from app.modules.pi_saas.models import PiUsageCounter
    from app.modules.pi_saas.operator import visible_tenants
    from app.modules.tenants.models import Tenant

    metrics = ("messages_in", "messages_out", "template_messages")
    query = (
        select(PiUsageCounter.tenant_id, PiUsageCounter.metric, func.sum(PiUsageCounter.quantity))
        .where(PiUsageCounter.period == month(), PiUsageCounter.metric.in_(metrics))
        .group_by(PiUsageCounter.tenant_id, PiUsageCounter.metric)
    )
    assigned = visible_tenants(operator)
    if assigned is not None:
        query = query.where(PiUsageCounter.tenant_id.in_(assigned))
    rows = list(await session.execute(query))
    names = {
        t.id: t.name
        for t in await session.scalars(
            select(Tenant).where(Tenant.id.in_({r[0] for r in rows} or {None}))
        )
    }
    per: dict[Any, dict[str, int]] = {}
    for tenant_id, metric, quantity in rows:
        per.setdefault(tenant_id, dict.fromkeys(metrics, 0))[metric] = int(quantity or 0)
    businesses = sorted(
        (
            {"tenant_id": tenant_id, "name": names.get(tenant_id, ""), **values}
            for tenant_id, values in per.items()
        ),
        key=lambda b: -(b["messages_out"] + b["template_messages"]),
    )
    totals = {m: sum(b[m] for b in businesses) for m in metrics}
    return {
        "period": month().isoformat(),
        "billing_mode": request.app.state.settings.kapso_meta_billing_mode,
        "totals": totals,
        "businesses": businesses[:50],
        "kapso_dashboard": "https://app.kapso.ai",
    }
