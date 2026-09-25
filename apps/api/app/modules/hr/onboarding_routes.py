from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.core.pagination import Page, Pagination
from app.core.rate_limit import client_ip, hit
from app.modules.access.dependencies import Session, require
from app.modules.hr.onboarding import (
    Approval,
    LinkCreate,
    LinkCreated,
    OnboardingDetail,
    OnboardingService,
    OnboardingSubmission,
    OnboardingSummary,
    PublicForm,
    PublicOnboarding,
    Rejection,
)
from app.shared.errors import BusinessRuleViolation
from app.shared.scope import WorkspaceScope

router = APIRouter(prefix="/hr", tags=["hr"])
public_router = APIRouter(prefix="/public/onboarding", tags=["public"])
Write = Annotated[WorkspaceScope, Depends(require("hr.write"))]
Sensitive = Annotated[WorkspaceScope, Depends(require("hr.sensitive"))]
Paging = Annotated[Pagination, Depends()]
Token = Annotated[str, Path(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
StatusFilter = Literal["pending", "expired", "submitted", "approved", "rejected", "revoked"]


def service(request: Request, session: Session, scope: WorkspaceScope) -> OnboardingService:
    return OnboardingService(session, scope, request.app.state.settings)


@router.post("/onboarding", response_model=LinkCreated, status_code=status.HTTP_201_CREATED)
async def create_link(
    data: LinkCreate, request: Request, scope: Write, session: Session
) -> LinkCreated:
    created = await service(request, session, scope).create_link(data)
    await session.commit()
    return created


@router.get("/onboarding", response_model=Page[OnboardingSummary])
async def links(
    request: Request,
    scope: Write,
    session: Session,
    page: Paging,
    state: Annotated[StatusFilter | None, Query(alias="status")] = None,
) -> Page[OnboardingSummary]:
    return await service(request, session, scope).search(page, state)


@router.get("/onboarding/{onboarding_id}", response_model=OnboardingDetail)
async def link(
    onboarding_id: UUID, request: Request, scope: Write, session: Session
) -> OnboardingDetail:
    return await service(request, session, scope).detail(onboarding_id)


@router.post("/onboarding/{onboarding_id}/approve", response_model=OnboardingDetail)
async def approve(
    onboarding_id: UUID, data: Approval, request: Request, scope: Write, session: Session
) -> OnboardingDetail:
    result = await service(request, session, scope).approve(onboarding_id, data)
    await session.commit()
    return result


@router.post("/onboarding/{onboarding_id}/reject", response_model=OnboardingDetail)
async def reject(
    onboarding_id: UUID, data: Rejection, request: Request, scope: Write, session: Session
) -> OnboardingDetail:
    result = await service(request, session, scope).reject(onboarding_id, data)
    await session.commit()
    return result


@router.post("/onboarding/{onboarding_id}/revoke", response_model=OnboardingDetail)
async def revoke(
    onboarding_id: UUID, request: Request, scope: Write, session: Session
) -> OnboardingDetail:
    result = await service(request, session, scope).revoke(onboarding_id)
    await session.commit()
    return result


@router.get("/employees/{employee_id}/personal")
async def personal_details(
    employee_id: UUID, request: Request, scope: Sensitive, session: Session
) -> dict[str, Any]:
    return await service(request, session, scope).personal_details(employee_id)


async def _limit(request: Request, token: str, bucket: str, per_ip: int) -> None:
    ip = client_ip(request)
    if not await hit(request, f"onboarding-{bucket}", ip, per_ip, 3600) or not await hit(
        request, f"onboarding-{bucket}-token", token, per_ip, 3600
    ):
        raise BusinessRuleViolation("RATE_LIMITED", "Too many attempts. Try again later.", 429)


@public_router.get("/{token}", response_model=PublicForm)
async def public_form(token: Token, request: Request, session: Session) -> PublicForm:
    await _limit(request, token, "view", 120)
    return await PublicOnboarding(session, request.app.state.settings).form(token)


@public_router.post("/{token}", response_model=PublicForm)
async def public_submit(
    token: Token, data: OnboardingSubmission, request: Request, session: Session
) -> PublicForm:
    await _limit(request, token, "submit", 10)
    result = await PublicOnboarding(session, request.app.state.settings).submit(
        token, data, getattr(request.state, "request_id", None)
    )
    await session.commit()
    return result
