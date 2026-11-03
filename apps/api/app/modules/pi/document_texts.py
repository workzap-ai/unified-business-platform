"""E1: keep what a customer's document says, with where it says it (`pi_document_texts`).

Written once, at upload, from the SAME local readers the document reader uses (`documents.py`,
`teach_files.py`): no model call, no network. The text is redacted before it is stored; the file's
bytes stay in `customer_files`. One row per page, sheet, slide or section, so an answer can cite
"page 3" and a later question is answered from stored text.

Brain mode only. Idempotent: a file already stored is left alone (unique on file + ordinal). A file
that cannot be read (scanned, locked, unknown type) stores nothing and never stops the chat. Every
write is in a savepoint; a missing table is tolerated.
"""

import hashlib
import io
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pi import memory_ledger
from app.modules.pi.memory_models import PiDocumentText
from app.shared.scope import WorkspaceScope

logger = logging.getLogger(__name__)

MAX_SEGMENTS = 60
SEGMENT_CAP = 4000
SECTION_SIZE = 3000
_MARK = re.compile(r"^(Sheet \d+|Slide \d+):\s*", re.MULTILINE)


def segments(raw: bytes) -> list[tuple[str, str]]:
    """[(reference, text)] for a PDF, Word, Excel, PowerPoint or text file; [] when unreadable.
    Pure and local."""
    from app.modules.pi import documents
    from app.modules.pi_saas.teach_files import detect

    try:
        office = documents.office_text(raw)
        if office is not None:
            return _marked(office[1])
        kind, _ = detect(raw)
        if kind == "pdf":
            return _pdf_pages(raw)
        label, text = documents.document_text(raw)
        del label
        return _sections(text)
    except Exception:  # noqa: BLE001 - unreadable means nothing stored
        return []


def _marked(text: str) -> list[tuple[str, str]]:
    parts = _MARK.split(text)
    if len(parts) < 3:
        return _sections(text)
    out: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1].strip()
        if body:
            out.append((parts[i], body))
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    """Redacted FIRST over the whole text (a number is never cut in half by a section edge), then
    cut into sections at a space."""
    text = memory_ledger.redacted(text, len(text) + 1)
    out: list[tuple[str, str]] = []
    start = 0
    while start < len(text):
        end = min(start + SECTION_SIZE, len(text))
        if end < len(text) and (space := text.rfind(" ", start, end)) > start:
            end = space
        piece = text[start:end].strip()
        if piece:
            out.append((f"section {len(out) + 1}", piece))
        start = end
    return out


def _pdf_pages(raw: bytes) -> list[tuple[str, str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    if reader.is_encrypted and not reader.decrypt(""):
        return []
    out: list[tuple[str, str]] = []
    for number, page in enumerate(list(reader.pages)[:MAX_SEGMENTS], start=1):
        body = (page.extract_text() or "").strip()
        if body:
            out.append((f"page {number}", body))
    return out


async def store(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    file_id: UUID,
    raw: bytes,
) -> int:
    """Store the redacted segments of one file; returns how many rows were added (0 when the file
    was stored before, is unreadable, or the table is missing). Never raises."""
    return await _write(session, scope, customer_id, file_id, segments(raw)[:MAX_SEGMENTS])


PICTURE_MARK = " (read from a picture)"


async def store_scanned(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    file_id: UUID,
    pages: list[tuple[int, str]],
    total: int,
) -> int:
    """Store the vision-read text of a scanned PDF, one row per page. The reference says it was
    read from a picture (never exact). When pages were not read, a last row says so. Same redaction
    and idempotence as `store`. Never raises."""
    from app.modules.pi import documents

    found = [(f"page {n}{PICTURE_MARK}", t) for n, t in pages if t.strip()]
    if not found:
        return 0
    if total > documents.MAX_SCANNED_PAGES:
        found.append(("pages not read", documents.not_read_note(len(pages), total)))
    return await _write(session, scope, customer_id, file_id, found[:MAX_SEGMENTS])


async def store_staff_file(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID,
    file_id: UUID,
    raw: bytes,
    response_rules: dict[str, Any] | None,
) -> int:
    """A file staff attached to a customer: the same local readers, off the event loop. Brain mode
    only; best effort; a file that cannot be read stores nothing and never blocks the upload."""
    import asyncio

    if not memory_ledger.brain_on(response_rules):
        return 0
    try:
        found = (await asyncio.to_thread(segments, raw))[:MAX_SEGMENTS]
        return await _write(session, scope, customer_id, file_id, found)
    except Exception:  # noqa: BLE001
        logger.warning("pi_staff_file_text_not_stored", exc_info=True)
        return 0


async def _write(
    session: AsyncSession,
    scope: WorkspaceScope,
    customer_id: UUID,
    file_id: UUID,
    found: list[tuple[str, str]],
) -> int:
    if not found:
        return 0
    try:
        async with session.begin_nested():
            have = set(
                await session.scalars(
                    select(PiDocumentText.ordinal).where(
                        PiDocumentText.tenant_id == scope.tenant_id,
                        PiDocumentText.environment_id == scope.environment_id,
                        PiDocumentText.customer_file_id == file_id,
                    )
                )
            )
            added = 0
            for ordinal, (ref, body) in enumerate(found):
                if ordinal in have:
                    continue
                clean = memory_ledger.redacted(body, SEGMENT_CAP)
                if not clean:
                    continue
                session.add(
                    PiDocumentText(
                        tenant_id=scope.tenant_id,
                        environment_id=scope.environment_id,
                        customer_id=customer_id,
                        customer_file_id=file_id,
                        ordinal=ordinal,
                        ref=ref[:80],
                        text=clean,
                        content_hash=hashlib.sha256(clean.encode("utf-8")).hexdigest(),
                    )
                )
                added += 1
            await session.flush()
            return added
    except Exception:  # noqa: BLE001
        logger.warning("pi_document_text_not_stored", exc_info=True)
        return 0


async def on_file_saved(
    session: AsyncSession,
    scope: WorkspaceScope,
    *,
    customer_id: UUID | None,
    file_id: UUID | None,
    raw: bytes,
    response_rules: dict[str, Any] | None,
) -> int:
    """The hook `runtime._keep_file` calls after a file is kept. Brain mode only."""
    if customer_id is None or file_id is None or not memory_ledger.brain_on(response_rules):
        return 0
    return await store(session, scope, customer_id=customer_id, file_id=file_id, raw=raw)
