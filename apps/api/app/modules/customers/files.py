"""Customer files kept in the database: what a customer sends on WhatsApp (documents,
photos), what the team uploads, and receipts.

The type always comes from the content (magic bytes), never the name or the browser. A
WhatsApp message's file is saved once, however often the message is processed. Bytes
are only loaded for a download.
"""

import hashlib
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import CustomerFile
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXTENSIONS = {
    "application/pdf": "pdf",
    DOCX: "docx",
    "text/plain": "txt",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sniff(data: bytes) -> str:
    """The file's real type from its first bytes; refuses anything else."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        from app.modules.pi_saas.teach_files import detect

        try:
            if detect(data)[0] == "docx":
                return DOCX
        except BusinessRuleViolation:
            pass
    else:
        try:
            data[:65536].decode("utf-8")
            if b"\x00" not in data[:65536]:
                return "text/plain"
        except UnicodeDecodeError:
            pass
    raise BusinessRuleViolation(
        "FILE_UNSUPPORTED", "Upload a PDF, Word (.docx), text file or photo", 415
    )


def clean_name(name: str, mime: str) -> str:
    base = re.sub(r"[\r\n\t]", " ", name.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    base = base[:180] or "file"
    extension = EXTENSIONS.get(mime, "bin")
    return base if base.lower().endswith(f".{extension}") else f"{base}.{extension}"


async def save(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    data: bytes,
    name: str,
    source: str,
    *,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    ref_type: str | None = None,
    ref_id: UUID | None = None,
) -> CustomerFile:
    """Store one file; a WhatsApp message's file is stored once (returns the existing)."""
    if not data:
        raise BusinessRuleViolation("FILE_EMPTY", "The file is empty")
    if len(data) > MAX_BYTES:
        raise BusinessRuleViolation("FILE_TOO_LARGE", "Use a file smaller than 10 MB", 413)
    repo = WorkspaceRepository(session, CustomerFile, scope)
    if message_id is not None:
        found = await repo.find(CustomerFile.message_id == message_id)
        if found is not None:
            return found
    mime = sniff(data)
    return await repo.add(
        repo.new(
            customer_id=customer_id,
            conversation_id=conversation_id,
            message_id=message_id,
            source=source,
            name=clean_name(name, mime),
            mime=mime,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            data=data,
            ref_type=ref_type,
            ref_id=ref_id,
            uploaded_by_label=scope.actor_label[:80],
        )
    )


async def save_from_message(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    data: bytes,
    name: str,
    *,
    conversation_id: UUID,
    message_id: UUID,
) -> CustomerFile | None:
    """Best effort for the WhatsApp path: a file that can't be kept never stops pi."""
    try:
        async with session.begin_nested():
            return await save(
                session,
                scope,
                customer_id,
                data,
                name,
                "whatsapp",
                conversation_id=conversation_id,
                message_id=message_id,
            )
    except (BusinessRuleViolation, DBAPIError):
        logger.warning("customer_file_not_saved", exc_info=True)
        return None


def view(row: CustomerFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "conversation_id": row.conversation_id,
        "message_id": row.message_id,
        "source": row.source,
        "name": row.name,
        "mime": row.mime,
        "size": row.size,
        "ref_type": row.ref_type,
        "ref_id": row.ref_id,
        "uploaded_by": row.uploaded_by_label,
        "created_at": row.created_at,
    }


async def file_bytes(session: AsyncSession, row: CustomerFile) -> bytes:
    data = await session.scalar(
        select(CustomerFile.data).where(
            CustomerFile.id == row.id,
            CustomerFile.tenant_id == row.tenant_id,
            CustomerFile.environment_id == row.environment_id,
        )
    )
    return bytes(data or b"")
