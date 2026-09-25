from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict

from app.core.pagination import Pagination
from app.integrations import business, whatsapp_bridge, workflows
from app.integrations.email import EMAIL_KEYS
from app.integrations.http import OutboundClient
from app.integrations.providers.s3 import S3Provider, scoped_key
from app.integrations.runtime import ConnectionRuntime
from app.integrations.workflow_models import IntegrationOperation, IntegrationWorkflow
from app.modules.access.dependencies import Scope, Session
from app.modules.integrations.api_keys import ApiKeyScope
from app.modules.integrations.models import IntegrationConnection
from app.shared.errors import BusinessRuleViolation, ResourceNotFound
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(tags=["integration workflows"])


def http(request: Request) -> OutboundClient:
    return OutboundClient(
        request.app.state.settings,
        request.app.state.http,
        resolver=getattr(request.app.state, "integration_resolver", None),
    )


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class RetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acknowledge_duplicate_risk: bool = False


@router.get("/integrations/capabilities")
async def capabilities(scope: Scope, session: Session) -> dict[str, bool]:
    rows = await session.scalars(
        WorkspaceRepository(session, IntegrationConnection, scope)
        .select()
        .where(IntegrationConnection.status.in_(("connected", "degraded")))
    )
    keys = {row.integration_key for row in rows}
    return {
        "email": bool(keys.intersection(EMAIL_KEYS)),
        "storage": "s3" in keys,
        "payments": "stripe" in keys,
    }


@router.get("/integrations/connections/{connection_id}/workflow")
async def rule(connection_id: UUID, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("integrations.read")
    await WorkspaceRepository(session, IntegrationConnection, scope).get(connection_id)
    row = await WorkspaceRepository(session, IntegrationWorkflow, scope).find(
        IntegrationWorkflow.connection_id == connection_id
    )
    return workflows.rule_view(row)


@router.put("/integrations/connections/{connection_id}/workflow")
async def save_rule(
    connection_id: UUID, data: workflows.WorkflowInput, scope: Scope, session: Session
) -> dict[str, Any]:
    result = await workflows.save_rule(session, scope, connection_id, data)
    await session.commit()
    return result


@router.get("/integrations/connections/{connection_id}/operations")
async def operations(connection_id: UUID, scope: Scope, session: Session) -> list[dict[str, Any]]:
    scope.require("integrations.read")
    await WorkspaceRepository(session, IntegrationConnection, scope).get(connection_id)
    rows = await session.scalars(
        WorkspaceRepository(session, IntegrationOperation, scope)
        .select()
        .where(IntegrationOperation.connection_id == connection_id)
        .order_by(IntegrationOperation.created_at.desc())
        .limit(100)
    )
    return [workflows.operation_view(row) for row in rows]


@router.post("/integrations/operations/{operation_id}/retry")
async def retry(
    operation_id: UUID, data: RetryInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("integrations.operate")
    op = await WorkspaceRepository(session, IntegrationOperation, scope).get(
        operation_id, for_update=True
    )
    if op.kind != "notification" or op.status not in {"failed", "needs_review"}:
        raise BusinessRuleViolation(
            "NOT_RETRYABLE", "Only failed notification deliveries can be retried here"
        )
    if op.status == "needs_review" and not data.acknowledge_duplicate_risk:
        raise BusinessRuleViolation(
            "REVIEW_REQUIRED",
            "Check the provider delivery history and acknowledge possible duplicate delivery",
        )
    op.status, op.attempts, op.next_attempt_at = "pending", 0, None
    await session.commit()
    await request.app.state.queue.enqueue(
        "deliver_integration_operation", str(op.id), job_id=f"operation-retry:{op.id}"
    )
    return workflows.operation_view(op)


@router.post("/integrations/connections/{connection_id}/activate-pi")
async def activate_pi(
    connection_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    result = await whatsapp_bridge.activate(
        session, request.app.state.settings, scope, connection_id
    )
    await session.commit()
    return result


@router.post("/billing/invoices/{invoice_id}/checkout")
async def checkout(
    invoice_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    return await business.checkout(
        session, request.app.state.settings, http(request), scope, invoice_id
    )


@router.post("/billing/invoices/{invoice_id}/email", status_code=202)
async def invoice_email(
    invoice_id: UUID, data: ActionInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    op = await business.email_invoice(session, scope, invoice_id, data.request_id)
    await session.commit()
    await request.app.state.queue.enqueue(
        "deliver_integration_operation", str(op.id), job_id=f"operation:{op.id}"
    )
    return workflows.operation_view(op)


@router.get("/files/records/{entity_type}/{entity_id}")
async def files(
    entity_type: str, entity_id: UUID, scope: Scope, session: Session
) -> list[dict[str, Any]]:
    await business.entity(session, scope, entity_type, entity_id)
    rows = await session.scalars(
        WorkspaceRepository(session, IntegrationOperation, scope)
        .select()
        .where(
            IntegrationOperation.kind == "file",
            IntegrationOperation.entity_type == entity_type,
            IntegrationOperation.entity_id == entity_id,
            IntegrationOperation.status != "cancelled",
        )
        .order_by(IntegrationOperation.created_at.desc())
        .limit(100)
    )
    return [workflows.operation_view(row) for row in rows]


@router.post("/files/records/{entity_type}/{entity_id}", status_code=201)
async def upload(
    entity_type: str,
    entity_id: UUID,
    request: Request,
    scope: Scope,
    session: Session,
    file: Annotated[UploadFile, File()],
    request_id: Annotated[UUID, Form()],
) -> dict[str, Any]:
    limit = min(request.app.state.settings.storage_max_upload_bytes, 25 * 1024**2)
    content = await file.read(limit + 1)
    return await business.upload_file(
        session,
        request.app.state.settings,
        http(request),
        scope,
        entity_type,
        entity_id,
        file.filename or "file",
        content,
        file.content_type or "application/octet-stream",
        request_id,
    )


@router.get("/files/{operation_id}/download")
async def download(
    operation_id: UUID, request: Request, scope: Scope, session: Session
) -> Response:
    op = await WorkspaceRepository(session, IntegrationOperation, scope).get(operation_id)
    if op.kind != "file" or op.status != "succeeded" or not op.entity_type or not op.entity_id:
        raise ResourceNotFound
    await business.entity(session, scope, op.entity_type, op.entity_id)
    connection = await business.connection_for(session, scope, ("s3",), op.connection_id)
    runtime = ConnectionRuntime(session, request.app.state.settings, http(request))
    content, _ = await runtime.call(
        connection, lambda ctx: S3Provider().download(ctx, op.output["key"]), kind="file_download"
    )
    await session.commit()
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(op.input["name"], safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/files/{operation_id}", status_code=204)
async def delete_file(
    operation_id: UUID, request: Request, scope: Scope, session: Session
) -> Response:
    op = await WorkspaceRepository(session, IntegrationOperation, scope).get(
        operation_id, for_update=True
    )
    if op.kind != "file" or not op.entity_type or not op.entity_id:
        raise ResourceNotFound
    await business.entity(session, scope, op.entity_type, op.entity_id, write=True)
    if op.status != "cancelled":
        connection = await business.connection_for(session, scope, ("s3",), op.connection_id)
        runtime = ConnectionRuntime(session, request.app.state.settings, http(request))
        key = op.output.get("key") or scoped_key(
            scope.tenant_id, scope.environment_id, f"attachments/{op.id}"
        )
        await runtime.call(
            connection, lambda ctx: S3Provider().delete(ctx, key), kind="file_delete"
        )
        op.status = "cancelled"
        await session.commit()
    return Response(status_code=204)


@router.get("/external/customers")
async def external_customers(
    scope: ApiKeyScope, session: Session, page: Annotated[Pagination, Depends()]
) -> Any:
    from app.modules.customers.service import CustomerService

    scope.require("customers.read")
    result = await CustomerService(session, scope).search(page)
    await session.commit()  # Persist last_used_at without changing scope.
    return result


@router.get("/external/invoices/{invoice_id}")
async def external_invoice(invoice_id: UUID, scope: ApiKeyScope, session: Session) -> Any:
    from app.modules.billing.service import BillingService

    scope.require("billing.read")
    result = await BillingService(session, scope).detail(invoice_id)
    await session.commit()
    return result
