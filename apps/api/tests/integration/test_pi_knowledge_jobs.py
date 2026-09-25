"""Knowledge ingestion through HTTP, the real indexer, and scoped PostgreSQL search."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from test_pi_pipeline import pi_workspace
from test_service_lifecycle import create

from app.modules.pi.knowledge_jobs import index_document, sweep_knowledge
from app.modules.pi.models import KnowledgeChunk, KnowledgeDocument

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("method", ["text", "upload", "faq"])
async def test_large_documents_are_indexed_and_retries_are_idempotent(api, business_db, method):
    pi = await pi_workspace(api, business_db)
    try:
        source = await create(api, "pi/knowledge/sources", {"name": "Manuals", "kind": "file"})
        body = "orchidalpha installation instructions\n" * 8000
        if method == "text":
            doc = await create(
                api,
                "pi/knowledge/documents",
                {"source_id": source["id"], "title": "Manual", "body": body},
            )
        elif method == "upload":
            response = await api.post(
                "/api/v1/pi/knowledge/documents/upload",
                data={"source_id": source["id"]},
                files={"file": ("manual.md", body.encode(), "text/markdown")},
            )
            assert response.status_code == 200
            doc = response.json()
        else:
            doc = await create(
                api,
                "pi/knowledge/faq",
                {
                    "source_id": source["id"],
                    "title": "Manual FAQ",
                    "entries": [
                        {"question": f"Question {i}?", "answer": "orchidalpha " * 300}
                        for i in range(100)
                    ],
                },
            )
        assert (doc["status"], doc["chunk_count"]) == ("pending", 0)
        assert pi.app.state.queue.jobs[-1] == ("index_document", (doc["id"],))
        await index_document(pi.ctx, doc["id"])
        first_ids = list(
            await business_db.scalars(
                select(KnowledgeChunk.id)
                .where(KnowledgeChunk.document_id == UUID(doc["id"]))
                .order_by(KnowledgeChunk.ordinal)
            )
        )
        assert len(first_ids) > 250
        result = (await api.get(f"/api/v1/pi/knowledge/documents/{doc['id']}")).json()
        assert result["status"] == "ready" and result["chunk_count"] == len(first_ids)
        found = (await api.get("/api/v1/pi/knowledge/search?q=orchidalpha")).json()
        assert found and found[0]["title"] == doc["title"]
        await index_document(pi.ctx, doc["id"])
        second_ids = list(
            await business_db.scalars(
                select(KnowledgeChunk.id)
                .where(KnowledgeChunk.document_id == UUID(doc["id"]))
                .order_by(KnowledgeChunk.ordinal)
            )
        )
        assert second_ids == first_ids
    finally:
        await pi.close()


async def test_pending_recovery_rechecks_product_and_deleted_documents(api, business_db):
    pi = await pi_workspace(api, business_db)
    try:
        source = await create(api, "pi/knowledge/sources", {"name": "Manuals", "kind": "file"})
        doc = await create(
            api,
            "pi/knowledge/documents",
            {"source_id": source["id"], "title": "Recovery", "body": "recoveryword " * 23000},
        )
        # Pretend enqueue was lost. The durable pending row is the recovery source.
        pi.app.state.queue.jobs.clear()
        assert (
            await api.put("/api/v1/products/pi/environment", json={"enabled": False})
        ).status_code == 200
        await index_document(pi.ctx, doc["id"])
        await sweep_knowledge(pi.ctx)
        row = await business_db.get(KnowledgeDocument, UUID(doc["id"]))
        assert row.status == "pending" and row.chunk_count == 0
        assert (
            await api.put("/api/v1/products/pi/environment", json={"enabled": True})
        ).status_code == 200
        await sweep_knowledge(pi.ctx)
        await business_db.refresh(row)
        assert row.status == "ready" and row.chunk_count > 0
        assert (await api.delete(f"/api/v1/pi/knowledge/documents/{doc['id']}")).status_code == 204
        await index_document(pi.ctx, doc["id"])
        assert (
            await business_db.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == UUID(doc["id"]))
            )
            == 0
        )
    finally:
        await pi.close()


@pytest.mark.parametrize("method", ["text", "upload", "faq"])
async def test_every_ingestion_path_schedules_embedding_and_retry(
    api, business_db, monkeypatch, method
):
    pi = await pi_workspace(api, business_db)
    calls = []

    async def embed(ctx, document_id):
        calls.append(document_id)

    monkeypatch.setattr("app.modules.pi.knowledge_jobs.embed_document", embed)
    try:
        source = await create(api, "pi/knowledge/sources", {"name": "Policies", "kind": "faq"})
        if method == "text":
            doc = await create(
                api,
                "pi/knowledge/documents",
                {"source_id": source["id"], "title": "Policy", "body": "Two revision rounds."},
            )
        elif method == "faq":
            doc = await create(
                api,
                "pi/knowledge/faq",
                {
                    "source_id": source["id"],
                    "title": "FAQ",
                    "entries": [{"question": "Revisions?", "answer": "Two rounds."}],
                },
            )
        else:
            response = await api.post(
                "/api/v1/pi/knowledge/documents/upload",
                data={"source_id": source["id"]},
                files={"file": ("policy.txt", b"Two revision rounds.", "text/plain")},
            )
            assert response.status_code == 200
            doc = response.json()
        assert doc["status"] == "ready"
        assert pi.app.state.queue.jobs[-1] == ("index_document", (doc["id"],))
        await index_document(pi.ctx, doc["id"])
        assert calls == [doc["id"]]
        assert (
            await api.post(f"/api/v1/pi/knowledge/documents/{doc['id']}/retry")
        ).status_code == 200
        assert pi.app.state.queue.jobs[-1] == ("index_document", (doc["id"],))
    finally:
        await pi.close()
