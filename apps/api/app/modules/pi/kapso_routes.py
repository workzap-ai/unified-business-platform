"""WhatsApp through Kapso for Owner OS workspaces (/pi/whatsapp/kapso, /pi/whatsapp/numbers).

The same connection lifecycle as standalone Pi businesses:
- **Pool number:** the workspace chooses a number from the platform's pool, or accepts
  one an operator offered.
- **Own number:** the workspace authorizes its own number on Kapso's hosted setup page.

Either way, no Meta keys are pasted. The platform's Kapso project key stays on the
server.
"""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.pi.service import require_pi
from app.modules.pi_saas import connections, number_pool
from app.modules.pi_saas.models import PiProviderConnection

router = APIRouter(prefix="/pi/whatsapp", tags=["pi-whatsapp-kapso"])


class KapsoSetup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_types: list[Literal["coexistence", "dedicated"]] = Field(
        default=["coexistence", "dedicated"], min_length=1, max_length=2
    )


class KapsoDisconnect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remove_from_provider: bool = False


def _view(row: PiProviderConnection | None) -> dict[str, Any]:
    if row is None:
        return {"status": "draft"}
    return {
        "status": row.status,
        "display_phone_number": row.display_phone_number,
        "connection_type": row.connection_type,
        "setup_url": row.setup_link_url if row.status == "setup_pending" else None,
        "health": row.health or None,
        "health_checked_at": row.health_checked_at,
        "problem": row.last_error_code,
    }


async def _target(session: Any, scope: Any) -> connections.Target:
    return await connections.workspace_target(session, scope.tenant_id, scope.environment_id)


@router.get("/kapso")
async def kapso_status(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.read")
    row = await session.scalar(
        select(PiProviderConnection).where(
            PiProviderConnection.tenant_id == scope.tenant_id,
            PiProviderConnection.environment_id == scope.environment_id,
        )
    )
    settings = request.app.state.settings
    return {
        "connection": _view(row),
        "provider_available": settings.kapso_api_key is not None,
        "webhook_ready": bool(connections.webhook_url(settings))
        and bool(settings.kapso_webhook_secret),
    }


@router.post("/kapso/setup")
async def kapso_setup(
    data: KapsoSetup, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.whatsapp.manage")
    target = await _target(session, scope)
    row = await connections.start_setup(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        target,
        connections.SetupRequest(connection_types=data.connection_types),
    )
    await session.commit()
    return _view(row)


@router.post("/kapso/confirm")
async def kapso_confirm(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.whatsapp.manage")
    target = await _target(session, scope)
    row = await connections.confirm_setup(
        session, request.app.state.settings, request.app.state.http, scope, target, "production"
    )
    await session.commit()
    return _view(row)


@router.post("/kapso/health")
async def kapso_health(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.read")
    target = await _target(session, scope)
    row = await connections.check_health(
        session, request.app.state.settings, request.app.state.http, target, "production"
    )
    await session.commit()
    return _view(row)


@router.post("/kapso/disconnect")
async def kapso_disconnect(
    data: KapsoDisconnect, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.whatsapp.manage")
    target = await _target(session, scope)
    row = await connections.disconnect(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        target,
        "production",
        data.remove_from_provider,
    )
    await session.commit()
    return _view(row)


@router.get("/numbers")
async def available_numbers(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await require_pi(session, scope, "pi.whatsapp.manage")
    target = await _target(session, scope)
    return [
        {**number_pool.view(n), "offered_to_you": n.status == "reserved"}
        for n in await number_pool.available(session, target)
    ]


@router.post("/numbers/{pool_id}/choose")
async def choose_number(
    pool_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.whatsapp.manage")
    target = await _target(session, scope)
    row = await number_pool.choose(
        session, request.app.state.settings, request.app.state.http, scope, target, pool_id
    )
    await session.commit()
    return _view(row)
