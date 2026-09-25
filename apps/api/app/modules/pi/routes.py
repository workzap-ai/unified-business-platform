import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.core.pagination import Page, Pagination
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.models import (
    PiHandoff,
    PiMessage,
    PiPendingAction,
    PiToolCall,
    WhatsAppConnection,
    WhatsAppWebhookEvent,
)
from app.modules.pi.runtime import system_scope
from app.modules.pi.schemas import (
    BodyInput,
    ConnectionInput,
    ConversationView,
    HandoffAction,
    HandoffInput,
    HandoffView,
    MessageView,
    StatusInput,
)
from app.modules.pi.service import PiService
from app.modules.pi.whatsapp import encrypt_token, normalize, verify_signature
from app.shared.errors import BusinessRuleViolation, Conflict
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi"])
webhook_router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])
Paging = Annotated[Pagination, Depends()]


@webhook_router.get("")
async def verify(request: Request) -> PlainTextResponse:
    settings = request.app.state.settings
    token = request.query_params.get("hub.verify_token", "")
    if (
        not settings.whatsapp_verify_token
        or request.query_params.get("hub.mode") != "subscribe"
        or not hmac.compare_digest(token, settings.whatsapp_verify_token.get_secret_value())
    ):
        raise HTTPException(403, "Verification failed")
    return PlainTextResponse(request.query_params.get("hub.challenge", "")[:200])


@webhook_router.post("")
async def receive(request: Request, session: Session) -> dict[str, bool]:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(413, "Webhook too large")
    if not verify_signature(
        bytes(body), request.headers.get("x-hub-signature-256", ""), request.app.state.settings
    ):
        raise HTTPException(403, "Invalid signature")
    try:
        payload = json.loads(body)
        events = normalize(payload)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise HTTPException(400, "Invalid webhook") from None
    queued = []
    for data in events:
        connection = await session.scalar(
            select(WhatsAppConnection).where(
                WhatsAppConnection.phone_number_id == data["number"],
                WhatsAppConnection.provider == "meta_cloud",
                WhatsAppConnection.status == "active",
            )
        )
        if not connection or not await system_scope(session, connection):
            continue
        if connection.verified_at is None:
            connection.verified_at = datetime.now(UTC)
        # Hash bounded provider identities, not customer content.
        event_key = hashlib.sha256(data["key"].encode()).hexdigest()
        event_id = await session.scalar(
            insert(WhatsAppWebhookEvent)
            .values(
                provider="meta_cloud",
                event_key=event_key,
                kind=data["kind"],
                tenant_id=connection.tenant_id,
                environment_id=connection.environment_id,
                connection_id=connection.id,
                phone_number_id=connection.phone_number_id,
                payload=data,
            )
            .on_conflict_do_update(
                constraint="uq_whatsapp_webhook_events_key",
                set_={"duplicate_count": WhatsAppWebhookEvent.duplicate_count + 1},
            )
            .returning(WhatsAppWebhookEvent.id)
        )
        queued.append(str(event_id))
    await session.commit()
    for queued_id in queued:
        await request.app.state.queue.enqueue(
            "process_pi_event", queued_id, job_id=f"pi:{queued_id}"
        )
    return {"received": True}


@router.get("/conversations", response_model=Page[ConversationView])
async def conversations(
    scope: Scope,
    session: Session,
    pagination: Paging,
    search: str | None = Query(None, max_length=100),
    status: Literal["open", "closed"] | None = None,
    mode: Literal["ai", "human"] | None = None,
) -> Page[ConversationView]:
    return await PiService(session, scope).search(pagination, search, status, mode)


def tool_summary(call: PiToolCall) -> str:
    label = call.tool_key.replace("_", " ")
    if call.status == "success":
        return f"{label}: completed"
    if call.status == "confirmation_required":
        return f"{label}: waiting for customer confirmation"
    return f"{label}: {call.status} ({call.error_code or 'refused'})"


async def message_views(
    session: Session, scope: Scope, conversation_id: UUID, rows: list[PiMessage]
) -> list[MessageView]:
    run_ids = {x.run_id for x in rows if x.run_id and x.sender_type == "ai"}
    calls: dict[UUID, list[dict[str, Any]]] = {}
    if run_ids:
        for call in await session.scalars(
            WorkspaceRepository(session, PiToolCall, scope)
            .select()
            .where(PiToolCall.run_id.in_(run_ids), PiToolCall.tool_key != "send_whatsapp_message")
            .order_by(PiToolCall.created_at)
        ):
            calls.setdefault(call.run_id, []).append(
                {
                    "tool": call.tool_key,
                    "status": "error" if call.status == "invalid" else call.status,
                    "summary": tool_summary(call),
                }
            )
    pending = list(
        await session.scalars(
            WorkspaceRepository(session, PiPendingAction, scope)
            .select()
            .where(PiPendingAction.conversation_id == conversation_id)
            .order_by(PiPendingAction.created_at.desc())
            .limit(20)
        )
    )
    now = datetime.now(UTC)
    result = []
    for row in rows:
        view = MessageView.model_validate(row)
        view.tool_events = calls.get(row.run_id, []) if row.run_id else []
        action = next(
            (a for a in pending if row.direction == "outbound" and row.body.startswith(a.summary)),
            None,
        )
        if action is not None:
            status = action.status
            if status == "pending" and action.expires_at <= now:
                status = "expired"
            view.confirmation = {
                "kind": "order_summary",
                "status": "expired" if status == "failed" else status,
                "reference": action.payload.get("reference", ""),
                "total": action.payload.get("total", ""),
                "currency": action.payload.get("currency", ""),
            }
        result.append(view)
    return result


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageView])
async def messages(
    conversation_id: UUID,
    scope: Scope,
    session: Session,
    before: datetime | None = None,
    limit: int = Query(100, ge=1, le=200),
) -> list[MessageView]:
    """Newest ``limit`` messages (optionally older than the ``before`` cursor), oldest first."""
    service = PiService(session, scope)
    await service.require()
    await service.conversations.get(conversation_id)
    query = service.messages.select().where(PiMessage.conversation_id == conversation_id)
    if before is not None:
        query = query.where(PiMessage.created_at < before)
    rows = list(await session.scalars(query.order_by(PiMessage.created_at.desc()).limit(limit)))
    return await message_views(session, scope, conversation_id, list(reversed(rows)))


@router.post("/conversations/{conversation_id}/messages", response_model=MessageView)
async def reply(
    conversation_id: UUID, data: BodyInput, request: Request, scope: Scope, session: Session
) -> MessageView:
    message = await PiService(session, scope).human_message(conversation_id, data.body)
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    await session.refresh(message)
    return MessageView.model_validate(message)


@router.post("/conversations/{conversation_id}/actions/{action}", response_model=ConversationView)
async def conversation_action(
    conversation_id: UUID,
    action: Literal["takeover", "return-to-ai", "close", "read"],
    scope: Scope,
    session: Session,
) -> ConversationView:
    service = PiService(session, scope)
    row = await service.mode(conversation_id, action)
    await session.commit()
    return await service.view(row)


@router.get("/handoffs", response_model=list[HandoffView])
async def handoffs(scope: Scope, session: Session, status: str | None = None) -> list[HandoffView]:
    service = PiService(session, scope)
    await service.require("pi.read", "handoff")
    query = service.handoffs.select()
    if status:
        query = query.where(PiHandoff.status == status)
    rows = await session.scalars(query.order_by(PiHandoff.created_at.desc()).limit(100))
    return [await service.handoff_view(row) for row in rows]


@router.post("/conversations/{conversation_id}/handoff", response_model=HandoffView)
async def create_handoff(
    conversation_id: UUID, data: HandoffInput, scope: Scope, session: Session
) -> HandoffView:
    service = PiService(session, scope)
    await service.require("pi.handoffs.manage", "handoff")
    row = await service.handoff(conversation_id, data.reason, data.summary)
    await session.commit()
    return await service.handoff_view(row)


@router.post("/handoffs/{handoff_id}/actions", response_model=HandoffView)
async def handoff_action(
    handoff_id: UUID, data: HandoffAction, scope: Scope, session: Session
) -> HandoffView:
    service = PiService(session, scope)
    await service.require("pi.handoffs.manage", "handoff")
    row = await service.update_handoff(handoff_id, data.action, data.assignee, data.note)
    await session.commit()
    return await service.handoff_view(row)


def connection_view(row: WhatsAppConnection) -> dict[str, Any]:
    keys = (
        "id",
        "provider",
        "phone_number_id",
        "display_phone_number",
        "business_account_id",
        "display_name",
        "status",
        "verified_at",
        "last_inbound_at",
        "last_outbound_at",
        "last_error_code",
        "last_error_at",
    )
    return {
        **{key: getattr(row, key) for key in keys},
        "has_access_token": bool(row.access_token_encrypted),
        "webhook_url": "/api/v1/webhooks/whatsapp",
        "webhook_verified": bool(row.verified_at),
        "messages_24h": {"inbound": 0, "outbound": 0, "failed": 0},
    }


@router.get("/whatsapp")
async def connection(scope: Scope, session: Session) -> dict[str, Any] | None:
    await PiService(session, scope).require("pi.whatsapp.manage")
    row = await WorkspaceRepository(session, WhatsAppConnection, scope).find()
    if not row:
        return None
    result = connection_view(row)
    # Actual message totals across this workspace; no synthetic delivery status.
    counts = await session.execute(
        select(PiMessage.direction, PiMessage.status, func.count())
        .where(
            PiMessage.tenant_id == scope.tenant_id,
            PiMessage.environment_id == scope.environment_id,
            PiMessage.created_at >= datetime.now(UTC) - timedelta(hours=24),
        )
        .group_by(PiMessage.direction, PiMessage.status)
    )
    for direction, state, count in counts:
        result["messages_24h"][direction] += count
        if state == "failed":
            result["messages_24h"]["failed"] += count
    return result


@router.put("/whatsapp")
async def save_connection(
    data: ConnectionInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.whatsapp.manage")
    repo = WorkspaceRepository(session, WhatsAppConnection, scope)
    row = await repo.find()
    if row and row.phone_number_id != data.phone_number_id:
        raise BusinessRuleViolation(
            "CONNECTION_IMMUTABLE", "Create a separate environment to connect a different number"
        )
    values = data.model_dump(exclude={"access_token"})
    if data.access_token:
        values["access_token_encrypted"] = encrypt_token(
            request.app.state.settings, data.access_token.get_secret_value()
        )
    try:
        if row is None:
            row = await repo.add(repo.new(provider="meta_cloud", **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
            await session.flush()
    except IntegrityError:
        await session.rollback()
        raise Conflict("This connection is unavailable") from None
    await record(
        session,
        "pi.connection_saved",
        scope=scope,
        entity_type="whatsapp_connection",
        entity_id=row.id,
    )
    await session.commit()
    result = await connection(scope, session)
    assert result is not None
    return result


@router.put("/whatsapp/status")
async def connection_status(data: StatusInput, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.whatsapp.manage")
    row = await WorkspaceRepository(session, WhatsAppConnection, scope).find()
    if row is None or (data.status == "active" and not row.access_token_encrypted):
        raise BusinessRuleViolation("CONNECTION_NOT_CONFIGURED", "Configure the connection first")
    row.status = data.status
    await record(
        session,
        "pi.connection_status",
        scope=scope,
        entity_type="whatsapp_connection",
        entity_id=row.id,
        details={"status": row.status},
    )
    await session.commit()
    result = await connection(scope, session)
    assert result is not None
    return result


@router.get("/whatsapp/events")
async def events(
    scope: Scope,
    session: Session,
    pagination: Paging,
    status: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.whatsapp.manage")
    query = select(WhatsAppWebhookEvent).where(
        WhatsAppWebhookEvent.tenant_id == scope.tenant_id,
        WhatsAppWebhookEvent.environment_id == scope.environment_id,
    )
    if status:
        query = query.where(WhatsAppWebhookEvent.status == status)
    if kind:
        query = query.where(WhatsAppWebhookEvent.kind == kind)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(WhatsAppWebhookEvent.created_at.desc())
        .limit(pagination.page_size)
        .offset(pagination.offset)
    )
    return {
        "items": [
            {
                **{
                    key: getattr(row, key)
                    for key in (
                        "id",
                        "event_key",
                        "kind",
                        "status",
                        "duplicate_count",
                        "attempts",
                        "error_code",
                        "created_at",
                        "processed_at",
                    )
                },
                "summary": f"WhatsApp {row.kind} receipt",
            }
            for row in rows
        ],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.post("/whatsapp/events/{event_id}/replay")
async def replay_event(
    event_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.whatsapp.manage")
    row = await session.scalar(
        select(WhatsAppWebhookEvent)
        .where(
            WhatsAppWebhookEvent.id == event_id,
            WhatsAppWebhookEvent.tenant_id == scope.tenant_id,
            WhatsAppWebhookEvent.environment_id == scope.environment_id,
        )
        .with_for_update()
    )
    if row is None:
        from app.shared.errors import ResourceNotFound

        raise ResourceNotFound
    if row.status not in {"failed", "received", "queued"}:
        raise BusinessRuleViolation(
            "EVENT_NOT_REPLAYABLE", "Only incomplete receipts can be retried"
        )
    row.status, row.attempts, row.error_code = "queued", 0, None
    await record(
        session,
        "pi.webhook_replayed",
        scope=scope,
        entity_type="whatsapp_webhook_event",
        entity_id=row.id,
    )
    await session.commit()
    await request.app.state.queue.enqueue(
        "process_pi_event", str(row.id), job_id=f"replay:{row.id}:{row.updated_at.isoformat()}"
    )
    return {
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "event_key",
                "kind",
                "status",
                "duplicate_count",
                "attempts",
                "error_code",
                "created_at",
                "processed_at",
            )
        },
        "summary": f"WhatsApp {row.kind} receipt",
    }
