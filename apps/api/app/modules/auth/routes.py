from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_session
from app.core.rate_limit import client_ip, hit
from app.modules.access.service import membership_grants
from app.modules.auth.dependencies import Auth
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SessionView,
    UserView,
    WorkspaceRef,
    WorkspaceSelection,
)
from app.modules.auth.service import AuthContext, AuthService, IssuedSession
from app.modules.branches.models import Branch
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.tenants.context import active_memberships
from app.modules.tenants.models import Tenant
from app.shared.errors import BusinessRuleViolation, Unauthenticated

router = APIRouter(prefix="/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]


def set_cookies(response: Response, settings: Settings, issued: IssuedSession) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    # Readable by the web app only to echo in X-CSRF-Token; bound to the session server-side.
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


def clear_cookies(response: Response, settings: Settings) -> None:
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=settings.secure_cookies)


async def session_view(session: AsyncSession, context: AuthContext) -> SessionView:
    auth, user = context.session, context.user
    tenant = environment = branch = None
    permissions: frozenset[str] = frozenset()
    roles: list[str] = []
    if auth.active_tenant_id is not None:
        membership = await session.scalar(
            active_memberships(user.id).where(Membership.tenant_id == auth.active_tenant_id)
        )
        if membership is not None:
            row = await session.get(Tenant, auth.active_tenant_id)
            if row is not None:
                tenant = WorkspaceRef(id=row.id, name=row.name, key=row.slug)
            permissions, roles = await membership_grants(
                session, membership.tenant_id, membership.id
            )
            if auth.active_environment_id is not None:
                env = await session.scalar(
                    select(Environment).where(
                        Environment.tenant_id == membership.tenant_id,
                        Environment.id == auth.active_environment_id,
                        Environment.status == "active",
                    )
                )
                if env is not None:
                    environment = WorkspaceRef(id=env.id, name=env.name, key=env.key, kind=env.kind)
            if auth.active_branch_id is not None:
                b = await session.scalar(
                    select(Branch).where(
                        Branch.tenant_id == membership.tenant_id,
                        Branch.id == auth.active_branch_id,
                    )
                )
                if b is not None:
                    branch = WorkspaceRef(id=b.id, name=b.name, key=b.code)
    return SessionView(
        user=UserView.model_validate(user),
        tenant=tenant,
        environment=environment,
        branch=branch,
        permissions=sorted(permissions),
        roles=roles,
    )


@router.post("/register", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest, request: Request, response: Response, session: Session
) -> SessionView:
    settings = request.app.state.settings
    if not await hit(request, "register", client_ip(request), 5, 3600):
        raise HTTPException(status_code=429)
    service = AuthService(session, settings)
    issued = await service.register(data, request.headers.get("user-agent", ""))
    await session.commit()
    set_cookies(response, settings, issued)
    context = await service.resolve(issued.token)
    return await session_view(session, context)


@router.post("/login", response_model=SessionView)
async def login(
    data: LoginRequest, request: Request, response: Response, session: Session
) -> SessionView:
    settings = request.app.state.settings
    limit = settings.rate_limit_login_per_minute
    if not await hit(request, "login-ip", client_ip(request), limit, 60) or not await hit(
        request, "login-account", data.email, limit, 60
    ):
        raise HTTPException(status_code=429)
    service = AuthService(session, settings)
    try:
        issued = await service.login(
            data.email, data.password, request.headers.get("user-agent", "")
        )
    except Unauthenticated:
        await session.commit()  # persist failure counters, lockout and audit
        raise
    await session.commit()
    set_cookies(response, settings, issued)
    context = await service.resolve(issued.token)
    return await session_view(session, context)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, auth: Auth, session: Session) -> Response:
    await AuthService(session, request.app.state.settings).logout(auth.session)
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_cookies(response, request.app.state.settings)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(request: Request, auth: Auth, session: Session) -> Response:
    await AuthService(session, request.app.state.settings).logout_all(auth.user.id)
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_cookies(response, request.app.state.settings)
    return response


@router.get("/session", response_model=SessionView)
async def current(auth: Auth, session: Session) -> SessionView:
    return await session_view(session, auth)


@router.put("/session/workspace", response_model=SessionView)
async def select_workspace(
    data: WorkspaceSelection, request: Request, auth: Auth, session: Session
) -> SessionView:
    await AuthService(session, request.app.state.settings).select_workspace(
        auth.session, data.tenant_id, data.environment_id, data.branch_id
    )
    await session.commit()
    return await session_view(session, auth)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    data: ChangePasswordRequest, request: Request, auth: Auth, session: Session
) -> Response:
    try:
        await AuthService(session, request.app.state.settings).change_password(
            auth.session, data.current_password, data.new_password
        )
    except BusinessRuleViolation:
        await session.commit()  # persist only the failed-attempt audit record
        raise
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
