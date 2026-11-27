"""Meeting agents and Ask AI chats.

`GET/POST /pi/meeting-agents` list and write the workspace's own agents (writing needs
`pi.meetings.approve`: an agent changes how pi sounds to customers), `PUT .../agent` picks the agent
of one meeting, and `/pi/meeting-intel/{id}/chats` keep the "Ask AI" conversations of a meeting.
The answer to each question is still `qa.ask`: it reads only this meeting's lines and shows the
lines it used; an agent adds its focus and tone below those rules. Audit entries carry ids and
counts, never the question, the answer or the agent's instructions.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.ai.manager import build_llm_manager
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import agents, qa, qa_routes
from app.modules.pi_meetings.agent_store import custom_row, resolve, valid_key
from app.modules.pi_meetings.models import (
    PiMeetingAgent,
    PiMeetingChat,
    PiMeetingChatMessage,
)
from app.modules.pi_meetings.routes import _gate, _meeting
from app.modules.tenants.errors import ResourceNotFound
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/pi", tags=["pi-meeting-agents"])

MAX_CHATS = 30  # per meeting
MAX_MESSAGES = 100  # per chat
TITLE_CHARS = 60
LIST_CHATS = 50


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=agents.NAME_MIN, max_length=agents.NAME_MAX)
    tagline: str = Field(default="", max_length=agents.TAGLINE_MAX)
    icon: str = "sparkles"
    color: str = "green"
    instructions: str = Field(max_length=agents.INSTRUCTIONS_MAX + 500)


class AgentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=agents.NAME_MIN, max_length=agents.NAME_MAX)
    tagline: str | None = Field(default=None, max_length=agents.TAGLINE_MAX)
    icon: str | None = None
    color: str | None = None
    instructions: str | None = Field(default=None, max_length=agents.INSTRUCTIONS_MAX + 500)


class CheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str = Field(max_length=agents.INSTRUCTIONS_MAX + 500)


class MeetingAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_key: str = Field(min_length=1, max_length=40)


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_key: str | None = Field(default=None, max_length=40)


class ChatPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=agents.NAME_MAX * 2)
    agent_key: str | None = Field(default=None, max_length=40)


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=qa_routes.MAX_QUESTION_CHARS)


# -- agents -------------------------------------------------------------------------------------


def _fields(data: AgentInput | AgentPatch) -> list[str]:
    """Why the values cannot be saved (empty: they can)."""
    problems: list[str] = []
    if data.icon is not None and data.icon not in agents.ICONS:
        problems.append("Pick one of the icons.")
    if data.color is not None and data.color not in agents.COLORS:
        problems.append("Pick one of the colours.")
    if data.instructions is not None:
        problems += agents.check_instructions(data.instructions)
    return problems


def _refuse(reasons: list[str]) -> BusinessRuleViolation:
    return BusinessRuleViolation("AGENT_INSTRUCTIONS_REFUSED", " ".join(reasons), 422)


@router.get("/meeting-agents")
async def list_agents(scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    rows = (
        await session.scalars(
            select(PiMeetingAgent)
            .where(
                PiMeetingAgent.tenant_id == scope.tenant_id,
                PiMeetingAgent.environment_id == scope.environment_id,
                PiMeetingAgent.archived_at.is_(None),
            )
            .order_by(PiMeetingAgent.created_at.desc())
        )
    ).all()
    can = scope.can("pi.meetings.approve")
    return {
        "agents": [
            *(agents.view(preset=p) for p in agents.PRESETS),
            *(agents.view(row=r, can_edit=can) for r in rows),
        ]
    }


@router.post("/meeting-agents/check")
async def check_agent(data: CheckInput, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    reasons = agents.check_instructions(data.instructions)
    return {"ok": not reasons, "reasons": reasons}


@router.post("/meeting-agents", status_code=201)
async def create_agent(data: AgentInput, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    problems = _fields(data)
    if problems:
        raise _refuse(problems)
    count = await session.scalar(
        select(func.count())
        .select_from(PiMeetingAgent)
        .where(
            PiMeetingAgent.tenant_id == scope.tenant_id,
            PiMeetingAgent.environment_id == scope.environment_id,
            PiMeetingAgent.archived_at.is_(None),
        )
    )
    if (count or 0) >= agents.MAX_CUSTOM:
        raise BusinessRuleViolation(
            "AGENT_LIMIT",
            f"A workspace can keep {agents.MAX_CUSTOM} agents; archive one first",
            422,
        )
    row = PiMeetingAgent(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        name=redacted(data.name.strip(), agents.NAME_MAX),
        tagline=redacted(data.tagline.strip(), agents.TAGLINE_MAX),
        icon=data.icon,
        color=data.color,
        instructions=agents.clean_instructions(data.instructions),
        created_by=scope.user_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise BusinessRuleViolation(
            "AGENT_NAME_TAKEN", "An agent with this name already exists", 409
        ) from None
    await record(
        session,
        "pi.meeting_agent_created",
        scope=scope,
        entity_type="pi_meeting_agent",
        entity_id=row.id,
        details={"instruction_chars": len(row.instructions)},
    )
    await session.commit()
    await session.refresh(row)
    return agents.view(row=row, can_edit=True)


@router.patch("/meeting-agents/{key}")
async def update_agent(
    key: str, data: AgentPatch, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.approve")
    row = await custom_row(session, scope, key)
    if row is None:
        raise ResourceNotFound
    problems = _fields(data)
    if problems:
        raise _refuse(problems)
    if data.name is not None:
        row.name = redacted(data.name.strip(), agents.NAME_MAX)
    if data.tagline is not None:
        row.tagline = redacted(data.tagline.strip(), agents.TAGLINE_MAX)
    if data.icon is not None:
        row.icon = data.icon
    if data.color is not None:
        row.color = data.color
    if data.instructions is not None:
        row.instructions = agents.clean_instructions(data.instructions)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise BusinessRuleViolation(
            "AGENT_NAME_TAKEN", "An agent with this name already exists", 409
        ) from None
    await record(
        session,
        "pi.meeting_agent_updated",
        scope=scope,
        entity_type="pi_meeting_agent",
        entity_id=row.id,
        details={"instruction_chars": len(row.instructions)},
    )
    await session.commit()
    await session.refresh(row)
    return agents.view(row=row, can_edit=True)


@router.delete("/meeting-agents/{key}", status_code=204)
async def archive_agent(key: str, scope: Scope, session: Session) -> None:
    await _gate(session, scope, "pi.meetings.approve")
    row = await custom_row(session, scope, key)
    if row is None:
        raise ResourceNotFound
    row.archived_at = datetime.now(UTC)
    await record(
        session,
        "pi.meeting_agent_archived",
        scope=scope,
        entity_type="pi_meeting_agent",
        entity_id=row.id,
    )
    await session.commit()


# -- a meeting's agent --------------------------------------------------------------------------


@router.put("/meeting-intel/{meeting_id}/agent")
async def set_meeting_agent(
    meeting_id: UUID, data: MeetingAgentInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    key = await valid_key(session, scope, data.agent_key)
    meeting.agent_key = None if key == agents.DEFAULT_KEY else key
    await record(
        session,
        "pi.meeting_agent_set",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"builtin": key in agents.BY_KEY},
    )
    await session.commit()
    return {"agent_key": meeting.agent_key}


# -- chats --------------------------------------------------------------------------------------


def _chat_view(chat: PiMeetingChat, count: int = 0, last: str = "") -> dict[str, Any]:
    return {
        "id": str(chat.id),
        "title": chat.title,
        "agent_key": chat.agent_key,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
        "message_count": count,
        "last_text": last[:120],
    }


def _preview(m: PiMeetingChatMessage) -> str:
    """One line for the chat list: the last message, or that the answer was not in the meeting."""
    if m.role == "assistant" and not m.found:
        return "This was not said in the meeting"
    return m.text


def _message_view(m: PiMeetingChatMessage) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "role": m.role,
        "text": m.text,
        "found": m.found,
        "partial": m.partial,
        "sources": m.sources or [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _chat(
    session: Any, scope: WorkspaceScope, meeting_id: UUID, chat_id: UUID
) -> PiMeetingChat:
    chat: PiMeetingChat | None = await session.scalar(
        select(PiMeetingChat).where(
            PiMeetingChat.tenant_id == scope.tenant_id,
            PiMeetingChat.environment_id == scope.environment_id,
            PiMeetingChat.meeting_id == meeting_id,
            PiMeetingChat.id == chat_id,
        )
    )
    if chat is None:
        raise ResourceNotFound
    return chat


@router.get("/meeting-intel/{meeting_id}/chats")
async def list_chats(meeting_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    where = (
        PiMeetingChat.tenant_id == scope.tenant_id,
        PiMeetingChat.environment_id == scope.environment_id,
        PiMeetingChat.meeting_id == meeting.id,
    )
    chats = (
        await session.scalars(
            select(PiMeetingChat)
            .where(*where)
            .order_by(PiMeetingChat.updated_at.desc())
            .limit(LIST_CHATS)
        )
    ).all()
    ids = [c.id for c in chats]
    counts: dict[UUID, int] = {}
    last: dict[UUID, str] = {}
    if ids:
        base = (
            PiMeetingChatMessage.tenant_id == scope.tenant_id,
            PiMeetingChatMessage.environment_id == scope.environment_id,
            PiMeetingChatMessage.chat_id.in_(ids),
        )
        counts = dict(
            (
                await session.execute(
                    select(PiMeetingChatMessage.chat_id, func.count())
                    .where(*base)
                    .group_by(PiMeetingChatMessage.chat_id)
                )
            ).all()
        )
        newest = await session.scalars(
            select(PiMeetingChatMessage)
            .where(*base)
            .distinct(PiMeetingChatMessage.chat_id)
            .order_by(PiMeetingChatMessage.chat_id, PiMeetingChatMessage.created_at.desc())
        )
        last = {m.chat_id: _preview(m) for m in newest}
    return {"chats": [_chat_view(c, counts.get(c.id, 0), last.get(c.id, "")) for c in chats]}


@router.post("/meeting-intel/{meeting_id}/chats", status_code=201)
async def create_chat(
    meeting_id: UUID, data: ChatInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    count = await session.scalar(
        select(func.count())
        .select_from(PiMeetingChat)
        .where(
            PiMeetingChat.tenant_id == scope.tenant_id,
            PiMeetingChat.environment_id == scope.environment_id,
            PiMeetingChat.meeting_id == meeting.id,
        )
    )
    if (count or 0) >= MAX_CHATS:
        raise BusinessRuleViolation(
            "CHAT_LIMIT", f"A meeting can keep {MAX_CHATS} chats; delete one first", 422
        )
    key = await valid_key(session, scope, data.agent_key or meeting.agent_key or agents.DEFAULT_KEY)
    chat = PiMeetingChat(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        agent_key=key,
        title="",
        created_by=scope.user_id,
    )
    session.add(chat)
    await session.flush()
    await session.commit()
    await session.refresh(chat)
    return _chat_view(chat)


@router.get("/meeting-intel/{meeting_id}/chats/{chat_id}")
async def get_chat(
    meeting_id: UUID, chat_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    chat = await _chat(session, scope, meeting.id, chat_id)
    messages = (
        await session.scalars(
            select(PiMeetingChatMessage)
            .where(
                PiMeetingChatMessage.tenant_id == scope.tenant_id,
                PiMeetingChatMessage.environment_id == scope.environment_id,
                PiMeetingChatMessage.chat_id == chat.id,
            )
            .order_by(PiMeetingChatMessage.created_at, PiMeetingChatMessage.id)
        )
    ).all()
    return {
        "chat": _chat_view(chat, len(messages), _preview(messages[-1]) if messages else ""),
        "messages": [_message_view(m) for m in messages],
    }


@router.post("/meeting-intel/{meeting_id}/chats/{chat_id}/messages")
async def send_message(
    meeting_id: UUID,
    chat_id: UUID,
    data: MessageInput,
    scope: Scope,
    session: Session,
    request: Request,
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    chat = await _chat(session, scope, meeting.id, chat_id)
    made = await session.scalar(
        select(func.count())
        .select_from(PiMeetingChatMessage)
        .where(
            PiMeetingChatMessage.tenant_id == scope.tenant_id,
            PiMeetingChatMessage.environment_id == scope.environment_id,
            PiMeetingChatMessage.chat_id == chat.id,
        )
    )
    if (made or 0) >= MAX_MESSAGES:
        raise BusinessRuleViolation(
            "CHAT_FULL", "This chat is full: start a new chat to keep asking", 422
        )
    asked_at = datetime.now(UTC)  # the question is older than its answer
    question = " ".join(data.question.split())
    lines, part, partial = await qa_routes.transcript_part(session, scope, meeting.id, question)
    _, _, persona = await resolve(session, scope, chat.agent_key)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    try:
        answer = await qa.ask(
            manager,
            scope,
            question,
            part,
            partial=partial,
            language=meeting.language,
            persona=persona,
        )
    except qa.AskFailed:
        raise BusinessRuleViolation(
            "MEETING_ASK_UNAVAILABLE", "The answer could not be written; try again", 502
        ) from None
    shown = qa_routes.answer_view(answer)
    user_row = PiMeetingChatMessage(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        chat_id=chat.id,
        role="user",
        text=redacted(question, qa_routes.MAX_QUESTION_CHARS),
        created_at=asked_at,
    )
    reply_row = PiMeetingChatMessage(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        chat_id=chat.id,
        role="assistant",
        text=shown["answer"],
        found=shown["found"],
        partial=shown["partial"],
        sources=shown["sources"],
        # never the same instant as the question (a coarse clock): the order must be certain
        created_at=max(datetime.now(UTC), asked_at + timedelta(milliseconds=1)),
    )
    session.add_all([user_row, reply_row])
    if not chat.title:
        chat.title = redacted(question, TITLE_CHARS)
    chat.updated_at = datetime.now(UTC)
    await record(
        session,
        "pi.meeting_asked",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={
            "found": answer.found,
            "lines_read": len(part),
            "lines_total": len(lines),
            "question_chars": len(question),
            "chat": str(chat.id),
            "agent": chat.agent_key if chat.agent_key in agents.BY_KEY else "custom",
        },
    )
    await session.commit()
    await session.refresh(user_row)
    await session.refresh(reply_row)
    return {"user": _message_view(user_row), "assistant": _message_view(reply_row)}


@router.patch("/meeting-intel/{meeting_id}/chats/{chat_id}")
async def update_chat(
    meeting_id: UUID, chat_id: UUID, data: ChatPatch, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    chat = await _chat(session, scope, meeting.id, chat_id)
    if data.title is not None:
        chat.title = redacted(" ".join(data.title.split()), TITLE_CHARS)
    if data.agent_key is not None:
        chat.agent_key = await valid_key(session, scope, data.agent_key)
    chat.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(chat)
    return _chat_view(chat)


@router.delete("/meeting-intel/{meeting_id}/chats/{chat_id}", status_code=204)
async def delete_chat(meeting_id: UUID, chat_id: UUID, scope: Scope, session: Session) -> None:
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    chat = await _chat(session, scope, meeting.id, chat_id)
    await session.execute(
        delete(PiMeetingChatMessage).where(
            PiMeetingChatMessage.tenant_id == scope.tenant_id,
            PiMeetingChatMessage.environment_id == scope.environment_id,
            PiMeetingChatMessage.chat_id == chat.id,
        )
    )
    await session.delete(chat)
    await session.commit()
