import hashlib
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.service import record
from app.modules.pi.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSource, PiMemory
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10 * 1024 * 1024)
    mime_type: str = "text/plain"


class FaqEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)


class FaqInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    title: str = Field(min_length=1, max_length=200)
    entries: list[FaqEntry] = Field(min_length=1, max_length=200)

    def as_document(self) -> DocumentInput:
        body = "\n\n".join(f"## {e.question}\n{e.answer}" for e in self.entries)
        return DocumentInput(
            source_id=self.source_id, title=self.title, body=body, mime_type="text/markdown"
        )


TEXT_TYPES = {"text/plain", "text/markdown"}
# Signatures of binary formats that must never be ingested as text.
BINARY_MAGIC = (
    b"%PDF",
    b"\x89PNG",
    b"PK\x03\x04",
    b"\xff\xd8\xff",
    b"GIF8",
    b"\x7fELF",
    b"MZ",
    b"\xd0\xcf\x11\xe0",
    b"Rar!",
    b"\x1f\x8b",
    b"OggS",
    b"ID3",
)
CHUNK_SIZE, CHUNK_STEP = 1000, 900
# Synchronous chunking is bounded; larger documents wait for the indexing worker.
SYNC_INDEX_MAX_BYTES = 256 * 1024


def sniff_text(raw: bytes, max_bytes: int) -> str:
    """Content-based validation: size, binary signatures, UTF-8, control characters."""
    if len(raw) > max_bytes:
        raise BusinessRuleViolation(
            "DOCUMENT_TOO_LARGE", "The document exceeds the upload limit", 413
        )
    if not raw.strip() or any(raw.startswith(magic) for magic in BINARY_MAGIC):
        raise BusinessRuleViolation(
            "UNSUPPORTED_DOCUMENT_TYPE", "Upload plain text or Markdown content", 415
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BusinessRuleViolation(
            "UNSUPPORTED_DOCUMENT_TYPE", "Upload plain text or Markdown content", 415
        ) from None
    control = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t\f")
    if "\x00" in text or control > max(8, len(text) // 200):
        raise BusinessRuleViolation(
            "UNSUPPORTED_DOCUMENT_TYPE", "Upload plain text or Markdown content", 415
        )
    return text


class KnowledgeService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope
        self.sources = WorkspaceRepository(session, KnowledgeSource, scope)
        self.documents = WorkspaceRepository(session, KnowledgeDocument, scope)
        self.chunks = WorkspaceRepository(session, KnowledgeChunk, scope)

    async def ingest(self, data: DocumentInput, max_bytes: int) -> KnowledgeDocument:
        self.scope.require("pi.knowledge.manage")
        await self.sources.get(data.source_id)
        if data.mime_type not in TEXT_TYPES:
            raise BusinessRuleViolation(
                "UNSUPPORTED_DOCUMENT_TYPE", "Upload plain text or Markdown content", 415
            )
        encoded = data.body.encode("utf-8")
        sniff_text(encoded, max_bytes)
        digest = hashlib.sha256(encoded).hexdigest()
        lock_key = int.from_bytes(
            hashlib.sha256(
                f"{self.scope.tenant_id}:{self.scope.environment_id}:{data.source_id}:{digest}".encode()
            ).digest()[:8],
            "big",
            signed=True,
        )
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        doc = await self.documents.find(
            KnowledgeDocument.source_id == data.source_id, KnowledgeDocument.content_hash == digest
        )
        if doc:
            return doc
        doc = await self.documents.add(
            self.documents.new(
                source_id=data.source_id,
                title=data.title,
                body=data.body,
                mime_type=data.mime_type,
                byte_size=len(encoded),
                content_hash=digest,
                status="processing",
                created_by_label=self.scope.actor_label,
            )
        )
        if doc.byte_size > SYNC_INDEX_MAX_BYTES:
            doc.status = "pending"
            return doc
        await self.reindex(doc)
        return doc

    async def reindex(self, doc: KnowledgeDocument, *, background: bool = False) -> None:
        self.scope.require("pi.knowledge.manage")
        if doc.byte_size > SYNC_INDEX_MAX_BYTES and not background:
            doc.status = "pending"
            return
        await self.session.execute(
            delete(KnowledgeChunk).where(
                self.chunks.predicate(), KnowledgeChunk.document_id == doc.id
            )
        )
        offsets = range(0, len(doc.body), CHUNK_STEP)
        for ordinal, offset in enumerate(offsets):
            self.session.add(
                self.chunks.new(
                    document_id=doc.id,
                    source_id=doc.source_id,
                    ordinal=ordinal,
                    content=doc.body[offset : offset + CHUNK_SIZE],
                )
            )
        await self.session.flush()
        doc.chunk_count = len(offsets)
        doc.error_code = None
        doc.status, doc.processed_at = "ready", datetime.now(UTC)
        await record(
            self.session,
            "pi.knowledge_ingested",
            scope=self.scope,
            entity_type="knowledge_document",
            entity_id=doc.id,
            details={"chunks": doc.chunk_count},
        )

    async def delete_document(self, document_id: UUID) -> None:
        self.scope.require("pi.knowledge.manage")
        doc = await self.documents.get(document_id, for_update=True)
        await self.session.execute(
            delete(KnowledgeChunk).where(
                self.chunks.predicate(), KnowledgeChunk.document_id == doc.id
            )
        )
        await self.documents.delete(doc)
        await record(
            self.session,
            "pi.knowledge_deleted",
            scope=self.scope,
            entity_type="knowledge_document",
            entity_id=document_id,
        )

    async def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        self.scope.require("pi.read")
        terms = func.websearch_to_tsquery("simple", query[:500])
        statement = (
            select(KnowledgeChunk.content, KnowledgeDocument.title, KnowledgeSource.name)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
            .where(
                self.chunks.predicate(),
                self.documents.predicate(),
                self.sources.predicate(),
                KnowledgeDocument.status == "ready",
                KnowledgeSource.status == "active",
                KnowledgeChunk.search_vector.op("@@")(terms),
            )
            .order_by(func.ts_rank(KnowledgeChunk.search_vector, terms).desc())
            .limit(min(max(limit, 1), 10))
        )
        rows = await self.session.execute(statement)
        return [
            {"snippet": content, "title": title, "source": source}
            for content, title, source in rows
        ]


async def remember(
    session: AsyncSession, scope: WorkspaceScope, customer_id: UUID, content: str, message_id: UUID
) -> None:
    scope.require("sales.write")
    value = content[:500]
    await session.execute(
        insert(PiMemory)
        .values(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            customer_id=customer_id,
            kind="requirement",
            content=value,
            content_hash=hashlib.sha256(value.encode()).hexdigest(),
            source_message_id=message_id,
        )
        .on_conflict_do_nothing(constraint="uq_pi_memories_entry")
    )
