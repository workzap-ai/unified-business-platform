"""The business's own email (SMTP, Resend or SendGrid), set up from the pi app.

pi already sends with it when it exists (payment-link and receipt emails, booking and
summary emails, the email tool); without it, the platform address is the fallback.
One email connection per business: saving a new one retires the old one. Secret
fields are stored encrypted and never returned; the form only says they are set.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.catalog import REGISTRY
from app.integrations.email import EMAIL_KEYS
from app.modules.integrations.models import IntegrationConnection
from app.modules.integrations.schemas import ConnectionCreate
from app.modules.integrations.service import IntegrationService, Runtime
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

USABLE = ("connected", "degraded")


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(pattern=r"^[a-z_]{2,40}$")
    values: dict[str, str] = Field(default_factory=dict, max_length=20)


def providers() -> list[dict[str, Any]]:
    result = []
    for key in EMAIL_KEYS:
        definition = REGISTRY.definition(key)
        if definition is None or not definition.connectable:
            continue
        result.append(
            {
                "key": key,
                "name": definition.name,
                "description": definition.description,
                "fields": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "type": f.type,
                        "required": f.required,
                        "secret": f.secret,
                        "help": f.help or "",
                        "options": [{"value": v, "label": label} for v, label in f.options],
                    }
                    for f in definition.config_schema
                ],
            }
        )
    return result


async def current(
    session: AsyncSession, scope: WorkspaceScope, *, for_update: bool = False
) -> IntegrationConnection | None:
    query = (
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .where(
            IntegrationConnection.integration_key.in_(EMAIL_KEYS),
            IntegrationConnection.status != "revoked",
        )
        .order_by(IntegrationConnection.created_at.desc())
        .limit(1)
    )
    if for_update:
        query = query.with_for_update()
    row: IntegrationConnection | None = await session.scalar(query)
    return row


def view(settings: Settings, row: IntegrationConnection | None) -> dict[str, Any]:
    connection = None
    if row is not None:
        state = (
            "connected"
            if row.status in USABLE
            else "connecting"
            if row.status in ("draft", "connecting")
            else "action_required"
        )
        connection = {
            "provider": row.integration_key,
            "state": state,
            "from_address": str(row.config.get("from_address") or ""),
            "from_name": str(row.config.get("from_name") or ""),
            "values": {k: str(v) for k, v in row.config.items() if not k.startswith("__")},
            "secrets_set": sorted(k for k in row.credential_hints if not k.startswith("__")),
            "problem": (row.last_error or "") if state != "connected" else "",
            "last_checked_at": row.last_health_check_at,
        }
    return {
        "providers": providers(),
        "connection": connection,
        "platform_fallback": bool(settings.platform_smtp_host),
    }


async def save(
    session: AsyncSession, scope: WorkspaceScope, rt: Runtime, data: EmailInput
) -> dict[str, Any]:
    scope.require("integrations.manage")
    definition = REGISTRY.definition(data.provider)
    if data.provider not in EMAIL_KEYS or definition is None or not definition.connectable:
        raise BusinessRuleViolation("UNKNOWN_PROVIDER", "Choose SMTP, Resend or SendGrid", 422)
    secret = {f.key for f in definition.config_schema if f.secret}
    known = {f.key for f in definition.config_schema}
    values = {k: v.strip() for k, v in data.values.items() if k in known}
    service = IntegrationService(session, scope, rt)
    old = await current(session, scope, for_update=True)
    credentials = {k: v for k, v in values.items() if k in secret and v}
    if old is not None and old.integration_key == data.provider:
        # Blank secret fields keep what is saved (the form never shows them).
        for key in secret - set(credentials):
            stored = service.runtime().context(old).credentials.get(key)
            if stored:
                credentials[key] = stored
    config: dict[str, Any] = {k: v for k, v in values.items() if k not in secret and v != ""}
    row = await service.create(
        ConnectionCreate(
            integration_key=data.provider,
            display_name=definition.name,
            mode="production",
            config=config,
            credentials=credentials,
        )
    )
    if old is not None:
        await service.disconnect(old.id)
    await session.flush()
    result = await service.run_test(row)
    return {"ok": result.ok, "message": result.message, **view(rt.settings, row)}


async def test(session: AsyncSession, scope: WorkspaceScope, rt: Runtime) -> dict[str, Any]:
    scope.require("integrations.manage")
    row = await current(session, scope, for_update=True)
    if row is None:
        raise BusinessRuleViolation("NOT_CONNECTED", "Set up email first", 409)
    result = await IntegrationService(session, scope, rt).run_test(row)
    return {"ok": result.ok, "message": result.message, **view(rt.settings, row)}


async def disconnect(session: AsyncSession, scope: WorkspaceScope, rt: Runtime) -> None:
    scope.require("integrations.manage")
    row = await current(session, scope, for_update=True)
    if row is not None:
        await IntegrationService(session, scope, rt).disconnect(row.id)


async def status(session: AsyncSession, settings: Settings, scope: WorkspaceScope) -> Any:
    scope.require("integrations.read")
    return view(settings, await current(session, scope))
