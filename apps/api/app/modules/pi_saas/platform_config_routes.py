"""Operator dashboard: platform keys (Kapso, AI, Stripe, email, Google, Shopify ...).

Only operators with ``operator.settings.manage`` (owners) can see or change them. Values
are write-only: secrets come back as a hint, and the audit log records which key changed,
never its value.
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict

from app.modules.access.dependencies import Session
from app.modules.audit.service import record
from app.modules.pi_saas import platform_config
from app.modules.pi_saas.operator import Operator

router = APIRouter(prefix="/operator/pi/platform-keys", tags=["pi-operator-platform"])


class KeyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any


async def _audit(session: Any, operator: Any, action: str, key: str) -> None:
    await record(
        session,
        f"pi_operator.platform_key_{action}",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="platform_setting",
        details={"key": key},
        include_environment=False,
    )


@router.get("")
async def list_keys(request: Request, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.settings.manage")
    settings = request.app.state.settings
    await platform_config.refresh(session, settings, max_age=0)
    return platform_config.listing(settings)


@router.get("/env-template", response_class=PlainTextResponse)
async def env_template(request: Request, operator: Operator, all: bool = False) -> str:
    operator.require("operator.settings.manage")
    return platform_config.env_template(request.app.state.settings, only_missing=not all)


@router.put("/{key}")
async def save_key(
    key: str, data: KeyValue, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.settings.manage")
    spec = await platform_config.save(
        session, request.app.state.settings, key, data.value, operator.user_id
    )
    await _audit(session, operator, "saved", spec.name)
    await session.commit()
    return _item(request, spec.name)


@router.delete("/{key}")
async def remove_key(
    key: str, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.settings.manage")
    spec = await platform_config.remove(session, request.app.state.settings, key)
    await _audit(session, operator, "removed", spec.name)
    await session.commit()
    return _item(request, spec.name)


@router.post("/{key}/test")
async def test_key(key: str, request: Request, operator: Operator) -> dict[str, Any]:
    operator.require("operator.settings.manage")
    return await platform_config.test(request.app.state.settings, request.app.state.http, key)


def _item(request: Request, name: str) -> dict[str, Any]:
    listing = platform_config.listing(request.app.state.settings)
    item: dict[str, Any] = next(i for i in listing["items"] if i["key"] == name)
    return {**item, "missing_required": listing["missing_required"]}
