"""The blocklist's HTTP face, mounted for Owner OS and the pi app. Reading needs ``pi.read``;
blocking, unblocking and editing need ``pi.settings.manage``."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.models import PiConversation, PiMessage
from app.modules.pi.service import PiService, require_pi
from app.modules.pi_saas.blocklist import service
from app.modules.pi_saas.blocklist.models import PiBlockedContact
from app.modules.pi_saas.nori_credits.resilience import digits
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi/blocklist", tags=["pi-blocklist"])

SUGGEST_PREFIX = 9  # digits of country code and operator range
SUGGEST_MIN = 3  # numbers from one range that only ever sent media


@router.get("")
async def get_blocklist(scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.read")
    rows = await service.list_rows(session, scope)
    await session.commit()
    return {
        "items": [service.view(r) for r in rows],
        "active": sum(1 for r in rows if r.active),
        "blocked_messages": sum(r.hits for r in rows),
    }


@router.get("/suggestions")
async def suggestions(scope: Scope, session: Session) -> dict[str, Any]:
    """Ranges whose open chats only ever sent media (no text) and are not blocked yet: the
    mark of a bulk-created flood."""
    await require_pi(session, scope, "pi.read")
    chats = WorkspaceRepository(session, PiConversation, scope)
    has_text = (
        select(PiMessage.id)
        .where(
            PiMessage.conversation_id == PiConversation.id,
            PiMessage.direction == "inbound",
            PiMessage.message_type == "text",
        )
        .exists()
    )
    prefix = func.left(PiConversation.contact_wa_id, SUGGEST_PREFIX)
    rows = (
        await session.execute(
            select(
                prefix,
                func.count(),
                func.min(PiConversation.created_at),
                func.max(PiConversation.created_at),
            )
            .select_from(PiConversation)
            .where(
                chats.predicate(),
                PiConversation.status == "open",
                PiConversation.channel == "whatsapp",
                ~has_text,
            )
            .group_by(prefix)
            .having(func.count() >= SUGGEST_MIN)
            .order_by(func.count().desc())
            .limit(30)
        )
    ).all()
    blocked = {r.value for r in await service.list_rows(session, scope) if r.active}
    await session.commit()
    return {
        "ranges": [
            {"prefix": p, "chats": n, "first_seen": first, "last_seen": last}
            for p, n, first, last in rows
            if p not in blocked
        ]
    }


class NewBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    value: str = Field(min_length=1, max_length=40)
    kind: Literal["number", "prefix"] = "number"
    reason: str = Field("", max_length=200)
    note: str = Field("", max_length=500)
    close_chats: bool = True


@router.post("", status_code=201)
async def add_block(data: NewBlock, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    row, _ = await service.block(
        session, scope, value=data.value, kind=data.kind, reason=data.reason, note=data.note
    )
    closed = await service.close_chats(session, scope, row) if data.close_chats else 0
    await record(
        session,
        "pi.number_blocked",
        scope=scope,
        entity_type="pi_blocked_contact",
        entity_id=row.id,
        details={"kind": row.kind, "reason": row.reason, "closed_chats": closed},
    )
    await session.commit()
    return {**service.view(row), "closed_chats": closed}


class BulkBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    values: list[str] = Field(min_length=1, max_length=service.MAX_BULK)
    reason: str = Field("", max_length=200)
    note: str = Field("", max_length=500)
    close_chats: bool = True


@router.post("/bulk")
async def add_bulk(data: BulkBlock, scope: Scope, session: Session) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    result = await service.block_many(
        session, scope, data.values, reason=data.reason, note=data.note
    )
    closed = 0
    if data.close_chats:
        repo = WorkspaceRepository(session, PiBlockedContact, scope)
        for raw in dict.fromkeys(digits(v) for v in data.values):
            row = await repo.find(PiBlockedContact.value == raw)
            if row is not None:
                closed += await service.close_chats(session, scope, row)
    await record(
        session,
        "pi.numbers_blocked",
        scope=scope,
        entity_type="pi_blocked_contact",
        entity_id=None,
        details={"added": result["added"], "reason": data.reason, "closed_chats": closed},
    )
    await session.commit()
    return {**result, "closed_chats": closed}


class ChatBlock(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field("", max_length=200)
    note: str = Field("", max_length=500)


@router.post("/from-conversation/{conversation_id}", status_code=201)
async def block_from_chat(
    conversation_id: UUID, data: ChatBlock, scope: Scope, session: Session
) -> dict[str, Any]:
    """Block the number of an inbox chat and close the chat."""
    service_pi = PiService(session, scope)
    await service_pi.require("pi.settings.manage")
    chat = await service_pi.conversations.get(conversation_id, for_update=True)
    row, _ = await service.block(
        session,
        scope,
        value=chat.contact_wa_id,
        reason=data.reason or "Blocked from the inbox",
        note=data.note,
        source="chat",
    )
    closed = await service.close_chats(session, scope, row)
    await record(
        session,
        "pi.number_blocked",
        scope=scope,
        entity_type="pi_blocked_contact",
        entity_id=row.id,
        details={"kind": "number", "from": "inbox", "closed_chats": closed},
    )
    await session.commit()
    return {**service.view(row), "closed_chats": closed}


class BlockChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str | None = Field(None, max_length=200)
    note: str | None = Field(None, max_length=500)
    active: bool | None = None


@router.patch("/{block_id}")
async def change_block(
    block_id: UUID, data: BlockChange, scope: Scope, session: Session
) -> dict[str, Any]:
    await require_pi(session, scope, "pi.settings.manage")
    values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    row = await service.change(session, scope, block_id, values)
    await record(
        session,
        "pi.block_updated",
        scope=scope,
        entity_type="pi_blocked_contact",
        entity_id=row.id,
        details={"active": row.active},
    )
    await session.commit()
    return service.view(row)


@router.delete("/{block_id}")
async def unblock(block_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    """Unblock: the number is answered again. The row stays, switched off, as a record."""
    await require_pi(session, scope, "pi.settings.manage")
    row = await service.unblock(session, scope, block_id)
    await record(
        session,
        "pi.number_unblocked",
        scope=scope,
        entity_type="pi_blocked_contact",
        entity_id=row.id,
    )
    await session.commit()
    return service.view(row)
