"""Send pi to a Zoom, Meet or Teams call (`/api/v1/pi/meeting-intel/bot`) and take its words back.

A person with the record permission pastes the call's link and confirms that everyone in the call
will be told. The provider's bot joins as "pi (AI) - Workzap notetaker", so the call itself shows an
AI is there, and the host can remove it at any moment. From then on the provider calls
`/public/recall/webhook` with what was said and where the bot is. When the call ends the meeting
goes to the same analysis and review as any other, and nothing reaches the Problem Map until a
person approves it.

Off unless the workspace has `brain.meeting_intel` AND `brain.meeting_bot` on AND the provider key
and the public API address are configured. pi does not speak through this bot yet: it listens.

The callback route has no login. Its only control is the provider's signature, checked before the
body is read as JSON; with no secret configured it refuses everything.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi.configuration import settings_row
from app.modules.pi.memory_ledger import redacted
from app.modules.pi_meetings import bot_ingest
from app.modules.pi_meetings.bot_provider import (
    BOT_NAME,
    BotProvider,
    BotProviderError,
    RecallProvider,
    link_hash,
    parse_meeting_link,
    verify_any,
)
from app.modules.pi_meetings.guest_routes import system_scope
from app.modules.pi_meetings.models import BOT_ACTIVE, PiMeeting, PiMeetingBot
from app.modules.pi_meetings.recording_routes import ISO_LANGUAGE
from app.modules.pi_meetings.routes import _customer_ok, _gate, _meeting, _view
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pi/meeting-intel", tags=["pi-meeting-intel"])
public_router = APIRouter(prefix="/public/recall", tags=["public"])

WEBHOOK_PATH = "/api/v1/public/recall/webhook"
MAX_BODY = 2_000_000


class BotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_url: str = Field(min_length=10, max_length=600)
    title: str = Field(default="", max_length=200)
    customer_id: UUID | None = None
    language: str = Field(default="", max_length=12)
    # the person sending pi confirms everyone in the call is told it records and that pi is an AI
    consent: bool = False


def provider_for(request: Request) -> BotProvider | None:
    """The configured provider, or None. Replaced in tests by assigning `app.state.bot_provider`."""
    override = getattr(request.app.state, "bot_provider", None)
    if override is not None:
        return override  # type: ignore[no-any-return]
    settings = request.app.state.settings
    if settings.recall_api_key is None:
        return None
    return RecallProvider(
        request.app.state.http,
        settings.recall_api_key.get_secret_value(),
        settings.recall_region,
    )


def public_base(request: Request) -> str | None:
    """The API's public https address, where the provider's callbacks are sent."""
    return request.app.state.settings.integrations_public_base_url  # type: ignore[no-any-return]


def webhook_secret(request: Request) -> str | None:
    """The secret that signs the provider's callbacks; None when it is not configured."""
    secret = request.app.state.settings.recall_webhook_secret
    return secret.get_secret_value() if secret is not None else None


async def _require_bot(session: Any, scope: WorkspaceScope) -> None:
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    if brain.get("meeting_bot") is not True:
        raise BusinessRuleViolation(
            "MEETING_BOT_OFF", "Sending pi to a call is not switched on for this workspace", 403
        )


def _view_bot(bot: PiMeetingBot) -> dict[str, Any]:
    return {
        "id": str(bot.id),
        "meeting_id": str(bot.meeting_id),
        "status": bot.status,
        "active": bot.status in BOT_ACTIVE,
        "sub_code": bot.sub_code,
        "host": bot.host,
        "bot_name": bot.bot_name,
        "started_at": bot.started_at.isoformat() if bot.started_at else None,
        "ended_at": bot.ended_at.isoformat() if bot.ended_at else None,
    }


async def _latest(session: Any, scope: WorkspaceScope, meeting_id: UUID) -> PiMeetingBot | None:
    return await session.scalar(  # type: ignore[no-any-return]
        select(PiMeetingBot)
        .where(
            PiMeetingBot.tenant_id == scope.tenant_id,
            PiMeetingBot.environment_id == scope.environment_id,
            PiMeetingBot.meeting_id == meeting_id,
        )
        .order_by(PiMeetingBot.created_at.desc())
        .limit(1)
    )


@router.post("/bot", status_code=201)
async def send_bot(
    data: BotInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await _gate(session, scope, "pi.meetings.record")
    await _require_bot(session, scope)
    provider = provider_for(request)
    base = public_base(request)
    if provider is None or not base:
        raise BusinessRuleViolation(
            "MEETING_BOT_UNCONFIGURED", "The meeting bot service is not set up yet", 503
        )
    if not data.consent:
        raise BusinessRuleViolation(
            "MEETING_CONSENT_REQUIRED",
            "Confirm that everyone in the call will be told pi is an AI notetaker and records it",
            422,
        )
    link = parse_meeting_link(data.meeting_url)
    if link is None:
        raise BusinessRuleViolation(
            "MEETING_LINK_INVALID", "Paste a Zoom, Google Meet or Teams meeting link", 422
        )
    if data.customer_id is not None:
        await _customer_ok(session, scope, data.customer_id)
    url_key = link_hash(data.meeting_url)
    busy = await session.scalar(
        select(PiMeetingBot.id)
        .where(
            PiMeetingBot.tenant_id == scope.tenant_id,
            PiMeetingBot.environment_id == scope.environment_id,
            PiMeetingBot.url_hash == url_key,
            PiMeetingBot.status.in_(BOT_ACTIVE),
        )
        .limit(1)
    )
    if busy is not None:
        raise BusinessRuleViolation(
            "MEETING_BOT_ALREADY_IN", "pi is already in, or on its way to, this call", 409
        )
    language = data.language.strip().lower()
    if language and not ISO_LANGUAGE.match(language):
        raise BusinessRuleViolation("MEETING_LANGUAGE_INVALID", "Use a language code like en", 422)
    now = datetime.now(UTC)
    meeting = PiMeeting(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=data.customer_id,
        title=redacted(data.title, 200),
        source=link.source,
        language=language,
        consent_at=now,
        consent_by=scope.user_id,
        consent_note="Host confirmed the call is told pi is an AI notetaker (meeting bot)",
        held_at=now,
        created_by=scope.user_id,
    )
    session.add(meeting)
    await session.flush()
    bot = PiMeetingBot(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting.id,
        provider=provider.name,
        status="requested",
        url_hash=url_key,
        host=link.host,
        bot_name=BOT_NAME,
        created_by=scope.user_id,
    )
    session.add(bot)
    await session.flush()
    try:
        bot.external_id = await provider.join(
            meeting_url=data.meeting_url.strip(),
            bot_name=BOT_NAME,
            webhook_url=f"{base.rstrip('/')}{WEBHOOK_PATH}",
            language=language,
        )
    except BotProviderError as error:
        bot.status = "failed"
        bot.sub_code = error.code.lower()[:80]
        meeting.status = "failed"
        meeting.failure_reason = error.message
        await record(
            session,
            "pi.meeting_bot_failed",
            scope=scope,
            entity_type="pi_meeting",
            entity_id=meeting.id,
            details={"code": error.code, "source": link.source},
        )
        await session.commit()
        raise BusinessRuleViolation(error.code, error.message, error.status) from None
    await record(
        session,
        "pi.meeting_bot_requested",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"source": link.source, "host": link.host, "provider": provider.name},
    )
    await session.commit()
    return {"meeting": _view(meeting), "bot": _view_bot(bot)}


@router.get("/{meeting_id}/bot")
async def bot_status(
    meeting_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Where pi is in this call. While the bot is still active it also asks the provider, so the
    page is right even if the provider's status callbacks are not set up."""
    await _gate(session, scope, "pi.meetings.read")
    meeting = await _meeting(session, scope, meeting_id)
    bot = await _latest(session, scope, meeting.id)
    if bot is None:
        return {"bot": None}
    provider = provider_for(request)
    if bot.status in BOT_ACTIVE and bot.external_id and provider is not None:
        try:
            latest = await provider.status(bot.external_id)
        except BotProviderError:
            latest = None  # show what we have; the page keeps polling
        if latest is not None and await bot_ingest.apply_status(
            session, bot, meeting, latest[0], latest[1]
        ):
            await session.commit()
    return {"bot": _view_bot(bot), "meeting_status": meeting.status}


@router.post("/{meeting_id}/bot/leave")
async def bot_leave(
    meeting_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Take pi out of the call now. Leaving cannot be undone: a new bot is sent for a new visit."""
    await _gate(session, scope, "pi.meetings.record")
    meeting = await _meeting(session, scope, meeting_id)
    bot = await _latest(session, scope, meeting.id)
    if bot is None or bot.status not in BOT_ACTIVE or not bot.external_id:
        raise BusinessRuleViolation("MEETING_BOT_NOT_ACTIVE", "pi is not in this call", 409)
    provider = provider_for(request)
    if provider is None:
        raise BusinessRuleViolation(
            "MEETING_BOT_UNCONFIGURED", "The meeting bot service is not set up yet", 503
        )
    try:
        await provider.leave(bot.external_id)
    except BotProviderError as error:
        raise BusinessRuleViolation(error.code, error.message, error.status) from None
    await bot_ingest.apply_status(session, bot, meeting, "call_ended")
    await record(
        session,
        "pi.meeting_bot_left",
        scope=scope,
        entity_type="pi_meeting",
        entity_id=meeting.id,
        details={"provider": bot.provider},
    )
    await session.commit()
    return {"bot": _view_bot(bot)}


@public_router.post("/webhook")
async def webhook(request: Request, session: Session) -> dict[str, bool]:
    """The provider's callbacks. Checked by signature before anything is read from the body."""
    secret = webhook_secret(request)
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_BODY:
        raise BusinessRuleViolation("RECALL_BODY_TOO_LARGE", "Too large", 413)
    body = await request.body()
    if secret is None or len(body) > MAX_BODY:
        raise BusinessRuleViolation("RECALL_NOT_CONFIGURED", "Not available", 503)
    if not verify_any(secret, dict(request.headers), body):
        raise BusinessRuleViolation("RECALL_SIGNATURE_INVALID", "Invalid signature", 401)
    try:
        payload = json.loads(body)
    except ValueError:
        return {"ok": True}  # signed but not ours to understand: do not make the provider retry
    event = payload.get("event") if isinstance(payload, dict) else None
    outer = payload.get("data") if isinstance(payload, dict) else None
    bot_ref = outer.get("bot") if isinstance(outer, dict) else None
    external = bot_ref.get("id") if isinstance(bot_ref, dict) else None
    if not isinstance(event, str) or not isinstance(external, str) or not isinstance(outer, dict):
        return {"ok": True}
    bot = await session.scalar(
        select(PiMeetingBot).where(
            PiMeetingBot.provider == "recall", PiMeetingBot.external_id == external
        )
    )
    if bot is None:
        return {"ok": True}  # not a bot of ours (another environment, or already erased)
    scope = system_scope(bot.tenant_id, bot.environment_id)
    brain = (await settings_row(session, scope)).response_rules.get("brain") or {}
    if brain.get("meeting_bot") is not True:
        return {"ok": True}
    meeting = await session.scalar(
        select(PiMeeting).where(
            PiMeeting.tenant_id == bot.tenant_id,
            PiMeeting.environment_id == bot.environment_id,
            PiMeeting.id == bot.meeting_id,
        )
    )
    if meeting is None:
        return {"ok": True}
    raw_inner = outer.get("data")
    inner: dict[str, Any] = raw_inner if isinstance(raw_inner, dict) else {}
    if event == "transcript.data":
        await bot_ingest.add_words(session, scope, meeting, inner)
    elif event.startswith("bot."):
        await bot_ingest.apply_status(
            session, bot, meeting, event, str(inner.get("sub_code") or "")
        )
    await session.commit()
    return {"ok": True}
