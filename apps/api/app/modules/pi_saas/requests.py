"""The request desk: pi asks the team, the team answers, pi carries on.

    pi raises a request (a question it can't answer, a proposal to price or approve,
    a document to review, a meeting to arrange)  →  the team sees it in Requests
    (Owner OS and the pi app) and writes an answer for pi  →  the chat goes back to pi,
    which replies to the customer itself, in their language, using that answer.

The answer is a note *for pi* (facts to follow), never sent to the customer verbatim.
Answered requests and the team's conversation notes stay in pi's context for later
turns. Price and approve requests close by themselves once that proposal is sent.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.customers.models import Customer
from app.modules.notifications.service import notify
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi_saas.models import REQUEST_KINDS, PiConversationNote, PiStaffRequest
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)
DONE = ("answered", "published", "resolved")
TITLES = {
    "question": "pi needs an answer",
    "price": "Price a proposal",
    "review_document": "Review a customer's document",
    "approve": "Approve a proposal",
    "meeting": "Arrange a meeting",
    "other": "pi needs your help",
}


# ---- Raising and closing ----------------------------------------------------------------


async def raise_request(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    conversation_id: UUID,
    customer_id: UUID,
    kind: str,
    question: str,
    context: str = "",
    title: str = "",
    lead_id: UUID | None = None,
    quote_id: UUID | None = None,
    file_id: UUID | None = None,
    priority: str = "normal",
    link: str = "",
) -> PiStaffRequest:
    """One open request per chat, kind and linked record: asking again adds to it."""
    if kind not in REQUEST_KINDS:
        kind = "other"
    repo = WorkspaceRepository(session, PiStaffRequest, scope)
    existing = await repo.find(
        PiStaffRequest.conversation_id == conversation_id,
        PiStaffRequest.status == "open",
        PiStaffRequest.kind == kind,
        PiStaffRequest.quote_id == quote_id if quote_id else PiStaffRequest.quote_id.is_(None),
    )
    if existing is not None:
        if question not in existing.question:
            existing.question = f"{existing.question}\n\n{question}"[-4000:]
        if priority == "high":
            existing.priority = "high"
        return existing
    row = await repo.add(
        repo.new(
            conversation_id=conversation_id,
            customer_id=customer_id,
            question=question[:4000],
            context_summary=context[:4000],
            kind=kind,
            priority=priority,
            lead_id=lead_id,
            quote_id=quote_id,
            file_id=file_id,
        )
    )
    await notify(
        session,
        scope,
        f"pi.request.{kind}",
        title or TITLES[kind],
        question[:200],
        link=link or f"/pi/requests?request={row.id}",
        permission="pi.inbox.reply",
        severity="warning" if priority == "high" else "info",
        dedupe_key=f"pi-request:{row.id}",
    )
    return row


async def resolve_for_quote(
    session: AsyncSession, scope: WorkspaceScope, quote_id: UUID, note: str
) -> None:
    """The proposal went out: its price/approve requests are done."""
    rows = await session.scalars(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(
            PiStaffRequest.quote_id == quote_id,
            PiStaffRequest.status == "open",
            PiStaffRequest.kind.in_(["price", "approve"]),
        )
    )
    for row in rows:
        row.status, row.answer = "resolved", row.answer or note
        row.resolved_at = datetime.now(UTC)


# ---- Answering --------------------------------------------------------------------------


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    save_as_knowledge: bool = False


async def answer(
    session: AsyncSession,
    scope: WorkspaceScope,
    request_id: UUID,
    text: str,
    *,
    save_as_knowledge: bool,
    max_bytes: int,
) -> PiStaffRequest:
    """The team's answer for pi. The chat goes back to pi; the caller queues pi's reply."""
    from app.modules.pi.service import PiService
    from app.modules.pi_saas.teach import DraftInput, _first_line, create_draft, publish_draft

    scope.require("pi.inbox.reply")
    repo = WorkspaceRepository(session, PiStaffRequest, scope)
    row = await repo.get(request_id, for_update=True)
    if row.status != "open":
        raise BusinessRuleViolation("REQUEST_CLOSED", "This request was already answered")
    service = PiService(session, scope)
    conversation = await service.conversations.get(row.conversation_id, for_update=True)
    if conversation.mode == "human":
        await service.mode(conversation.id, "return-to-ai")
    row.answer, row.answered_by_user_id = text, scope.user_id
    row.status, row.resolved_at = "answered", datetime.now(UTC)
    if save_as_knowledge:
        draft = await create_draft(
            session,
            scope,
            DraftInput(title=_first_line(row.question), content=f"Q: {row.question}\n\nA: {text}"),
            origin="ask_owner",
            staff_request_id=row.id,
        )
        if scope.can("pi.knowledge.publish"):
            published = await publish_draft(session, scope, draft.id, max_bytes)
            row.knowledge_document_id = published.published_document_id
            row.status = "published"
    await record(
        session,
        "pi_saas.staff_request_answered",
        scope=scope,
        entity_type="pi_staff_request",
        entity_id=row.id,
        details={"kind": row.kind, "knowledge": save_as_knowledge},
    )
    return row


async def team_notes(
    session: AsyncSession, scope: WorkspaceScope, conversation_id: UUID
) -> list[dict[str, str]]:
    """What the team told pi about this chat: answered requests and internal notes."""
    notes: list[dict[str, str]] = []
    try:
        async with session.begin_nested():
            answered = await session.scalars(
                WorkspaceRepository(session, PiStaffRequest, scope)
                .select()
                .where(
                    PiStaffRequest.conversation_id == conversation_id,
                    PiStaffRequest.status.in_(DONE),
                    PiStaffRequest.answer.is_not(None),
                )
                .order_by(PiStaffRequest.created_at.desc())
                .limit(5)
            )
            notes += [
                {"kind": f"answer to: {r.question[:300]}", "note": str(r.answer)[:1500]}
                for r in answered
            ]
            internal = await session.scalars(
                WorkspaceRepository(session, PiConversationNote, scope)
                .select()
                .where(PiConversationNote.conversation_id == conversation_id)
                .order_by(PiConversationNote.created_at.desc())
                .limit(5)
            )
            notes += [{"kind": "team note", "note": n.body[:1500]} for n in internal]
    except DBAPIError:
        logger.warning("pi_team_notes_unavailable", exc_info=True)
    return notes


# ---- pi replies with the team's answer --------------------------------------------------


async def reply_with_answer(ctx: dict[str, Any], request_id: str) -> None:
    """Job: pi writes the customer a reply that uses the team's answer. Inside the
    24-hour window only; otherwise the answer waits in pi's context for their next
    message. Never runs while the team holds the chat."""
    from app.ai.manager import build_llm_manager
    from app.modules.pi.configuration import settings_row
    from app.modules.pi.guard import ReplyRejected
    from app.modules.pi.runtime import enqueue_sends
    from app.modules.pi.service_conversation import compose_service_turn, prepare_context
    from app.modules.pi_saas.deals import system_scope_for

    async with ctx["sessions"]() as session:
        row = await session.get(PiStaffRequest, UUID(request_id))
        if row is None or row.status not in DONE or not row.answer:
            return
        scope = await system_scope_for(session, row.tenant_id, row.environment_id)
        conversation = await WorkspaceRepository(session, PiConversation, scope).get(
            row.conversation_id
        )
        now = datetime.now(UTC)
        if conversation.mode == "human" or not conversation.last_inbound_at:
            return
        if conversation.last_inbound_at < now - WINDOW:
            return
        key = f"pi-team-answer:{row.id}"
        repo = WorkspaceRepository(session, PiMessage, scope)
        if await repo.find(PiMessage.idempotency_key == key) is not None:
            return
        latest = await session.scalar(
            repo.select()
            .where(
                PiMessage.conversation_id == conversation.id,
                PiMessage.direction == "inbound",
            )
            .order_by(PiMessage.created_at.desc())
            .limit(1)
        )
        if latest is None:
            return
        policy = await settings_row(session, scope)
        context = await prepare_context(session, scope, conversation, latest, policy)
        context["team_answer_now"] = {"question": row.question[:1500], "answer": row.answer}
        await session.commit()  # No transaction is held across the model call.
        manager = build_llm_manager(ctx["settings"], ctx["http"], ctx["sessions"])
        body: str | None
        try:
            body = (await compose_service_turn(manager, scope, conversation, policy, context)).reply
        except (ReplyRejected, Exception):  # noqa: BLE001 - see the fallback below
            logger.warning("pi_team_answer_reply_failed", exc_info=True)
            # A customer's question still gets its answer: as the team wrote it. Other
            # kinds (internal notes on prices, approvals) are never sent verbatim.
            body = row.answer if row.kind == "question" else None
        if not body:
            return
        message = await repo.add(
            repo.new(
                conversation_id=conversation.id,
                direction="outbound",
                sender_type="ai",
                agent_key="requirement",
                body=body,
                status="queued",
                idempotency_key=key,
            )
        )
        conversation.last_message_at = datetime.now(UTC)
        conversation.last_message_preview = body[:200]
        row.reply_message_id = message.id
        await session.commit()
        await enqueue_sends(ctx, [str(message.id)])


async def enqueue_reply(request: Request, request_id: UUID) -> None:
    await request.app.state.queue.enqueue(
        "pi_reply_with_team_answer", str(request_id), job_id=f"pi-team-answer:{request_id}"
    )


# ---- API --------------------------------------------------------------------------------

router = APIRouter(prefix="/pi/requests", tags=["pi-requests"])


async def view(
    session: AsyncSession, scope: WorkspaceScope, rows: list[PiStaffRequest]
) -> list[dict[str, Any]]:
    names = {
        c.id: c.name
        for c in await session.scalars(
            WorkspaceRepository(session, Customer, scope)
            .select()
            .where(Customer.id.in_([r.customer_id for r in rows] or [None]))
        )
    }
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "priority": r.priority,
            "status": r.status,
            "question": r.question,
            "context": r.context_summary,
            "answer": r.answer,
            "conversation_id": r.conversation_id,
            "customer_id": r.customer_id,
            "customer_name": names.get(r.customer_id),
            "lead_id": r.lead_id,
            "quote_id": r.quote_id,
            "file_id": r.file_id,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r in rows
    ]


@router.get("")
async def list_requests(
    scope: Scope,
    session: Session,
    status: Literal["open", "done", "all"] = Query("open"),
) -> dict[str, Any]:
    from app.modules.pi.service import PiService

    scope.require("pi.read")
    service = PiService(session, scope)
    visible = service.conversations.select().with_only_columns(PiConversation.id)
    query = (
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(PiStaffRequest.conversation_id.in_(visible))
    )
    if status == "open":
        query = query.where(PiStaffRequest.status == "open")
    elif status == "done":
        query = query.where(PiStaffRequest.status != "open")
    rows = list(await session.scalars(query.order_by(PiStaffRequest.created_at.desc()).limit(200)))
    open_count = sum(1 for r in rows if r.status == "open") if status != "done" else 0
    return {"items": await view(session, scope, rows), "open": open_count}


@router.post("/{request_id}/answer")
async def answer_request(
    request_id: UUID, data: AnswerInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    from app.modules.pi.service import PiService

    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id)
    await PiService(session, scope).conversations.get(row.conversation_id)  # visibility
    row = await answer(
        session,
        scope,
        request_id,
        data.answer,
        save_as_knowledge=data.save_as_knowledge,
        max_bytes=request.app.state.settings.knowledge_upload_max_bytes,
    )
    await session.commit()
    await enqueue_reply(request, row.id)
    return (await view(session, scope, [row]))[0]


@router.post("/{request_id}/dismiss")
async def dismiss_request(request_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.inbox.reply")
    row = await WorkspaceRepository(session, PiStaffRequest, scope).get(request_id, for_update=True)
    if row.status == "open":
        row.status, row.resolved_at = "dismissed", datetime.now(UTC)
    await session.commit()
    return (await view(session, scope, [row]))[0]
