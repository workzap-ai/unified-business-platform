from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.ai.gateway import Gateway
from app.modules.access.dependencies import Scope, Session
from app.modules.pi.configuration import (
    VersionInput,
    publish,
    seed_agents,
    settings_row,
    settings_view,
    update_settings,
)
from app.modules.pi.graph import route_message
from app.modules.pi.knowledge import (
    DocumentInput,
    FaqInput,
    KnowledgeService,
    sniff_text,
)
from app.modules.pi.models import (
    KnowledgeDocument,
    KnowledgeSource,
    PiAgent,
    PiAgentRun,
    PiAgentTool,
    PiAgentVersion,
    PiToolCall,
)
from app.modules.pi.schemas import BodyInput
from app.modules.pi.service import PiService
from app.modules.pi.tools.catalog import TOOL_CATALOG
from app.shared.errors import BusinessRuleViolation
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi", tags=["pi-configuration"])


class SettingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any


class EnabledInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["company_info", "faq", "policy", "catalog", "approved_answer", "file"]
    description: str = Field(default="", max_length=300)


class SourceStatus(BaseModel):
    status: Literal["active", "disabled"]


@router.get("/settings")
async def settings(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.settings.manage")
    result = await settings_view(session, scope, request.app.state.settings)
    await session.commit()
    return result


@router.patch("/settings/{section}")
async def change_settings(
    section: str, data: SettingInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.settings.manage")
    if (
        section == "knowledge_config"
        and isinstance(data.value, dict)
        and data.value.get("semantic_enabled")
    ):
        from app.modules.pi.semantic import vector_available

        config = request.app.state.settings
        if (
            not config.semantic_search_enabled
            or not config.openai_api_key
            or not config.openai_models.get("embedding")
            or not await vector_available(session)
        ):
            raise BusinessRuleViolation(
                "SEMANTIC_NOT_CONFIGURED",
                "Configure the embedding model and pgvector before enabling semantic search",
            )
    await update_settings(session, scope, section, data.value)
    await session.commit()
    return await settings_view(session, scope, request.app.state.settings)


async def agent_view(agent: PiAgent, scope: Scope, session: Session) -> dict[str, Any]:
    versions = WorkspaceRepository(session, PiAgentVersion, scope)
    version = await versions.find(
        PiAgentVersion.agent_id == agent.id, PiAgentVersion.version == agent.current_version
    )
    config = await settings_row(session, scope)
    runs = WorkspaceRepository(session, PiAgentRun, scope)
    count, success, latency, latest = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(PiAgentRun.status == "completed"),
                func.avg(PiAgentRun.latency_ms),
                func.max(PiAgentRun.created_at),
            ).where(
                runs.predicate(),
                PiAgentRun.agent_path.contains([agent.key]),
                PiAgentRun.created_at >= datetime.now(UTC) - timedelta(days=7),
            )
        )
    ).one()
    disabled = set(
        await session.scalars(
            WorkspaceRepository(session, PiAgentTool, scope)
            .select()
            .with_only_columns(PiAgentTool.tool_key)
            .where(PiAgentTool.agent_id == agent.id, PiAgentTool.enabled.is_(False))
        )
    )
    return {
        "id": agent.id,
        "key": agent.key,
        "name": agent.name,
        "role": agent.name,
        "description": agent.description,
        "enabled": agent.enabled,
        "current_version": agent.current_version,
        "model_alias": version.model_alias if version else "fast",
        "temperature": str(version.temperature) if version else "0.20",
        "tools": [
            key
            for key in TOOL_CATALOG
            if config.tool_permissions.get(key, True) is not False and key not in disabled
        ],
        "runs_7d": count,
        "success_rate": success / count if count else 0,
        "avg_latency_ms": float(latency or 0),
        "last_run_at": latest,
    }


@router.get("/agents")
async def agents(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.agents.manage")
    await seed_agents(session, scope)
    rows = list(
        await session.scalars(
            WorkspaceRepository(session, PiAgent, scope).select().order_by(PiAgent.key)
        )
    )
    result = [await agent_view(row, scope, session) for row in rows]
    await session.commit()
    return result


@router.get("/agents/{agent_id}")
async def agent(agent_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    return await agent_view(
        await WorkspaceRepository(session, PiAgent, scope).get(agent_id), scope, session
    )


def version_view(row: PiAgentVersion, current: int) -> dict[str, Any]:
    return {
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "agent_id",
                "version",
                "instructions",
                "model_alias",
                "note",
                "created_by_label",
                "created_at",
            )
        },
        "temperature": str(row.temperature),
        "status": "active" if row.version == current else "archived",
    }


@router.get("/agents/{agent_id}/versions")
async def versions(agent_id: UUID, scope: Scope, session: Session) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.agents.manage")
    row = await WorkspaceRepository(session, PiAgent, scope).get(agent_id)
    rows = await session.scalars(
        WorkspaceRepository(session, PiAgentVersion, scope)
        .select()
        .where(PiAgentVersion.agent_id == agent_id)
        .order_by(PiAgentVersion.version.desc())
        .limit(100)
    )
    return [version_view(v, row.current_version) for v in rows]


@router.post("/agents/{agent_id}/versions")
async def publish_version(
    agent_id: UUID, data: VersionInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    row = await publish(session, scope, agent_id, data)
    await session.commit()
    return version_view(row, row.version)


@router.post("/agents/{agent_id}/versions/{version_id}/rollback")
async def rollback(
    agent_id: UUID, version_id: UUID, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    row = await WorkspaceRepository(session, PiAgentVersion, scope).get(version_id)
    from app.shared.errors import ResourceNotFound

    if row.agent_id != agent_id:
        raise ResourceNotFound
    result = await publish(
        session,
        scope,
        agent_id,
        VersionInput(
            instructions=row.instructions,
            model_alias=row.model_alias,
            temperature=row.temperature,
            note=f"Rollback to version {row.version}",
        ),
    )
    await session.commit()
    return version_view(result, result.version)


@router.put("/agents/{agent_id}/enabled")
async def agent_enabled(
    agent_id: UUID, data: EnabledInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    row = await WorkspaceRepository(session, PiAgent, scope).get(agent_id, for_update=True)
    row.enabled = data.enabled
    await session.commit()
    return await agent_view(row, scope, session)


@router.get("/tools")
async def tools(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.agents.manage")
    config = await settings_row(session, scope)
    rows = await session.execute(
        select(
            PiToolCall.tool_key,
            func.count(),
            func.count().filter(PiToolCall.status != "success"),
            func.max(PiToolCall.created_at),
        )
        .where(
            WorkspaceRepository(session, PiToolCall, scope).predicate(),
            PiToolCall.created_at >= datetime.now(UTC) - timedelta(days=7),
        )
        .group_by(PiToolCall.tool_key)
    )
    stats = {key: (count, failed, latest) for key, count, failed, latest in rows}
    return [
        {
            "key": key,
            "name": key.replace("_", " ").capitalize(),
            "description": spec.description,
            "capability": spec.capability,
            "permission": spec.permission,
            "requires_confirmation": spec.requires_confirmation,
            "enabled": config.tool_permissions.get(key, True) is not False,
            "calls_7d": stats.get(key, (0, 0, None))[0],
            "failures_7d": stats.get(key, (0, 0, None))[1],
            "last_called_at": stats.get(key, (0, 0, None))[2],
        }
        for key, spec in TOOL_CATALOG.items()
    ]


@router.get("/tools/catalog")
async def tool_catalog(scope: Scope, session: Session) -> list[dict[str, Any]]:
    """Machine-readable definitions (input/output JSON schema) for the runtime and admins."""
    await PiService(session, scope).require("pi.agents.manage")
    return [spec.describe() for spec in TOOL_CATALOG.values()]


@router.put("/tools/{key}/enabled")
async def tool_enabled(
    key: str, data: EnabledInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.settings.manage")
    scope.require("pi.agents.manage")
    if key not in TOOL_CATALOG:
        raise BusinessRuleViolation("UNKNOWN_TOOL", "Unknown PI tool")
    config = await settings_row(session, scope)
    current = {k: v for k, v in config.tool_permissions.items() if k in TOOL_CATALOG}
    await update_settings(session, scope, "tool_permissions", {**current, key: data.enabled})
    await session.commit()
    return next(t for t in await tools(scope, session) if t["key"] == key)


@router.get("/knowledge/sources")
async def sources(scope: Scope, session: Session) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    service = KnowledgeService(session, scope)
    rows = list(
        await session.scalars(service.sources.select().order_by(KnowledgeSource.name).limit(100))
    )
    counts = await session.execute(
        select(
            KnowledgeDocument.source_id,
            func.count(),
            func.count().filter(KnowledgeDocument.status == "ready"),
            func.count().filter(KnowledgeDocument.status == "failed"),
        )
        .where(service.documents.predicate())
        .group_by(KnowledgeDocument.source_id)
    )
    stats = {key: (n, ready, failed) for key, n, ready, failed in counts}
    return [
        {
            **{
                key: getattr(row, key)
                for key in ("id", "name", "kind", "description", "status", "updated_at")
            },
            "documents": stats.get(row.id, (0, 0, 0))[0],
            "ready": stats.get(row.id, (0, 0, 0))[1],
            "failed": stats.get(row.id, (0, 0, 0))[2],
        }
        for row in rows
    ]


@router.post("/knowledge/sources")
async def add_source(data: SourceInput, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    service = KnowledgeService(session, scope)
    row = await service.sources.add(service.sources.new(**data.model_dump()))
    await session.commit()
    return next(x for x in await sources(scope, session) if x["id"] == row.id)


@router.put("/knowledge/sources/{source_id}/status")
async def source_status(
    source_id: UUID, data: SourceStatus, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    row = await KnowledgeService(session, scope).sources.get(source_id)
    row.status = data.status
    await session.commit()
    return next(x for x in await sources(scope, session) if x["id"] == row.id)


async def document_view(row: KnowledgeDocument, scope: Scope, session: Session) -> dict[str, Any]:
    source = await KnowledgeService(session, scope).sources.get(row.source_id)
    return {
        **{
            key: getattr(row, key)
            for key in (
                "id",
                "source_id",
                "title",
                "mime_type",
                "byte_size",
                "status",
                "chunk_count",
                "error_code",
                "created_by_label",
                "created_at",
                "processed_at",
                "body",
            )
        },
        "source_name": source.name,
    }


@router.get("/knowledge/documents")
async def documents(
    scope: Scope,
    session: Session,
    source_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    service = KnowledgeService(session, scope)
    query = service.documents.select()
    if source_id:
        query = query.where(KnowledgeDocument.source_id == source_id)
    if status:
        query = query.where(KnowledgeDocument.status == status)
    if search:
        from app.shared.workspace_repository import like_pattern

        query = query.where(KnowledgeDocument.title.ilike(like_pattern(search[:100])))
    rows = list(
        await session.scalars(query.order_by(KnowledgeDocument.created_at.desc()).limit(100))
    )
    return [await document_view(row, scope, session) for row in rows]


@router.get("/knowledge/documents/{document_id}")
async def document(document_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    return await document_view(
        await KnowledgeService(session, scope).documents.get(document_id), scope, session
    )


@router.post("/knowledge/documents")
async def add_document(
    data: DocumentInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    row = await KnowledgeService(session, scope).ingest(
        data, request.app.state.settings.knowledge_upload_max_bytes
    )
    await session.commit()
    await request.app.state.queue.enqueue("index_document", str(row.id), job_id=f"index:{row.id}")
    return await document_view(row, scope, session)


@router.put("/agents/{agent_id}/tools/{key}")
async def agent_tool(
    agent_id: UUID, key: str, data: EnabledInput, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    agent = await WorkspaceRepository(session, PiAgent, scope).get(agent_id)
    if key not in TOOL_CATALOG:
        raise BusinessRuleViolation("UNKNOWN_TOOL", "Unknown PI tool")
    await session.execute(
        insert(PiAgentTool)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            agent_id=agent.id,
            tool_key=key,
            enabled=data.enabled,
        )
        .on_conflict_do_update(constraint="uq_pi_agent_tools_entry", set_={"enabled": data.enabled})
    )
    from app.modules.audit.service import record

    await record(
        session,
        "pi.agent_tool_updated",
        scope=scope,
        entity_type="pi_agent",
        entity_id=agent.id,
        details={"tool": key, "enabled": data.enabled},
    )
    await session.commit()
    return await agent_view(agent, scope, session)


@router.post("/agent-test")
async def agent_test(
    data: BodyInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.agents.manage")
    config = await settings_row(session, scope)
    await session.commit()
    result = await route_message(
        data.body,
        Gateway(request.app.state.settings, request.app.state.http),
        threshold=float(config.handoff_rules.get("low_confidence_threshold", "0.75")),
    )
    return {
        "simulated": True,
        "intent": result["intent"],
        "confidence": result["confidence"],
        "route": ["router", result["agent"]],
        "tools": [],
        "note": (
            "AI providers are unavailable, so this message would go to a team member."
            if result["provider_failed"]
            else "Routing preview only. No customer records, messages or actions were created."
        ),
    }


@router.post("/knowledge/documents/{document_id}/retry")
async def retry_document(
    document_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    service = KnowledgeService(session, scope)
    row = await service.documents.get(document_id, for_update=True)
    if row.status != "ready":
        await service.reindex(row)
    await session.commit()
    await request.app.state.queue.enqueue(
        "index_document",
        str(row.id),
        job_id=f"index-retry:{row.id}:{row.updated_at.isoformat()}",
    )
    return await document_view(row, scope, session)


@router.post("/knowledge/faq")
async def add_faq(
    data: FaqInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    row = await KnowledgeService(session, scope).ingest(
        data.as_document(), request.app.state.settings.knowledge_upload_max_bytes
    )
    await session.commit()
    await request.app.state.queue.enqueue("index_document", str(row.id), job_id=f"index:{row.id}")
    return await document_view(row, scope, session)


@router.post("/knowledge/documents/upload")
async def upload_document(
    request: Request,
    scope: Scope,
    session: Session,
    source_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=200)] = "",
) -> dict[str, Any]:
    """Multipart upload. The type is decided by content sniffing, not the client header."""
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    limit = request.app.state.settings.knowledge_upload_max_bytes
    raw = await file.read(limit + 1)
    text = sniff_text(raw, limit)
    name = (file.filename or "document.txt").rsplit("/", 1)[-1][:200]
    mime = "text/markdown" if name.lower().endswith((".md", ".markdown")) else "text/plain"
    row = await KnowledgeService(session, scope).ingest(
        DocumentInput(source_id=source_id, title=title.strip() or name, body=text, mime_type=mime),
        limit,
    )
    await session.commit()
    await request.app.state.queue.enqueue("index_document", str(row.id), job_id=f"index:{row.id}")
    return await document_view(row, scope, session)


@router.delete("/knowledge/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID, scope: Scope, session: Session) -> None:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    await KnowledgeService(session, scope).delete_document(document_id)
    await session.commit()


@router.get("/knowledge/search")
async def search_knowledge(
    scope: Scope,
    session: Session,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(5, ge=1, le=10),
) -> list[dict[str, str]]:
    await PiService(session, scope).require("pi.knowledge.manage", "knowledge")
    return await KnowledgeService(session, scope).search(q, limit)
