"""Bounded, repeatable indexing of accepted documents, including large uploads."""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.pi.knowledge import KnowledgeService
from app.modules.pi.models import KnowledgeDocument
from app.modules.pi.semantic import embed_document
from app.modules.products.models import (
    EnvironmentProductInstallation,
    PlatformProduct,
    TenantProductInstallation,
)
from app.modules.products.service import enabled_products
from app.shared.scope import WorkspaceScope


async def index_document(ctx: dict[str, Any], document_id: str) -> None:
    async with ctx["sessions"]() as session:
        document = await session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == UUID(document_id))
            .with_for_update()
        )
        if document is None:
            return
        scope = WorkspaceScope.system(
            document.tenant_id,
            document.environment_id,
            frozenset({"pi.read", "pi.knowledge.manage"}),
            "PI indexing",
        )
        if "knowledge" not in (await enabled_products(session, scope)).get("pi", set()):
            return
        if document.status != "ready":
            await KnowledgeService(session, scope).reindex(document, background=True)
        await session.commit()
    await embed_document(ctx, document_id)


async def sweep_knowledge(ctx: dict[str, Any]) -> None:
    """Recover pending work when the upload's enqueue was unavailable."""
    async with ctx["sessions"]() as session:
        ids = list(
            await session.scalars(
                select(KnowledgeDocument.id)
                .join(
                    EnvironmentProductInstallation,
                    (EnvironmentProductInstallation.tenant_id == KnowledgeDocument.tenant_id)
                    & (
                        EnvironmentProductInstallation.environment_id
                        == KnowledgeDocument.environment_id
                    ),
                )
                .join(
                    TenantProductInstallation,
                    TenantProductInstallation.id == EnvironmentProductInstallation.installation_id,
                )
                .join(PlatformProduct, PlatformProduct.id == TenantProductInstallation.product_id)
                .where(
                    KnowledgeDocument.status.in_(["pending", "processing"]),
                    EnvironmentProductInstallation.enabled.is_(True),
                    ~EnvironmentProductInstallation.disabled_features.contains(["knowledge"]),
                    TenantProductInstallation.status == "installed",
                    PlatformProduct.key == "pi",
                    PlatformProduct.status == "available",
                )
                .order_by(KnowledgeDocument.created_at)
                .limit(50)
            )
        )
    for document_id in ids:
        if ctx.get("redis"):
            await ctx["redis"].enqueue_job(
                "index_document", str(document_id), _job_id=f"index-sweep:{document_id}"
            )
        else:
            await index_document(ctx, str(document_id))
