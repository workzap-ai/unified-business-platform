"""Shared-inbox collaboration: assignment, internal notes, tags, saved replies, reply
approval and the customer profile. Used by both the Owner OS PI workspace and the
standalone Pi app. Every route goes through ``PiService.conversations``, so members who
may only see assigned conversations cannot reach others by id.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.access.dependencies import Scope, Session
from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.memberships.models import Membership
from app.modules.pi.models import PiConversation, PiHandoff, PiMemory, PiMessage
from app.modules.pi.schemas import MessageView
from app.modules.pi.service import ACTIVE_HANDOFF, PiService
from app.modules.pi_saas.models import (
    PiBooking,
    PiConversationNote,
    PiConversationTag,
    PiCustomerConsent,
    PiSavedReply,
    PiStaffRequest,
    PiTask,
    PiTicket,
)
from app.modules.tenants.context import active_memberships
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-inbox"])


class AssignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID | None = None


class NoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str = Field(min_length=1, max_length=4000)


class TagInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tag: str = Field(min_length=1, max_length=40, pattern=r"^[\w\- ]+$")


class SavedReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    body: str | None = Field(default=None, min_length=1, max_length=4000)


@router.post("/conversations/{conversation_id}/assign")
async def assign(
    conversation_id: UUID, data: AssignInput, scope: Scope, session: Session
) -> dict[str, Any]:
    service = PiService(session, scope)
    await service.require("pi.inbox.assign")
    conversation = await service.conversations.get(conversation_id, for_update=True)
    label = None
    if data.user_id is not None:
        membership = await session.scalar(
            active_memberships(data.user_id).where(Membership.tenant_id == scope.tenant_id)
        )
        if membership is None:
            raise ResourceNotFound
        grants, _ = await membership_grants(session, scope.tenant_id, membership.id)
        if "pi.read" not in grants:
            raise BusinessRuleViolation(
                "ASSIGNEE_NO_ACCESS", "This person can't use the inbox. Change their role first."
            )
        user = await session.get(PlatformUser, data.user_id)
        label = user.display_name if user else None
    conversation.assigned_user_id = data.user_id
    await record(
        session,
        "pi.conversation_assigned",
        scope=scope,
        entity_type="pi_conversation",
        entity_id=conversation.id,
        details={"assignee": str(data.user_id) if data.user_id else None},
    )
    await session.commit()
    return {"conversation_id": conversation.id, "assigned_user_id": data.user_id, "label": label}


@router.get("/conversations/{conversation_id}/notes")
async def notes(conversation_id: UUID, scope: Scope, session: Session) -> list[dict[str, Any]]:
    service = PiService(session, scope)
    await service.require("pi.inbox.notes")
    await service.conversations.get(conversation_id)
    rows = await session.scalars(
        WorkspaceRepository(session, PiConversationNote, scope)
        .select()
        .where(PiConversationNote.conversation_id == conversation_id)
        .order_by(PiConversationNote.created_at.desc())
        .limit(100)
    )
    return [
        {"id": r.id, "body": r.body, "author": r.author_label, "created_at": r.created_at}
        for r in rows
    ]


@router.post("/conversations/{conversation_id}/notes", status_code=201)
async def add_note(
    conversation_id: UUID, data: NoteInput, scope: Scope, session: Session
) -> dict[str, Any]:
    service = PiService(session, scope)
    await service.require("pi.inbox.notes")
    await service.conversations.get(conversation_id)
    repo = WorkspaceRepository(session, PiConversationNote, scope)
    row = await repo.add(
        repo.new(
            conversation_id=conversation_id,
            author_user_id=scope.user_id,
            author_label=scope.actor_label,
            body=data.body,
        )
    )
    await session.commit()
    return {
        "id": row.id,
        "body": row.body,
        "author": row.author_label,
        "created_at": row.created_at,
    }


@router.get("/conversations/{conversation_id}/tags")
async def tags(conversation_id: UUID, scope: Scope, session: Session) -> list[str]:
    service = PiService(session, scope)
    await service.require()
    await service.conversations.get(conversation_id)
    rows = await session.scalars(
        WorkspaceRepository(session, PiConversationTag, scope)
        .select()
        .with_only_columns(PiConversationTag.tag)
        .where(PiConversationTag.conversation_id == conversation_id)
        .order_by(PiConversationTag.tag)
    )
    return list(rows)


@router.post("/conversations/{conversation_id}/tags", status_code=201)
async def add_tag(
    conversation_id: UUID, data: TagInput, scope: Scope, session: Session
) -> list[str]:
    service = PiService(session, scope)
    await service.require("pi.inbox.reply")
    await service.conversations.get(conversation_id)
    await session.execute(
        insert(PiConversationTag)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            conversation_id=conversation_id,
            tag=data.tag.lower(),
        )
        .on_conflict_do_nothing(constraint="uq_pi_conversation_tag")
    )
    await session.commit()
    return await tags(conversation_id, scope, session)


@router.delete("/conversations/{conversation_id}/tags/{tag}")
async def remove_tag(conversation_id: UUID, tag: str, scope: Scope, session: Session) -> list[str]:
    service = PiService(session, scope)
    await service.require("pi.inbox.reply")
    await service.conversations.get(conversation_id)
    await session.execute(
        delete(PiConversationTag).where(
            WorkspaceRepository(session, PiConversationTag, scope).predicate(),
            PiConversationTag.conversation_id == conversation_id,
            PiConversationTag.tag == tag.lower()[:40],
        )
    )
    await session.commit()
    return await tags(conversation_id, scope, session)


@router.get("/saved-replies")
async def saved_replies(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.inbox.reply")
    rows = await session.scalars(
        WorkspaceRepository(session, PiSavedReply, scope)
        .select()
        .order_by(PiSavedReply.title)
        .limit(200)
    )
    return [{"id": r.id, "title": r.title, "body": r.body} for r in rows]


@router.post("/saved-replies", status_code=201)
async def add_saved_reply(data: SavedReplyInput, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.settings.manage")
    repo = WorkspaceRepository(session, PiSavedReply, scope)
    if await repo.find(PiSavedReply.title == data.title):
        raise Conflict("A saved reply with this title already exists")
    row = await repo.add(repo.new(title=data.title, body=data.body))
    await session.commit()
    return {"id": row.id, "title": row.title, "body": row.body}


@router.delete("/saved-replies/{reply_id}", status_code=204)
async def delete_saved_reply(reply_id: UUID, scope: Scope, session: Session) -> None:
    await PiService(session, scope).require("pi.settings.manage")
    repo = WorkspaceRepository(session, PiSavedReply, scope)
    await repo.delete(await repo.get(reply_id))
    await session.commit()


async def _pending_reply(
    service: PiService, conversation_id: UUID, message_id: UUID
) -> tuple[PiConversation, PiMessage]:
    await service.require("pi.inbox.reply")
    conversation = await service.conversations.get(conversation_id, for_update=True)
    message = await service.messages.get(message_id, for_update=True)
    if message.conversation_id != conversation.id or message.status != "pending_approval":
        raise BusinessRuleViolation("NOT_AWAITING_APPROVAL", "This reply is no longer waiting", 409)
    return conversation, message


@router.post("/conversations/{conversation_id}/messages/{message_id}/approve")
async def approve_reply(
    conversation_id: UUID,
    message_id: UUID,
    data: ApprovalInput,
    request: Request,
    scope: Scope,
    session: Session,
) -> MessageView:
    """Approve (optionally edit) a reply PI drafted. Delivery still re-checks takeover,
    connection, plan and the messaging window at send time."""
    service = PiService(session, scope)
    conversation, message = await _pending_reply(service, conversation_id, message_id)
    edited = data.body is not None and data.body != message.body
    if data.body is not None:
        message.body = data.body
    message.status = "queued"
    message.media = {
        **message.media,
        "approved_by": str(scope.user_id),
        "approved_at": datetime.now(UTC).isoformat(),
        "edited": edited,
    }
    if edited:
        message.sender_type = "human"  # The approver authored the final text.
        message.sent_by_user_id, message.sent_by_label = scope.user_id, scope.actor_label
    await record(
        session,
        "pi.reply_approved",
        scope=scope,
        entity_type="pi_message",
        entity_id=message.id,
        details={"edited": edited},
    )
    await session.commit()
    await request.app.state.queue.enqueue(
        "send_pi_message", str(message.id), job_id=f"send:{message.id}"
    )
    await session.refresh(message)
    return MessageView.model_validate(message)


@router.post("/conversations/{conversation_id}/messages/{message_id}/reject")
async def reject_reply(
    conversation_id: UUID, message_id: UUID, scope: Scope, session: Session
) -> MessageView:
    service = PiService(session, scope)
    _, message = await _pending_reply(service, conversation_id, message_id)
    message.status, message.error_code = "skipped", "REJECTED_BY_TEAM"
    await record(
        session, "pi.reply_rejected", scope=scope, entity_type="pi_message", entity_id=message.id
    )
    await session.commit()
    await session.refresh(message)
    return MessageView.model_validate(message)


@router.get("/approvals")
async def approvals(scope: Scope, session: Session) -> list[dict[str, Any]]:
    """Replies waiting for approval in conversations this member may see."""
    service = PiService(session, scope)
    await service.require("pi.inbox.reply")
    rows = await session.execute(
        service.messages.select()
        .add_columns(PiConversation.customer_id)
        .join(
            PiConversation,
            (PiConversation.id == PiMessage.conversation_id)
            & (PiConversation.tenant_id == PiMessage.tenant_id),
        )
        .where(
            PiMessage.status == "pending_approval",
            PiMessage.conversation_id.in_(
                service.conversations.select().with_only_columns(PiConversation.id)
            ),
        )
        .order_by(PiMessage.created_at)
        .limit(100)
    )
    return [
        {
            "message_id": m.id,
            "conversation_id": m.conversation_id,
            "customer_id": customer_id,
            "body": m.body,
            "created_at": m.created_at,
        }
        for m, customer_id in rows
    ]


@router.get("/customers/{customer_id}/profile")
async def customer_profile(customer_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Everything the team knows about one customer, limited by the viewer's access."""
    service = PiService(session, scope)
    await service.require()
    customer = await service.customers.get(customer_id)
    visible = service.conversations.select().where(PiConversation.customer_id == customer_id)
    conversations = list(
        await session.scalars(visible.order_by(PiConversation.last_message_at.desc()).limit(20))
    )
    if not conversations and not scope.can("pi.inbox.all"):
        raise ResourceNotFound
    result: dict[str, Any] = {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email if scope.can("customers.read") else None,
            "tags": customer.tags,
            "created_at": customer.created_at,
        },
        "conversations": [
            {
                "id": c.id,
                "status": c.status,
                "mode": c.mode,
                "last_message_at": c.last_message_at,
                "summary": c.summary,
                "language": c.language,
                "requirements": (c.service_brief or {}).get("requirements", {}),
            }
            for c in conversations
        ],
        "memory": [],
        "consents": [],
        "open_issues": [],
        "bookings": [],
        "tasks": [],
    }
    if scope.can("pi.memory.read"):
        rows = await session.scalars(
            WorkspaceRepository(session, PiMemory, scope)
            .select()
            .where(PiMemory.customer_id == customer_id, PiMemory.status == "active")
            .order_by(PiMemory.created_at.desc())
            .limit(50)
        )
        result["memory"] = [
            {
                "id": m.id,
                "content": m.content,
                "kind": m.kind,
                "source_message_id": m.source_message_id,
                "created_at": m.created_at,
                "last_used_at": m.last_used_at,
            }
            for m in rows
        ]
    consents = await session.scalars(
        WorkspaceRepository(session, PiCustomerConsent, scope)
        .select()
        .where(PiCustomerConsent.customer_id == customer_id)
    )
    result["consents"] = [
        {"purpose": c.purpose, "status": c.status, "source": c.source, "updated_at": c.updated_at}
        for c in consents
    ]
    for c in conversations:
        brief = c.service_brief or {}
        if brief.get("reminder_consent") in {"granted", "declined"} and not result["consents"]:
            result["consents"].append(
                {
                    "purpose": "reminders",
                    "status": "granted" if brief["reminder_consent"] == "granted" else "withdrawn",
                    "source": brief.get("consent_evidence", ""),
                    "updated_at": c.updated_at,
                }
            )
    handoffs = await session.scalars(
        service.handoffs.select().where(
            PiHandoff.customer_id == customer_id, PiHandoff.status.in_(ACTIVE_HANDOFF)
        )
    )
    result["open_issues"] = [
        {"kind": "handoff", "id": h.id, "summary": h.summary, "status": h.status} for h in handoffs
    ]
    tickets = await session.scalars(
        WorkspaceRepository(session, PiTicket, scope)
        .select()
        .where(
            PiTicket.customer_id == customer_id, PiTicket.status.in_(["open", "pending_customer"])
        )
    )
    result["open_issues"] += [
        {"kind": "ticket", "id": t.id, "summary": t.subject, "status": t.status} for t in tickets
    ]
    requests = await session.scalars(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(PiStaffRequest.customer_id == customer_id, PiStaffRequest.status == "open")
    )
    result["open_issues"] += [
        {"kind": "question", "id": r.id, "summary": r.question[:200], "status": r.status}
        for r in requests
    ]
    bookings = await session.scalars(
        WorkspaceRepository(session, PiBooking, scope)
        .select()
        .where(PiBooking.customer_id == customer_id)
        .order_by(PiBooking.starts_at.desc())
        .limit(20)
    )
    result["bookings"] = [
        {"id": b.id, "starts_at": b.starts_at, "status": b.status, "timezone": b.timezone}
        for b in bookings
    ]
    tasks = await session.scalars(
        WorkspaceRepository(session, PiTask, scope)
        .select()
        .where(PiTask.customer_id == customer_id)
        .order_by(PiTask.created_at.desc())
        .limit(20)
    )
    result["tasks"] = [{"id": t.id, "title": t.title, "status": t.status} for t in tasks]
    return result


@router.get("/customers")
async def visible_customers(
    scope: Scope,
    session: Session,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    """Customers who have talked to Pi, limited to conversations the viewer may see."""
    from app.modules.customers.models import Customer
    from app.shared.workspace_repository import like_pattern

    service = PiService(session, scope)
    await service.require()
    page, page_size = max(1, min(page, 10_000)), max(1, min(page_size, 100))
    latest = (
        service.conversations.select()
        .with_only_columns(
            PiConversation.customer_id,
            func.max(PiConversation.last_message_at).label("last_message_at"),
            func.count().label("conversations"),
        )
        .group_by(PiConversation.customer_id)
        .subquery()
    )
    query = (
        service.customers.select()
        .add_columns(latest.c.last_message_at, latest.c.conversations)
        .join(latest, latest.c.customer_id == Customer.id)
    )
    if search:
        pattern = like_pattern(search[:100])
        query = query.where(Customer.name.ilike(pattern) | Customer.phone.ilike(pattern))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(latest.c.last_message_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone,
                "last_message_at": last,
                "conversations": count,
            }
            for customer, last, count in rows
        ],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=500)


@router.patch("/memory/{memory_id}")
async def correct_memory(
    memory_id: UUID, data: MemoryUpdate, scope: Scope, session: Session
) -> dict[str, Any]:
    """Correct a remembered fact. The correction is attributed to the team member."""
    import hashlib

    service = PiService(session, scope)
    await service.require("pi.memory.read")
    scope.require("pi.inbox.reply")
    memory = await WorkspaceRepository(session, PiMemory, scope).get(memory_id, for_update=True)
    if await service.conversations.find(PiConversation.customer_id == memory.customer_id) is None:
        raise ResourceNotFound
    duplicate = await WorkspaceRepository(session, PiMemory, scope).find(
        PiMemory.customer_id == memory.customer_id,
        PiMemory.content_hash == hashlib.sha256(data.content.encode()).hexdigest(),
        PiMemory.id != memory.id,
    )
    if duplicate is not None:
        raise Conflict("Pi already remembers exactly this")
    memory.content = data.content
    memory.content_hash = hashlib.sha256(data.content.encode()).hexdigest()
    await record(
        session,
        "pi.memory_corrected",
        scope=scope,
        entity_type="pi_memory",
        entity_id=memory.id,
    )
    await session.commit()
    return {"id": memory.id, "content": memory.content}


@router.get("/customers/{customer_id}/export")
async def export_customer(customer_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Controlled export of what Pi holds about one customer (subject access requests).
    Requires the export permission and is audited."""
    service = PiService(session, scope)
    await service.require("pi.customers.export")
    profile = await customer_profile(customer_id, scope, session)
    messages = await session.scalars(
        service.messages.select()
        .where(
            PiMessage.conversation_id.in_(
                service.conversations.select()
                .with_only_columns(PiConversation.id)
                .where(PiConversation.customer_id == customer_id)
            )
        )
        .order_by(PiMessage.created_at)
        .limit(5000)
    )
    profile["messages"] = [
        {
            "at": m.created_at,
            "direction": m.direction,
            "sender": m.sender_type,
            "type": m.message_type,
            "text": m.body,
        }
        for m in messages
    ]
    await record(
        session,
        "pi.customer_exported",
        scope=scope,
        entity_type="customer",
        entity_id=customer_id,
    )
    await session.commit()
    return profile
