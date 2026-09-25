"""Link a verified integration connection to PI without a second credential setup."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.crypto import CredentialManager
from app.modules.integrations.models import InboundEvent, IntegrationConnection
from app.modules.pi.models import WhatsAppConnection, WhatsAppWebhookEvent
from app.modules.pi.service import PiService
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


async def activate(
    session: AsyncSession, settings: Settings, scope: WorkspaceScope, connection_id: UUID
) -> dict[str, Any]:
    scope.require("integrations.manage")
    await PiService(session, scope).require("pi.whatsapp.manage")
    integration = await WorkspaceRepository(session, IntegrationConnection, scope).get(
        connection_id, for_update=True
    )
    if integration.integration_key != "whatsapp_meta" or integration.status not in {
        "connected",
        "degraded",
    }:
        raise BusinessRuleViolation("CONNECTION_NOT_READY", "Verify the WhatsApp connection first")
    credentials = CredentialManager(settings).decrypt_json(integration.credentials_encrypted)
    if (
        not credentials.get("access_token")
        or not (credentials.get("app_secret") or settings.whatsapp_app_secret)
        or not credentials.get("verify_token")
    ):
        raise BusinessRuleViolation(
            "WEBHOOK_REQUIRED",
            "Configure the access token, app secret and webhook verification token",
        )
    repo = WorkspaceRepository(session, WhatsAppConnection, scope)
    row = await repo.find()
    number = str(integration.config["phone_number_id"])
    if row and (
        row.phone_number_id != number or row.integration_connection_id not in {None, integration.id}
    ):
        raise BusinessRuleViolation(
            "WHATSAPP_ALREADY_CONNECTED",
            "This environment already uses another WhatsApp connection",
        )
    # A phone number can belong to only one workspace, including legacy PI connections.
    foreign = await session.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.phone_number_id == number)
    )
    if foreign and (row is None or foreign.id != row.id):
        raise BusinessRuleViolation(
            "WHATSAPP_ALREADY_CONNECTED", "This WhatsApp number is already in use"
        )
    if row is None:
        row = await repo.add(
            repo.new(
                provider="meta_cloud",
                phone_number_id=number,
                display_phone_number=number,
                display_name=integration.display_name,
            )
        )
    row.integration_connection_id = integration.id
    row.access_token_encrypted = CredentialManager(settings).encrypt(
        str(credentials["access_token"])
    )
    row.business_account_id = str(integration.config.get("business_account_id", ""))
    row.status = "active"
    await session.flush()
    return {"status": "active", "connection_id": str(row.id)}


async def receive(session: AsyncSession, event: InboundEvent) -> UUID | None:
    data = event.payload or {}
    connection = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.tenant_id == event.tenant_id,
            WhatsAppConnection.environment_id == event.environment_id,
            WhatsAppConnection.integration_connection_id == event.connection_id,
            WhatsAppConnection.status == "active",
        )
    )
    if connection is None or data.get("phone_number_id") != connection.phone_number_id:
        return None
    if connection.verified_at is None:
        connection.verified_at = datetime.now(UTC)
    status = event.event_type == "message.status"
    mid = str(data.get("message_id", ""))
    raw_key = f"{connection.phone_number_id}:{mid}" + (f":{data.get('status')}" if status else "")
    payload = {
        "key": raw_key,
        "kind": "status" if status else "message",
        "number": connection.phone_number_id,
        "message_id": mid,
        "sender": data.get("from", ""),
        "profile": None,
        "message_type": data.get("type", "other"),
        "body": data.get("text", ""),
        "media_id": data.get("media_id"),
        "state": data.get("status"),
    }
    return await session.scalar(
        insert(WhatsAppWebhookEvent)
        .values(
            tenant_id=event.tenant_id,
            environment_id=event.environment_id,
            provider="meta_cloud",
            connection_id=connection.id,
            phone_number_id=connection.phone_number_id,
            event_key=hashlib.sha256(raw_key.encode()).hexdigest(),
            kind=payload["kind"],
            payload=payload,
        )
        .on_conflict_do_update(
            constraint="uq_whatsapp_webhook_events_key",
            set_={"duplicate_count": WhatsAppWebhookEvent.duplicate_count + 1},
        )
        .returning(WhatsAppWebhookEvent.id)
    )


async def token(session: AsyncSession, settings: Settings, connection: WhatsAppConnection) -> str:
    from app.modules.pi.whatsapp import decrypt_token

    if connection.integration_connection_id:
        linked = await session.get(IntegrationConnection, connection.integration_connection_id)
        if linked is None or linked.status not in {"connected", "degraded"}:
            raise BusinessRuleViolation("CONNECTION_INACTIVE", "The linked integration is disabled")
        return str(
            CredentialManager(settings).decrypt_json(linked.credentials_encrypted)["access_token"]
        )
    return decrypt_token(settings, connection.access_token_encrypted)
