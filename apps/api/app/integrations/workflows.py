"""Business event delivery through connected providers, with durable attempt history."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.integrations.email import EMAIL_KEYS, render_template
from app.integrations.errors import IntegrationError
from app.integrations.events import EVENT_TYPES
from app.integrations.http import CallContext, OutboundClient
from app.integrations.outbox import delivery_body
from app.integrations.registry import (
    EmailMessage,
    EmailProvider,
    MessagingProvider,
    OutboundWebhookProvider,
    ProviderContext,
)
from app.integrations.retry import backoff_seconds
from app.integrations.runtime import ConnectionRuntime
from app.integrations.workflow_models import IntegrationOperation, IntegrationWorkflow
from app.modules.audit.service import record
from app.modules.integrations.models import IntegrationConnection, OutboxEvent
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

NOTIFICATION_PROVIDERS = {*EMAIL_KEYS, "slack", "generic_webhook"}


def now() -> datetime:
    return datetime.now(UTC)


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    event_types: list[str] = Field(default_factory=list, max_length=40)
    recipients: list[EmailStr] = Field(default_factory=list, max_length=20)


def rule_view(row: IntegrationWorkflow | None) -> dict[str, Any]:
    return {
        "enabled": row.enabled if row else False,
        "event_types": row.event_types if row else [],
        "recipients": row.recipients if row else [],
    }


async def save_rule(
    session: AsyncSession, scope: WorkspaceScope, connection_id: UUID, data: WorkflowInput
) -> dict[str, Any]:
    scope.require("integrations.manage")
    connection = await WorkspaceRepository(session, IntegrationConnection, scope).get(
        connection_id, for_update=True
    )
    if connection.integration_key not in NOTIFICATION_PROVIDERS:
        raise BusinessRuleViolation(
            "UNSUPPORTED_WORKFLOW",
            "This provider uses its business feature instead of event alerts",
        )
    if set(data.event_types) - EVENT_TYPES.keys():
        raise BusinessRuleViolation("INVALID_EVENTS", "Choose supported business events")
    if data.enabled and (
        not data.event_types or connection.status not in {"connected", "degraded"}
    ):
        raise BusinessRuleViolation(
            "WORKFLOW_NOT_READY", "Verify the connection and choose at least one event"
        )
    if data.enabled and connection.integration_key in EMAIL_KEYS and not data.recipients:
        raise BusinessRuleViolation("RECIPIENT_REQUIRED", "Choose at least one email recipient")
    repo = WorkspaceRepository(session, IntegrationWorkflow, scope)
    row = await repo.find(IntegrationWorkflow.connection_id == connection_id)
    if row is None:
        row = await repo.add(repo.new(connection_id=connection_id))
    # Restart the eligibility window on changes, never replay older business events.
    row.enabled_at = now() if data.enabled else None
    row.enabled, row.event_types = data.enabled, sorted(set(data.event_types))
    row.recipients = sorted({str(address) for address in data.recipients})
    await record(
        session,
        "integration.workflow_configured",
        scope=scope,
        entity_type="integration_connection",
        entity_id=connection_id,
        details={"enabled": row.enabled, "event_types": row.event_types},
    )
    await session.flush()
    return rule_view(row)


async def fanout(session: AsyncSession, event: OutboxEvent) -> None:
    rules = await session.scalars(
        select(IntegrationWorkflow)
        .join(IntegrationConnection, IntegrationConnection.id == IntegrationWorkflow.connection_id)
        .where(
            IntegrationWorkflow.tenant_id == event.tenant_id,
            IntegrationWorkflow.environment_id == event.environment_id,
            IntegrationWorkflow.enabled.is_(True),
            IntegrationWorkflow.enabled_at <= event.created_at,
            IntegrationConnection.status.in_(("connected", "degraded")),
        )
    )
    for rule in rules:
        if (
            event.event_type not in rule.event_types
            or event.origin == f"workflow:{rule.connection_id}"
        ):
            continue
        # One durable task per recipient prevents partial-batch retries duplicating email.
        connection = await session.get(IntegrationConnection, rule.connection_id)
        assert connection is not None
        recipients: list[str | None] = (
            list(rule.recipients) if connection.integration_key in EMAIL_KEYS else [None]
        )
        for index, recipient in enumerate(recipients):
            await session.execute(
                insert(IntegrationOperation)
                .values(
                    tenant_id=event.tenant_id,
                    environment_id=event.environment_id,
                    connection_id=rule.connection_id,
                    outbox_event_id=event.id,
                    kind="notification",
                    dedupe_key=f"event:{event.id}:{rule.id}:{index}",
                    input={"recipient": recipient},
                    status="pending",
                )
                .on_conflict_do_nothing(constraint="uq_integration_operations_dedupe")
            )


async def deliver(
    session: AsyncSession,
    settings: Settings,
    http: OutboundClient,
    operation_id: UUID,
    redis: Any = None,
) -> str:
    op = await session.scalar(
        select(IntegrationOperation)
        .where(IntegrationOperation.id == operation_id, IntegrationOperation.kind == "notification")
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if op is None or op.status not in {"pending", "failed"}:
        return "skipped"
    if op.next_attempt_at and op.next_attempt_at > now():
        return "not_due"
    scope = WorkspaceScope.system(
        op.tenant_id, op.environment_id, frozenset(), "integration-worker"
    )
    connection = await WorkspaceRepository(session, IntegrationConnection, scope).get(
        op.connection_id
    )
    if connection.status in {"revoked", "disabled"}:
        op.status, op.last_error = "cancelled", "Connection disabled or disconnected"
        await session.commit()
        return op.status
    event = await session.get(OutboxEvent, op.outbox_event_id) if op.outbox_event_id else None
    if event is not None:
        rule = await WorkspaceRepository(session, IntegrationWorkflow, scope).find(
            IntegrationWorkflow.connection_id == connection.id
        )
        if not rule or not rule.enabled or event.event_type not in rule.event_types:
            op.status, op.last_error = "cancelled", "Workflow disabled or event removed"
            await session.commit()
            return op.status
        if (
            connection.integration_key in EMAIL_KEYS
            and op.input.get("recipient") not in rule.recipients
        ):
            op.status, op.last_error = "cancelled", "Recipient removed from workflow"
            await session.commit()
            return op.status
    if op.attempts and now() - op.created_at > timedelta(hours=23):
        op.status, op.last_error = "needs_review", "Automatic retry window has expired"
        await session.commit()
        return op.status
    op.status, op.attempts = "running", op.attempts + 1
    await session.commit()  # Durable claim before any external effect.
    runtime = ConnectionRuntime(session, settings, http, redis=redis)
    provider = runtime.provider(connection)
    title = (
        str(event.payload.get("title") or EVENT_TYPES.get(event.event_type, event.event_type))
        if event
        else str(op.input.get("title", "Workspace notification"))
    )
    message = (
        str(event.payload.get("body") or event.payload.get("number") or title)
        if event
        else str(op.input.get("message", title))
    )

    async def send(ctx: ProviderContext) -> dict[str, Any]:
        if isinstance(provider, EmailProvider):
            rendered = render_template(
                "system_alert",
                {
                    "severity": "info",
                    "title": title,
                    "message": message,
                    "workspace": "your workspace",
                },
            )
            result = await provider.send_email(
                ctx,
                EmailMessage(
                    to=[str(op.input["recipient"])],
                    subject=rendered.subject,
                    text=rendered.text,
                    html=rendered.html,
                    idempotency_key=str(op.id),
                ),
            )
            return {"provider_message_id": result.provider_message_id}
        if isinstance(provider, OutboundWebhookProvider) and event:
            status = await provider.deliver(ctx, event.event_type, str(op.id), delivery_body(event))
            return {"http_status": status}
        if isinstance(provider, MessagingProvider):
            result = await provider.send_text(ctx, "", f"{title}\n{message}"[:3000])
            return {"provider_message_id": result.provider_message_id}
        raise IntegrationError(
            "UNSUPPORTED_WORKFLOW", "This connection cannot deliver notifications"
        )

    try:
        result, _ = await runtime.call(
            connection,
            send,
            kind="workflow_send",
            call=CallContext(
                idempotent=connection.integration_key in {"resend", "generic_webhook"}
            ),
        )
        op.status, op.output, op.last_error, op.next_attempt_at = "succeeded", result, None, None
    except IntegrationError as error:
        op.last_error = error.message[:300]
        uncertain_server_error = connection.integration_key not in {
            "resend",
            "generic_webhook",
        } and (error.status == 408 or (error.status is not None and error.status >= 500))
        if (
            error.retryable
            and not uncertain_server_error
            and op.attempts < settings.delivery_max_attempts
        ):
            op.status = "failed"
            op.next_attempt_at = now() + timedelta(
                seconds=backoff_seconds(op.attempts, 30, 3600, error.retry_after)
            )
        else:
            op.status, op.next_attempt_at = "needs_review", None
    except Exception:
        op.status, op.last_error, op.next_attempt_at = (
            "needs_review",
            "Delivery outcome needs review before retrying",
            None,
        )
    await session.commit()
    return op.status


async def due(session: AsyncSession) -> list[UUID]:
    # A crash after send may have delivered the message: do not blindly send again.
    stale = await session.scalars(
        select(IntegrationOperation)
        .where(
            IntegrationOperation.kind == "notification",
            IntegrationOperation.status == "running",
            IntegrationOperation.updated_at < now() - timedelta(minutes=10),
        )
        .with_for_update(skip_locked=True)
    )
    for row in stale:
        row.status, row.last_error = (
            "needs_review",
            "Worker interrupted; check delivery before retrying",
        )
    rows = list(
        await session.scalars(
            select(IntegrationOperation.id)
            .where(
                IntegrationOperation.kind == "notification",
                or_(
                    IntegrationOperation.status == "pending",
                    and_(
                        IntegrationOperation.status == "failed",
                        IntegrationOperation.next_attempt_at <= now(),
                    ),
                ),
            )
            .order_by(IntegrationOperation.created_at)
            .limit(100)
        )
    )
    await session.commit()
    return rows


def operation_view(row: IntegrationOperation) -> dict[str, Any]:
    return {
        "id": row.id,
        "connection_id": row.connection_id,
        "kind": row.kind,
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "output": row.output,
    }
