"""Optional semantic indexing with durable retries; lexical search remains available."""

from typing import Any
from uuid import UUID

from sqlalchemy import cast, select, text

from app.ai.embeddings import embed
from app.ai.gateway import GatewayUnavailable
from app.modules.pi.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from app.modules.products.service import product_enabled
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


async def vector_available(session: Any) -> bool:
    return bool(
        await session.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
    )


async def embed_document(ctx: dict[str, Any], document_id: str) -> None:
    settings = ctx["settings"]
    if not settings.semantic_search_enabled or not settings.openai_models.get("embedding"):
        return
    async with ctx["sessions"]() as session:
        document = await session.get(KnowledgeDocument, UUID(document_id))
        if not document or document.status != "ready":
            return
        scope = WorkspaceScope.system(
            document.tenant_id, document.environment_id, frozenset({"pi.read"}), "PI indexing"
        )
        if not await product_enabled(session, scope, "pi") or not await vector_available(session):
            return
        repo = WorkspaceRepository(session, KnowledgeChunk, scope)
        chunks = list(
            await session.scalars(
                repo.select()
                .where(KnowledgeChunk.document_id == document.id)
                .order_by(KnowledgeChunk.ordinal)
            )
        )
        pending = [
            (x.id, x.content)
            for x in chunks
            if x.embedding_values is None
            or x.embedding_model != settings.openai_models["embedding"]
        ]
        await session.commit()
        for offset in range(0, len(pending), 32):
            batch = pending[offset : offset + 32]
            try:
                vectors = await embed(settings, ctx["http"], [value for _, value in batch])
            except GatewayUnavailable:
                document.error_code = "EMBEDDING_UNAVAILABLE"
                await session.commit()
                return
            for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                chunk = await session.scalar(
                    repo.select().where(KnowledgeChunk.id == chunk_id).with_for_update()
                )
                if chunk is not None:
                    chunk.embedding_values, chunk.embedding_model = (
                        vector,
                        settings.openai_models["embedding"],
                    )
            await session.commit()
        document.error_code = None
        await session.commit()


async def semantic_search(
    session: Any,
    scope: WorkspaceScope,
    vector: list[float],
    model: str,
    limit: int,
    min_score: float,
) -> list[dict[str, str]]:
    from pgvector.sqlalchemy import VECTOR

    distance = cast(KnowledgeChunk.embedding_values, VECTOR(len(vector))).cosine_distance(vector)
    rows = await session.execute(
        select(KnowledgeChunk.content, KnowledgeDocument.title, KnowledgeSource.name)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
        .where(
            WorkspaceRepository(session, KnowledgeChunk, scope).predicate(),
            WorkspaceRepository(session, KnowledgeDocument, scope).predicate(),
            WorkspaceRepository(session, KnowledgeSource, scope).predicate(),
            KnowledgeDocument.status == "ready",
            KnowledgeSource.status == "active",
            KnowledgeChunk.embedding_model == model,
            KnowledgeChunk.embedding_values.is_not(None),
            distance <= 1 - min_score,
        )
        .order_by(distance)
        .limit(limit)
    )
    return [
        {"snippet": content, "title": title, "source": source} for content, title, source in rows
    ]
