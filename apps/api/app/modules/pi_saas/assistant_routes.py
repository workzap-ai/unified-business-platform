"""pi Assistant API: chat for business teams (pi-app) and help-guide management (operator)."""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.ai.manager import build_llm_manager
from app.core.rate_limit import hit
from app.modules.access.dependencies import Scope, Session
from app.modules.audit.service import record
from app.modules.pi_saas import help_kb
from app.modules.pi_saas.assistant import ChatInput, chat
from app.modules.pi_saas.operator import Operator
from app.shared.errors import BusinessRuleViolation, PermissionDenied

logger = logging.getLogger("platform")

router = APIRouter(prefix="/assistant", tags=["pi-assistant"])
operator_router = APIRouter(prefix="/operator/pi/help", tags=["pi-operator-help"])


def ai_enabled(request: Request) -> bool:
    settings = request.app.state.settings
    return any(getattr(settings, f"{p}_api_key", None) for p in settings.provider_order())


@router.get("/context")
async def context(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """What this member can ask about (drives the starter prompts)."""
    can = scope.can
    return {
        "ai_enabled": ai_enabled(request),
        "can": {
            "overview": can("pi.read"),
            "conversations": can("pi.read"),
            "all_conversations": can("pi.inbox.all"),
            "reports": can("pi.analytics.read"),
            "work": can("pi.bookings.read") or can("pi.work.read"),
            "campaigns": can("pi.campaigns.read"),
            "billing": can("pi.billing.read"),
            "leads": can("sales.read"),
        },
        "guides": [
            {"id": a.id, "title": a.title, "page": a.page} for a in await help_kb.articles(session)
        ],
    }


async def _limit(request: Request, scope: Any) -> None:
    if not await hit(request, "pi-assistant", f"{scope.tenant_id}:{scope.user_id}", 30, 60):
        raise BusinessRuleViolation("RATE_LIMITED", "Please wait a moment before continuing.", 429)


async def _audit_answer(session: Any, scope: Any, result: dict[str, Any]) -> None:
    await record(
        session,
        "pi.assistant_asked",
        scope=scope,
        entity_type="pi_assistant",
        details={"mode": result["mode"], "cards": [c["title"] for c in result["cards"]]},
    )


@router.post("/chat")
async def ask(data: ChatInput, request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await _limit(request, scope)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    try:
        async with asyncio.timeout(90):
            result = await chat(session, scope, request, manager, data, ai_enabled(request))
    except TimeoutError:
        raise BusinessRuleViolation(
            "ASSISTANT_TIMEOUT", "That took too long. Please try a narrower question.", 503
        ) from None
    await _audit_answer(session, scope, result)
    await session.commit()
    return result


@router.post("/chat/stream")
async def ask_stream(
    data: ChatInput, request: Request, scope: Scope, session: Session
) -> StreamingResponse:
    """The same agent, streamed as NDJSON: each real step as it happens, then the reply.

    Events: {"type": "thinking"}, {"type": "step", "tool", "label"},
    {"type": "step_done", "tool", "ok"}, then {"type": "reply", "reply": {...}} or
    {"type": "error", "message"}. The request's database session stays open until the
    response has been sent (FastAPI's default request scope), so the agent can use it
    while streaming.
    """
    await _limit(request, scope)
    state = request.app.state
    manager = build_llm_manager(state.settings, state.http, state.sessions)
    enabled = ai_enabled(request)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def work() -> None:
        try:
            async with asyncio.timeout(90):
                result = await chat(session, scope, request, manager, data, enabled, emit)
            await _audit_answer(session, scope, result)
            await session.commit()
            await queue.put({"type": "reply", "reply": result})
        except TimeoutError:
            await queue.put(
                {
                    "type": "error",
                    "message": "That took too long. Please try a narrower question.",
                }
            )
        except Exception:  # the stream must always end with a clear message
            logger.exception("pi assistant stream failed")
            await queue.put(
                {
                    "type": "error",
                    "message": "Something went wrong on our side. Please try again.",
                }
            )
        finally:
            await queue.put(None)

    async def stream() -> Any:
        task = asyncio.create_task(work())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event, default=str) + "\n"
        finally:
            if not task.done():  # the person closed the panel or stopped the answer
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/guides/{guide_id}")
async def guide(guide_id: str, scope: Scope, session: Session) -> dict[str, Any]:
    for article in await help_kb.articles(session):
        if article.id == guide_id:
            return help_kb.view(article)
    raise BusinessRuleViolation("NOT_FOUND", "Guide not found", 404)


# -- operator: manage the guides every business sees ----------------------------------------


def _can_edit(operator: Any) -> None:
    if not (operator.can("operator.onboarding.assist") or operator.can("operator.settings.manage")):
        raise PermissionDenied


@operator_router.get("")
async def list_guides(operator: Operator, session: Session) -> dict[str, Any]:
    _can_edit(operator)
    return {
        "pages": list(help_kb.PI_PAGES),
        "items": [help_kb.view(a) for a in await help_kb.articles(session, include_hidden=True)],
    }


async def _audit(session: Any, operator: Any, action: str, guide_id: str) -> None:
    await record(
        session,
        f"pi_operator.help_{action}",
        tenant_id=None,
        actor_user_id=operator.user_id,
        entity_type="pi_help_guide",
        details={"guide": guide_id},
        include_environment=False,
    )


@operator_router.post("", status_code=201)
async def create_guide(
    data: help_kb.ArticleInput, operator: Operator, session: Session
) -> dict[str, Any]:
    _can_edit(operator)
    article = await help_kb.save(session, None, data, operator.label)
    await _audit(session, operator, "created", article.id)
    await session.commit()
    return help_kb.view(article)


@operator_router.put("/{guide_id}")
async def update_guide(
    guide_id: str, data: help_kb.ArticleInput, operator: Operator, session: Session
) -> dict[str, Any]:
    _can_edit(operator)
    article = await help_kb.save(session, guide_id, data, operator.label)
    await _audit(session, operator, "updated", guide_id)
    await session.commit()
    return help_kb.view(article)


@operator_router.post("/{guide_id}/hide")
async def hide_guide(guide_id: str, operator: Operator, session: Session) -> dict[str, Any]:
    _can_edit(operator)
    await help_kb.set_hidden(session, guide_id, True)
    await _audit(session, operator, "hidden", guide_id)
    await session.commit()
    return {"id": guide_id, "hidden": True}


@operator_router.post("/{guide_id}/show")
async def show_guide(guide_id: str, operator: Operator, session: Session) -> dict[str, Any]:
    _can_edit(operator)
    await help_kb.set_hidden(session, guide_id, False)
    await _audit(session, operator, "shown", guide_id)
    await session.commit()
    return {"id": guide_id, "hidden": False}


@operator_router.delete("/{guide_id}")
async def reset_guide(guide_id: str, operator: Operator, session: Session) -> dict[str, Any]:
    """Built-in guide: back to the shipped text. Operator guide: deleted."""
    _can_edit(operator)
    await help_kb.reset(session, guide_id)
    await _audit(session, operator, "reset", guide_id)
    await session.commit()
    return {"id": guide_id, "reset": True}
