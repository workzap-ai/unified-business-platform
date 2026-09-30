import asyncio
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.ai.manager import LLMManager
from app.core.rate_limit import hit
from app.modules.access.dependencies import Scope, Session
from app.modules.workspace_agent.assistant import WorkspaceUsageStore, chat
from app.modules.workspace_agent.documents import MAX_BYTES, extract, process
from app.modules.workspace_agent.insights import Insights
from app.modules.workspace_agent.schemas import ChatInput, Decision, ProposalInput, ReadInput
from app.modules.workspace_agent.service import AgentService
from app.shared.errors import BusinessRuleViolation


async def bound_workspace(request: Request, scope: Scope) -> None:
    # Required even for read requests: a stale browser must not reinterpret the conversation
    # in another workspace after a server-side session switch.
    if request.headers.get("x-workspace-tenant") != str(scope.tenant_id) or request.headers.get(
        "x-workspace-environment"
    ) != str(scope.environment_id):
        raise BusinessRuleViolation(
            "WORKSPACE_CHANGED", "Refresh the workspace before using Agent Beta.", 409
        )


router = APIRouter(
    prefix="/workspace-agent", tags=["workspace-agent"], dependencies=[Depends(bound_workspace)]
)


def manager(request: Request) -> LLMManager:
    return LLMManager(
        request.app.state.settings,
        request.app.state.http,
        usage=WorkspaceUsageStore(request.app.state.sessions),
    )


def ai_enabled(request: Request) -> bool:
    settings = request.app.state.settings
    return any(getattr(settings, f"{p}_api_key", None) for p in settings.provider_order())


async def limited(request: Request, scope: Scope) -> None:
    if not await hit(request, "workspace-agent", f"{scope.tenant_id}:{scope.user_id}", 30, 60):
        raise BusinessRuleViolation("RATE_LIMITED", "Please wait a moment before continuing.", 429)


@router.get("/context")
async def context(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    return {**await AgentService(session, scope).identity(), "ai_enabled": ai_enabled(request)}


@router.post("/chat")
async def ask(data: ChatInput, request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await limited(request, scope)
    try:
        async with asyncio.timeout(100):
            result = await chat(
                AgentService(session, scope), manager(request), data, ai_enabled(request)
            )
    except TimeoutError:
        raise BusinessRuleViolation(
            "AGENT_TIMEOUT", "This request took too long. Please try a smaller request.", 503
        ) from None
    await session.commit()
    return result


@router.post("/read")
async def read(data: ReadInput, scope: Scope, session: Session) -> dict[str, Any]:
    return await AgentService(session, scope).read(data)


@router.get("/monitor")
async def monitor(scope: Scope, session: Session) -> dict[str, Any]:
    return await Insights(AgentService(session, scope)).monitor()


@router.get("/proposals")
async def pending(scope: Scope, session: Session) -> list[dict[str, Any]]:
    return await AgentService(session, scope).pending()


@router.post("/proposals", status_code=201)
async def propose(
    data: ProposalInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await limited(request, scope)
    result = await AgentService(session, scope).propose(data.operation, data.arguments)
    await session.commit()
    return result


@router.post("/proposals/{action_id}/decision")
async def decide(action_id: UUID, data: Decision, scope: Scope, session: Session) -> dict[str, Any]:
    result = await AgentService(session, scope).decide(action_id, data.decision)
    await session.commit()
    return result


@router.post("/documents")
async def document(
    request: Request,
    scope: Scope,
    session: Session,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[Literal["employees", "summary"], Form()] = "summary",
) -> dict[str, Any]:
    await limited(request, scope)
    if purpose == "employees":
        scope.require("hr.read", "hr.write")
    try:
        content = await file.read(MAX_BYTES + 1)
        text, rows = await run_in_threadpool(extract, file.filename or "", content)
    finally:
        await file.close()
    result = await process(
        AgentService(session, scope), manager(request), text, rows, purpose, ai_enabled(request)
    )
    await session.commit()
    return result
