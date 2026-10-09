"""Customer files API: list, upload (no S3 needed), download, delete.

Downloads are served as attachments with ``nosniff``, ``no-store`` and a sandboxing CSP,
so a stored file can never run in the app's origin.
"""

from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.modules.access.dependencies import Session, require
from app.modules.customers import files
from app.modules.customers.models import CustomerFile
from app.modules.customers.service import CustomerService, log_activity
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(tags=["customer-files"])
Read = Annotated[WorkspaceScope, Depends(require("customers.read"))]
Write = Annotated[WorkspaceScope, Depends(require("customers.write"))]


@router.get("/customers/{customer_id}/files")
async def customer_files(customer_id: UUID, scope: Read, session: Session) -> list[dict[str, Any]]:
    await CustomerService(session, scope).get(customer_id)
    rows = await session.scalars(
        WorkspaceRepository(session, CustomerFile, scope)
        .select()
        .where(CustomerFile.customer_id == customer_id)
        .order_by(CustomerFile.created_at.desc())
        .limit(200)
    )
    return [files.view(row) for row in rows]


@router.post("/customers/{customer_id}/files", status_code=status.HTTP_201_CREATED)
async def upload_file(
    customer_id: UUID,
    scope: Write,
    session: Session,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    await CustomerService(session, scope).get(customer_id)
    try:
        data = await file.read(files.MAX_BYTES + 1)
    finally:
        await file.close()
    row = await files.save(session, scope, customer_id, data, file.filename or "file", "upload")
    await log_activity(
        session, scope, customer_id, "file", f"File added: {row.name}", "customer_file", row.id
    )
    await session.commit()
    return files.view(row)


@router.get("/customer-files/{file_id}/download")
async def download_file(file_id: UUID, scope: Read, session: Session) -> Response:
    row = await WorkspaceRepository(session, CustomerFile, scope).get(file_id)
    data = await files.file_bytes(session, row)
    if not data:
        raise BusinessRuleViolation("FILE_MISSING", "This file is no longer available", 404)
    return Response(
        data,
        media_type=row.mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.name)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.delete("/customer-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: UUID, scope: Write, session: Session) -> Response:
    row = await WorkspaceRepository(session, CustomerFile, scope).get(file_id)
    if row.source == "receipt":
        raise BusinessRuleViolation("RECEIPT_KEPT", "Receipts are kept for the record", 409)
    name, customer_id = row.name, row.customer_id
    await session.delete(row)
    await log_activity(session, scope, customer_id, "file", f"File removed: {name}")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def files_for_messages(
    session: Session, scope: WorkspaceScope, message_ids: list[UUID]
) -> dict[UUID | None, dict[str, Any]]:
    """{message_id: file view} for an inbox page (so a document shows as a file chip)."""
    if not message_ids:
        return {}
    rows = await session.scalars(
        WorkspaceRepository(session, CustomerFile, scope)
        .select()
        .where(CustomerFile.message_id.in_(message_ids))
    )
    return {row.message_id: files.view(row) for row in rows}
