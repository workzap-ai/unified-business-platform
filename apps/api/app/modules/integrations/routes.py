"""HTTP API for docs/contracts/integrations-api.md (session + CSRF, tenant+environment)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.pagination import Page, Pagination
from app.integrations import oauth
from app.integrations.catalog import REGISTRY
from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Session, require
from app.modules.integrations.api_keys import ApiKeyService
from app.modules.integrations.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyView,
    ConnectionCreate,
    ConnectionDetail,
    ConnectionStatus,
    ConnectionUpdate,
    ConnectionView,
    CredentialsUpdate,
    DefinitionView,
    DeliveryView,
    EventStatus,
    EventTypeView,
    FailureView,
    HealthView,
    InboundEventView,
    JobStatus,
    OAuthStart,
    SyncJobView,
    SyncRequest,
    TestResult,
    WebhookCreate,
    WebhookCreated,
    WebhookUpdate,
    WebhookView,
)
from app.modules.integrations.service import IntegrationService, Runtime
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/integrations", tags=["integrations"])
Read = Annotated[WorkspaceScope, Depends(require("integrations.read"))]
Manage = Annotated[WorkspaceScope, Depends(require("integrations.manage"))]
Operate = Annotated[WorkspaceScope, Depends(require("integrations.operate"))]
Keys = Annotated[WorkspaceScope, Depends(require("api_keys.manage"))]
Paging = Annotated[Pagination, Depends()]
NO_CONTENT = status.HTTP_204_NO_CONTENT


def runtime(request: Request) -> Runtime:
    state = request.app.state
    return Runtime(
        settings=state.settings,
        http=OutboundClient(
            state.settings, state.http, resolver=getattr(state, "integration_resolver", None)
        ),
        queue=getattr(state, "queue", None),
        redis=getattr(state, "redis", None),
    )


Rt = Annotated[Runtime, Depends(runtime)]


def svc(session: Session, scope: WorkspaceScope, rt: Runtime) -> IntegrationService:
    return IntegrationService(session, scope, rt)


# --- directory ------------------------------------------------------------------------


@router.get("/definitions", response_model=list[DefinitionView])
async def definitions(scope: Read, session: Session, rt: Rt) -> list[DefinitionView]:
    return await svc(session, scope, rt).definitions()


@router.get("/event-types", response_model=list[EventTypeView])
async def event_types(scope: Read, session: Session, rt: Rt) -> list[EventTypeView]:
    return [EventTypeView(key=k, description=d) for k, d in svc(session, scope, rt).event_types()]


# --- connections ----------------------------------------------------------------------


@router.get("/connections", response_model=Page[ConnectionView])
async def connections(
    scope: Read,
    session: Session,
    rt: Rt,
    pagination: Paging,
    integration_key: Annotated[str | None, Query(pattern=r"^[a-z0-9_]{2,60}$")] = None,
    status_filter: Annotated[ConnectionStatus | None, Query(alias="status")] = None,
) -> Page[ConnectionView]:
    return await svc(session, scope, rt).list_connections(
        pagination, integration_key, status_filter
    )


@router.post("/connections", response_model=ConnectionView, status_code=201)
async def create_connection(
    data: ConnectionCreate, scope: Manage, session: Session, rt: Rt
) -> ConnectionView:
    service = svc(session, scope, rt)
    connection = await service.create(data)
    await session.commit()
    # Create-time test runs after the insert commits (no provider I/O inside that write).
    if data.credentials and service.can_test(connection):
        connection = await service.get(connection.id, for_update=True)
        await service.run_test(connection)
        await session.commit()
    return ConnectionView.model_validate(await service.get(connection.id))


@router.get("/connections/{connection_id}", response_model=ConnectionDetail)
async def connection_detail(
    connection_id: UUID, scope: Read, session: Session, rt: Rt
) -> ConnectionDetail:
    service = svc(session, scope, rt)
    return await service.detail(await service.get(connection_id))


@router.patch("/connections/{connection_id}", response_model=ConnectionDetail)
async def update_connection(
    connection_id: UUID, data: ConnectionUpdate, scope: Manage, session: Session, rt: Rt
) -> ConnectionDetail:
    service = svc(session, scope, rt)
    connection = await service.update(connection_id, data)
    await session.commit()
    return await service.detail(connection)


@router.put("/connections/{connection_id}/credentials", response_model=ConnectionDetail)
async def rotate_credentials(
    connection_id: UUID, data: CredentialsUpdate, scope: Manage, session: Session, rt: Rt
) -> ConnectionDetail:
    service = svc(session, scope, rt)
    connection = await service.rotate(connection_id, dict(data.credentials))
    await session.commit()
    if connection.status != "disabled" and service.can_test(connection):
        connection = await service.get(connection_id, for_update=True)
        await service.run_test(connection)
        await session.commit()
    return await service.detail(await service.get(connection_id))


@router.post("/connections/{connection_id}/test", response_model=TestResult)
async def test_connection(
    connection_id: UUID, scope: Operate, session: Session, rt: Rt
) -> TestResult:
    result = await svc(session, scope, rt).test(connection_id)
    await session.commit()
    return result


@router.post("/connections/{connection_id}/enable", response_model=ConnectionDetail)
async def enable_connection(
    connection_id: UUID, scope: Manage, session: Session, rt: Rt
) -> ConnectionDetail:
    service = svc(session, scope, rt)
    connection = await service.enable(connection_id)
    await session.commit()
    if connection.status == "connecting":
        connection = await service.get(connection_id, for_update=True)
        await service.run_test(connection)
        await session.commit()
    return await service.detail(await service.get(connection_id))


@router.post("/connections/{connection_id}/disable", response_model=ConnectionDetail)
async def disable_connection(
    connection_id: UUID, scope: Manage, session: Session, rt: Rt
) -> ConnectionDetail:
    service = svc(session, scope, rt)
    connection = await service.disable(connection_id)
    await session.commit()
    return await service.detail(connection)


@router.delete("/connections/{connection_id}", status_code=NO_CONTENT)
async def disconnect(connection_id: UUID, scope: Manage, session: Session, rt: Rt) -> Response:
    await svc(session, scope, rt).disconnect(connection_id)
    await session.commit()
    return Response(status_code=NO_CONTENT)


@router.post("/connections/{connection_id}/oauth/start", response_model=OAuthStart)
async def oauth_start(connection_id: UUID, scope: Manage, session: Session, rt: Rt) -> OAuthStart:
    url = await svc(session, scope, rt).oauth_start(connection_id)
    await session.commit()
    return OAuthStart(authorization_url=url)


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    scope: Manage,
    session: Session,
    rt: Rt,
    state: Annotated[str, Query(max_length=200)] = "",
    code: Annotated[str | None, Query(max_length=2048)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> RedirectResponse:
    try:
        result = await oauth.callback(
            session,
            rt.settings,
            rt.http,
            REGISTRY.definition,
            state=state,
            code=code,
            error=error,
            user_id=scope.user_id,
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
        )
    except oauth.OAuthStateInvalid:
        await session.commit()  # consumed/expired states stay consumed
        return RedirectResponse("/settings/integrations?oauth=error", status_code=302)
    from app.modules.audit.service import record

    await record(
        session,
        "integration.oauth.completed",
        scope=scope,
        entity_type="integration_connection",
        entity_id=result.connection_id,
        outcome="success" if result.ok else "failure",
    )
    await session.commit()
    outcome = "ok" if result.ok else "error"
    return RedirectResponse(
        f"/settings/integrations/connections/{result.connection_id}?oauth={outcome}",
        status_code=302,
    )


# --- outbound webhooks ----------------------------------------------------------------


@router.get("/webhooks", response_model=Page[WebhookView])
async def webhooks(scope: Read, session: Session, rt: Rt, pagination: Paging) -> Page[WebhookView]:
    return await svc(session, scope, rt).list_webhooks(pagination)


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
async def create_webhook(
    data: WebhookCreate, scope: Manage, session: Session, rt: Rt
) -> WebhookCreated:
    result = await svc(session, scope, rt).create_webhook(data)
    await session.commit()
    return result


@router.patch("/webhooks/{subscription_id}", response_model=WebhookView)
async def update_webhook(
    subscription_id: UUID, data: WebhookUpdate, scope: Manage, session: Session, rt: Rt
) -> WebhookView:
    result = await svc(session, scope, rt).update_webhook(subscription_id, data)
    await session.commit()
    return result


@router.post("/webhooks/{subscription_id}/rotate-secret", response_model=WebhookCreated)
async def rotate_webhook_secret(
    subscription_id: UUID, scope: Manage, session: Session, rt: Rt
) -> WebhookCreated:
    result = await svc(session, scope, rt).rotate_webhook_secret(subscription_id)
    await session.commit()
    return result


@router.delete("/webhooks/{subscription_id}", status_code=NO_CONTENT)
async def delete_webhook(
    subscription_id: UUID, scope: Manage, session: Session, rt: Rt
) -> Response:
    await svc(session, scope, rt).delete_webhook(subscription_id)
    await session.commit()
    return Response(status_code=NO_CONTENT)


@router.get("/webhooks/{subscription_id}/deliveries", response_model=Page[DeliveryView])
async def deliveries(
    subscription_id: UUID, scope: Read, session: Session, rt: Rt, pagination: Paging
) -> Page[DeliveryView]:
    return await svc(session, scope, rt).list_deliveries(subscription_id, pagination)


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryView)
async def retry_delivery(
    delivery_id: UUID, scope: Operate, session: Session, rt: Rt
) -> DeliveryView:
    service = svc(session, scope, rt)
    result = await service.retry_delivery(delivery_id)
    await session.commit()
    await service.flush_jobs()
    return result


# --- inbound events ---------------------------------------------------------------------


@router.get("/events", response_model=Page[InboundEventView])
async def events(
    scope: Read,
    session: Session,
    rt: Rt,
    pagination: Paging,
    connection_id: UUID | None = None,
    status_filter: Annotated[EventStatus | None, Query(alias="status")] = None,
    event_type: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[InboundEventView]:
    return await svc(session, scope, rt).list_events(
        pagination, connection_id, status_filter, event_type
    )


@router.post("/events/{event_id}/replay", response_model=InboundEventView)
async def replay_event(
    event_id: UUID, scope: Operate, session: Session, rt: Rt
) -> InboundEventView:
    service = svc(session, scope, rt)
    result = await service.replay_event(event_id)
    await session.commit()
    await service.flush_jobs()
    return result


# --- sync jobs ----------------------------------------------------------------------------


@router.get("/jobs", response_model=Page[SyncJobView])
async def jobs(
    scope: Read,
    session: Session,
    rt: Rt,
    pagination: Paging,
    connection_id: UUID | None = None,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
) -> Page[SyncJobView]:
    return await svc(session, scope, rt).list_jobs(pagination, connection_id, status_filter)


@router.post("/connections/{connection_id}/sync", response_model=SyncJobView, status_code=201)
async def start_sync(
    connection_id: UUID, data: SyncRequest, scope: Operate, session: Session, rt: Rt
) -> SyncJobView:
    service = svc(session, scope, rt)
    result = await service.start_sync(connection_id, data)
    await session.commit()
    await service.flush_jobs()
    return result


async def _control(
    job_id: UUID, action: str, scope: WorkspaceScope, session: Session, rt: Runtime
) -> SyncJobView:
    service = svc(session, scope, rt)
    result = await service.control_job(job_id, action)
    await session.commit()
    await service.flush_jobs()
    return result


@router.post("/jobs/{job_id}/pause", response_model=SyncJobView)
async def pause_job(job_id: UUID, scope: Operate, session: Session, rt: Rt) -> SyncJobView:
    return await _control(job_id, "pause", scope, session, rt)


@router.post("/jobs/{job_id}/resume", response_model=SyncJobView)
async def resume_job(job_id: UUID, scope: Operate, session: Session, rt: Rt) -> SyncJobView:
    return await _control(job_id, "resume", scope, session, rt)


@router.post("/jobs/{job_id}/cancel", response_model=SyncJobView)
async def cancel_job(job_id: UUID, scope: Operate, session: Session, rt: Rt) -> SyncJobView:
    return await _control(job_id, "cancel", scope, session, rt)


@router.post("/jobs/{job_id}/retry", response_model=SyncJobView)
async def retry_job(job_id: UUID, scope: Operate, session: Session, rt: Rt) -> SyncJobView:
    return await _control(job_id, "retry", scope, session, rt)


# --- failures + health ------------------------------------------------------------------


@router.get("/failures", response_model=Page[FailureView])
async def failures(scope: Read, session: Session, rt: Rt, pagination: Paging) -> Page[FailureView]:
    return await svc(session, scope, rt).failures(pagination)


@router.get("/health", response_model=HealthView)
async def health(scope: Read, session: Session, rt: Rt) -> HealthView:
    return await svc(session, scope, rt).health()


# --- API keys -------------------------------------------------------------------------


@router.get("/api-keys", response_model=list[ApiKeyView])
async def api_keys(scope: Keys, session: Session) -> list[ApiKeyView]:
    return await ApiKeyService(session, scope).list()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    data: ApiKeyCreate, scope: Keys, session: Session, request: Request
) -> ApiKeyCreated:
    service = ApiKeyService(session, scope, request.app.state.settings.api_key_max_per_environment)
    result = await service.create(data)
    await session.commit()
    return result


@router.delete("/api-keys/{key_id}", status_code=NO_CONTENT)
async def revoke_api_key(key_id: UUID, scope: Keys, session: Session) -> Response:
    await ApiKeyService(session, scope).revoke(key_id)
    await session.commit()
    return Response(status_code=NO_CONTENT)
