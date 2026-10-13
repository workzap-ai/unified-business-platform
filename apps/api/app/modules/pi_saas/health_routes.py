"""pi Health routes (Owner OS): the live state, "Fix now", the owner's one-click fixes
and "Run tests now". See health.py and health_selftest.py."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.knowledge import KnowledgeService
from app.modules.pi.models import KnowledgeDocument, WhatsAppWebhookEvent
from app.modules.pi.service import PiService
from app.modules.pi_saas import health, health_selftest
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi/health", tags=["pi-health"])


def _enqueue(request: Request) -> health.Enqueue:
    async def enqueue(name: str, arg: str, job_id: str) -> bool:
        return bool(await request.app.state.queue.enqueue(name, arg, job_id=job_id))

    return enqueue


@router.get("")
async def get_health(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.read")
    return await health.state(session, scope, request.app.state.settings)


@router.post("/heal")
async def heal_now(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """Run pi's safe automatic fixes for this business now."""
    await PiService(session, scope).require("pi.settings.manage")
    state = request.app.state
    ctx = health.Context(
        enqueue=_enqueue(request),
        settings=state.settings,
        http=state.http,
        sessions=getattr(state, "sessions", None),
    )
    fixes = await health.heal_scope(session, scope, ctx)
    return {**await health.state(session, scope, state.settings), "fixes": fixes}


@router.post("/fix/{key}")
async def fix_one(
    key: Literal["whatsapp_failed_events", "knowledge_failed"],
    request: Request,
    scope: Scope,
    session: Session,
) -> dict[str, Any]:
    """The owner's button for a fix pi doesn't do on its own."""
    service = PiService(session, scope)
    count = 0
    if key == "whatsapp_failed_events":
        # Same as replaying each receipt on WhatsApp → Events, for the last 24 hours.
        await service.require("pi.whatsapp.manage")
        rows = list(
            await session.scalars(
                select(WhatsAppWebhookEvent)
                .where(
                    WhatsAppWebhookEvent.tenant_id == scope.tenant_id,
                    WhatsAppWebhookEvent.environment_id == scope.environment_id,
                    WhatsAppWebhookEvent.kind == "message",
                    WhatsAppWebhookEvent.status.in_(["failed", "received", "queued"]),
                    WhatsAppWebhookEvent.attempts >= 3,
                    WhatsAppWebhookEvent.created_at >= datetime.now(UTC) - timedelta(hours=24),
                )
                .limit(50)
                .with_for_update()
            )
        ) + list(
            await session.scalars(
                select(WhatsAppWebhookEvent)
                .where(
                    WhatsAppWebhookEvent.tenant_id == scope.tenant_id,
                    WhatsAppWebhookEvent.environment_id == scope.environment_id,
                    WhatsAppWebhookEvent.kind == "message",
                    WhatsAppWebhookEvent.status == "failed",
                    WhatsAppWebhookEvent.attempts < 3,
                    WhatsAppWebhookEvent.created_at >= datetime.now(UTC) - timedelta(hours=24),
                )
                .limit(50)
                .with_for_update()
            )
        )
        for row in rows:
            row.status, row.attempts, row.error_code = "queued", 0, None
            await record(
                session,
                "pi.webhook_replayed",
                scope=scope,
                entity_type="whatsapp_webhook_event",
                entity_id=row.id,
            )
        await session.commit()
        for row in rows:
            await request.app.state.queue.enqueue(
                "process_pi_event",
                str(row.id),
                job_id=f"replay:{row.id}:{row.updated_at.isoformat()}",
            )
        count = len(rows)
    else:
        await service.require("pi.knowledge.manage", "knowledge")
        knowledge = KnowledgeService(session, scope)
        docs = list(
            await session.scalars(
                WorkspaceRepository(session, KnowledgeDocument, scope)
                .select()
                .where(KnowledgeDocument.status == "failed")
                .limit(20)
                .with_for_update()
            )
        )
        for doc in docs:
            await knowledge.reindex(doc)
        await session.commit()
        for doc in docs:
            await request.app.state.queue.enqueue(
                "index_document",
                str(doc.id),
                job_id=f"index-retry:{doc.id}:{doc.updated_at.isoformat()}",
            )
        count = len(docs)
    return {**await health.state(session, scope, request.app.state.settings), "fixed": count}


@router.post("/self-test")
async def self_test(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """Run pi's self-tests now (real, metered AI calls; nothing is sent)."""
    await PiService(session, scope).require("pi.settings.manage")
    state = request.app.state
    await health_selftest.run_self_tests(
        session, scope, state.settings, state.http, state.sessions, record_scope=scope
    )
    return await health.state(session, scope, state.settings)
