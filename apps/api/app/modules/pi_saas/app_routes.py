"""Customer-facing API for the standalone Pi app, mounted under /api/v1/pi-app.

Routes under this prefix accept only Pi app sessions (own cookies and origins); Owner OS
sessions are rejected, and Pi sessions are rejected everywhere else. The shared PI
inbox/knowledge/settings routers are mounted under the same prefix so both editions use
one implementation. Customers never see tenant, environment or provider identifiers.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.rate_limit import client_ip, hit
from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Scope
from app.modules.access.members import MemberService
from app.modules.access.models import Role
from app.modules.access.permissions import PERMISSIONS, SYSTEM_ROLES
from app.modules.access.schemas import MemberCreate
from app.modules.access.service import membership_grants
from app.modules.audit.service import record
from app.modules.auth.crypto import hash_password
from app.modules.auth.dependencies import Auth
from app.modules.auth.models import UserCredential
from app.modules.auth.schemas import (
    AcceptInviteRequest,
    ForgotPasswordRequest,
    Password,
    ResetPasswordRequest,
    VerifyEmailRequest,
    normalize_email,
)
from app.modules.auth.service import AuthService, IssuedSession, pi_business_tenants
from app.modules.business_settings.models import BusinessSettings
from app.modules.memberships.models import Membership
from app.modules.pi.models import PiAgentRun, PiConversation, PiHandoff, PiMessage
from app.modules.pi.service import ACTIVE_HANDOFF, PiService
from app.modules.pi_saas import billing, connections, onboarding, teach
from app.modules.pi_saas.entitlement import entitlement, month, storage_used_mb, usage_for
from app.modules.pi_saas.models import (
    PiKnowledgeDraft,
    PiPlan,
    PiPlatformInvoice,
    PiProviderConnection,
    PiStaffRequest,
    PiSubscription,
    PiSupportGrant,
)
from app.modules.pi_saas.playground import PlaygroundInput, preview
from app.modules.pi_saas.provisioning import provision_business
from app.modules.tenants.context import active_memberships
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, Unauthenticated
from app.shared.scope import WorkspaceScope
from app.shared.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/pi-app", tags=["pi-app"])
Session = Annotated[AsyncSession, Depends(get_session)]

CLIENT_ROLES: dict[str, tuple[str, str]] = {
    "owner": ("Business owner", "Everything, including billing and removing the business"),
    "admin": ("Admin", "Runs Pi, the team and settings"),
    "manager": ("Manager", "Sees every conversation and assigns work"),
    "member": ("Sales/Support member", "Handles conversations assigned to them"),
    "viewer": ("Viewer", "Can look, but not change anything"),
    "billing": ("Billing", "Plan, usage and invoices only"),
}


# ------------------------------------------------------------------------------ auth


class PiRegister(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    password: Password
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    business_name: Annotated[str, StringConstraints(min_length=2, max_length=160)]
    offer_type: Literal["services", "products", "both"] = "services"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def _strength(cls, value: str) -> str:
        if len(set(value)) < 5:
            raise ValueError("Password is too simple")
        return value


class PiLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return normalize_email(value)


class BusinessSelect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_id: UUID
    environment: Literal["production", "test"] = "production"


class NewBusiness(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Annotated[str, StringConstraints(min_length=2, max_length=160)]
    offer_type: Literal["services", "products", "both"] = "services"


def _set_cookies(response: Response, request: Request, issued: IssuedSession) -> None:
    settings = request.app.state.settings
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.pi_session_cookie_name,
        issued.token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.pi_csrf_cookie_name,
        issued.csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
        path="/",
    )


def _clear_cookies(response: Response, request: Request) -> None:
    settings = request.app.state.settings
    for name in (settings.pi_session_cookie_name, settings.pi_csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=settings.secure_cookies)


async def _session_view(
    session: AsyncSession, auth_session: Any, user: PlatformUser
) -> dict[str, Any]:
    businesses = []
    memberships = await session.execute(
        active_memberships(user.id)
        .where(Membership.tenant_id.in_(pi_business_tenants()))
        .with_only_columns(Membership.id, Membership.tenant_id)
    )
    for _membership_id, tenant_id in memberships:
        tenant = await session.get(Tenant, tenant_id)
        businesses.append({"id": tenant_id, "name": tenant.name if tenant else ""})
    current = None
    permissions: frozenset[str] = frozenset()
    roles: list[str] = []
    if auth_session.active_tenant_id in {b["id"] for b in businesses}:
        account = await onboarding.current_account(session, auth_session.active_tenant_id)
        membership = await session.scalar(
            active_memberships(user.id).where(Membership.tenant_id == account.tenant_id)
        )
        if membership is not None:
            permissions, roles = await membership_grants(session, account.tenant_id, membership.id)
        current = {
            "id": account.tenant_id,
            "name": account.name,
            "setup_state": account.setup_state,
            "onboarding_step": account.onboarding_step,
            "environment": "test"
            if auth_session.active_environment_id == account.test_environment_id
            else "production",
        }
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "email_verified": user.email_verified,
        },
        "business": current,
        "businesses": sorted(businesses, key=lambda b: b["name"].lower()),
        "permissions": sorted(permissions),
        "roles": [r for r in roles if r in CLIENT_ROLES] or roles,
    }


@router.post("/auth/register", status_code=201)
async def register(
    data: PiRegister, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    settings = request.app.state.settings
    if not settings.pi_allow_registration:
        raise BusinessRuleViolation("REGISTRATION_DISABLED", "Sign-up is not open yet")
    if not await hit(request, "pi-register", client_ip(request), 5, 3600):
        raise HTTPException(status_code=429)
    existing = await session.scalar(select(PlatformUser.id).where(PlatformUser.email == data.email))
    if existing is not None:
        # Same response for existing accounts: sign in and add a business instead.
        raise Conflict("Sign-up could not be completed. If you have an account, sign in.")
    user = PlatformUser(email=data.email, display_name=data.display_name)
    session.add(user)
    await session.flush()
    session.add(
        UserCredential(
            user_id=user.id,
            password_hash=hash_password(data.password),
            password_changed_at=datetime.now(UTC),
        )
    )
    await provision_business(
        session,
        settings,
        user,
        data.business_name,
        offer_type=data.offer_type,
        request_id=getattr(request.state, "request_id", None),
    )
    service = AuthService(session, settings)
    issued = await service._issue(user, request.headers.get("user-agent", ""), "pi")
    await record(session, "auth.registered", actor_user_id=user.id, details={"audience": "pi"})
    http = OutboundClient(settings, request.app.state.http)
    await service.start_email_verification(user, http, "pi")
    await session.commit()
    _set_cookies(response, request, issued)
    return await _session_view(session, issued.record, user)


@router.post("/auth/accept-invite", status_code=201)
async def accept_invite(
    data: AcceptInviteRequest, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    settings = request.app.state.settings
    if not await hit(request, "pi-accept-invite", client_ip(request), 20, 3600):
        raise HTTPException(status_code=429)
    service = AuthService(session, settings)
    issued = await service.accept_invite(
        data.token, data.new_password, request.headers.get("user-agent", ""), "pi"
    )
    await session.commit()
    _set_cookies(response, request, issued)
    context = await service.resolve(issued.token, "pi")
    return await _session_view(session, context.session, context.user)


@router.post("/auth/login")
async def login(
    data: PiLogin, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    settings = request.app.state.settings
    limit = settings.rate_limit_login_per_minute
    if not await hit(request, "login-ip", client_ip(request), limit, 60) or not await hit(
        request, "login-account", data.email, limit, 60
    ):
        raise HTTPException(status_code=429)
    service = AuthService(session, settings)
    try:
        issued = await service.login(
            data.email, data.password, request.headers.get("user-agent", ""), "pi"
        )
    except Unauthenticated:
        await session.commit()
        raise
    await session.commit()
    _set_cookies(response, request, issued)
    context = await service.resolve(issued.token, "pi")
    return await _session_view(session, context.session, context.user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, auth: Auth, session: Session) -> Response:
    await AuthService(session, request.app.state.settings).logout(auth.session)
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_cookies(response, request)
    return response


@router.get("/auth/session")
async def current_session(auth: Auth, session: Session) -> dict[str, Any]:
    return await _session_view(session, auth.session, auth.user)


@router.post("/auth/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(data: VerifyEmailRequest, request: Request, session: Session) -> Response:
    settings = request.app.state.settings
    if not await hit(request, "pi-verify-email", client_ip(request), 20, 3600):
        raise HTTPException(status_code=429)
    await AuthService(session, settings).verify_email(data.token)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(request: Request, auth: Auth, session: Session) -> Response:
    settings = request.app.state.settings
    limit = settings.rate_limit_email_verification_per_hour
    if not await hit(request, "pi-resend-verification", str(auth.user.id), limit, 3600):
        raise HTTPException(status_code=429)
    http = OutboundClient(settings, request.app.state.http)
    await AuthService(session, settings).resend_verification(auth.user, http, "pi")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    data: ForgotPasswordRequest, request: Request, session: Session
) -> Response:
    settings = request.app.state.settings
    limit = settings.rate_limit_password_reset_per_hour
    if not await hit(
        request, "pi-forgot-password-ip", client_ip(request), limit, 3600
    ) or not await hit(request, "pi-forgot-password-account", data.email, limit, 3600):
        raise HTTPException(status_code=429)
    http = OutboundClient(settings, request.app.state.http)
    await AuthService(session, settings).request_password_reset(data.email, http, "pi")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    data: ResetPasswordRequest, request: Request, session: Session
) -> Response:
    settings = request.app.state.settings
    if not await hit(request, "pi-reset-password", client_ip(request), 20, 3600):
        raise HTTPException(status_code=429)
    await AuthService(session, settings).reset_password(data.token, data.new_password)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/auth/business")
async def select_business(
    data: BusinessSelect, request: Request, auth: Auth, session: Session
) -> dict[str, Any]:
    account = await onboarding.current_account(session, data.business_id)
    environment_id = (
        account.test_environment_id
        if data.environment == "test"
        else account.production_environment_id
    )
    await AuthService(session, request.app.state.settings).select_workspace(
        auth.session, account.tenant_id, environment_id, None
    )
    await session.commit()
    return await _session_view(session, auth.session, auth.user)


@router.post("/businesses", status_code=201)
async def add_business(
    data: NewBusiness, request: Request, auth: Auth, session: Session
) -> dict[str, Any]:
    """Another, fully separate business for the same person (no shared customers)."""
    if not await hit(request, "pi-business-create", str(auth.user.id), 5, 3600):
        raise HTTPException(status_code=429)
    account = await provision_business(
        session,
        request.app.state.settings,
        auth.user,
        data.name,
        offer_type=data.offer_type,
        request_id=getattr(request.state, "request_id", None),
    )
    await AuthService(session, request.app.state.settings).select_workspace(
        auth.session, account.tenant_id, account.production_environment_id, None
    )
    await session.commit()
    return await _session_view(session, auth.session, auth.user)


# --------------------------------------------------------------------------- account


async def _account(session: AsyncSession, scope: WorkspaceScope) -> Any:
    return await onboarding.current_account(session, scope.tenant_id)


def _connection_view(row: PiProviderConnection | None) -> dict[str, Any]:
    if row is None:
        return {"status": "draft"}
    request = row.number_request or {}
    return {
        "status": row.status,
        "display_phone_number": row.display_phone_number,
        "connection_type": row.connection_type,
        "setup_url": row.setup_link_url if row.status == "setup_pending" else None,
        "setup_expires_at": row.setup_expires_at,
        "health": row.health or None,
        "health_checked_at": row.health_checked_at,
        "problem": row.last_error_code,
        "number_request": {
            "status": request.get("status"),
            "country": request.get("country"),
            "quote": request.get("quote"),
        }
        if request
        else None,
    }


@router.get("/account")
async def account(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    row = await _account(session, scope)
    await onboarding.refresh_state(session, scope, row)
    await session.commit()
    return {
        "name": row.name,
        "business_category": row.business_category,
        "language": row.language,
        "timezone": row.timezone,
        "country": row.country,
        "website": row.website,
        "description": row.description,
        "offer_type": row.offer_type,
        "currency": await session.scalar(
            select(BusinessSettings.default_currency).where(
                BusinessSettings.tenant_id == row.tenant_id,
                BusinessSettings.environment_id == row.production_environment_id,
            )
        ),
        "goals": row.goals,
        "automation_mode": row.automation_mode,
        "price_disclosure": row.onboarding_data.get("price_disclosure", "quote"),
        "tools": row.onboarding_data.get("tools", []),
        "whatsapp_choice": row.onboarding_data.get("whatsapp_choice"),
        "setup_state": row.setup_state,
        "onboarding_step": row.onboarding_step,
        "completed_steps": sorted(int(k) for k in row.onboarding_data.get("done", {})),
        "help_requested_at": row.help_requested_at,
        "launched_at": row.launched_at,
        "paused_reason": row.paused_reason,
        "readiness": await onboarding.readiness(session, row),
        "whatsapp": _connection_view(await onboarding.production_connection(session, row)),
        "tool_groups": list(onboarding.TOOL_GROUPS),
        "goals_available": list(onboarding.GOALS),
    }


STEP_MODELS: dict[int, type[BaseModel]] = {
    1: onboarding.BusinessStep,
    2: onboarding.OfferStep,
    3: onboarding.WhatsAppStep,
    4: onboarding.HelpStep,
}


@router.put("/account/onboarding/{step}")
async def save_step(step: int, request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    model = STEP_MODELS.get(step)
    if model is None:
        raise BusinessRuleViolation("INVALID_STEP", "Unknown setup step", 404)
    try:
        data = model.model_validate(await request.json())
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    row = await _account(session, scope)
    await onboarding.save_step(session, scope, row, step, data)
    await session.commit()
    return await account(scope, session)


class PauseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(default="", max_length=200)


@router.post("/account/launch")
async def launch(scope: Scope, session: Session) -> dict[str, Any]:
    row = await _account(session, scope)
    await onboarding.launch(session, scope, row)
    await session.commit()
    return await account(scope, session)


@router.post("/account/pause")
async def pause(data: PauseInput, scope: Scope, session: Session) -> dict[str, Any]:
    row = await _account(session, scope)
    await onboarding.pause(session, scope, row, data.reason)
    await session.commit()
    return await account(scope, session)


class HelpInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=500)
    days: int = Field(default=14, ge=1, le=30)


@router.post("/account/help")
async def request_help(data: HelpInput, scope: Scope, session: Session) -> dict[str, Any]:
    """ "Help me set up": lets our team prepare configuration (never your WhatsApp or
    payment authorization) for a limited time. You can revoke it at any moment."""
    scope.require("pi.support.grant")
    row = await _account(session, scope)
    row.help_requested_at = datetime.now(UTC)
    session.add(
        PiSupportGrant(
            tenant_id=row.tenant_id,
            scope="configuration",
            status="active",
            reason=data.note or "Help me set up",
            requested_by="client",
            approved_by_user_id=scope.user_id,
            expires_at=datetime.now(UTC) + timedelta(days=data.days),
        )
    )
    await record(
        session,
        "pi_saas.help_requested",
        scope=scope,
        entity_type="pi_business_account",
        entity_id=row.id,
    )
    await session.commit()
    return await support_access(scope, session)


@router.get("/account/support-access")
async def support_access(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    rows = await session.scalars(
        select(PiSupportGrant)
        .where(PiSupportGrant.tenant_id == scope.tenant_id)
        .order_by(PiSupportGrant.created_at.desc())
        .limit(50)
    )
    now = datetime.now(UTC)
    return {
        "grants": [
            {
                "id": g.id,
                "scope": g.scope,
                "status": "expired"
                if g.status == "active" and g.expires_at and g.expires_at <= now
                else g.status,
                "reason": g.reason,
                "requested_by": g.requested_by,
                "expires_at": g.expires_at,
                "created_at": g.created_at,
            }
            for g in rows
        ]
    }


@router.post("/account/support-access/{grant_id}/{action}")
async def decide_support_access(
    grant_id: UUID,
    action: Literal["approve", "decline", "revoke"],
    scope: Scope,
    session: Session,
) -> dict[str, Any]:
    scope.require("pi.support.grant")
    grant = await session.scalar(
        select(PiSupportGrant)
        .where(PiSupportGrant.tenant_id == scope.tenant_id, PiSupportGrant.id == grant_id)
        .with_for_update()
    )
    if grant is None:
        from app.shared.errors import ResourceNotFound

        raise ResourceNotFound
    if action == "approve":
        if grant.status != "requested":
            raise BusinessRuleViolation("GRANT_CLOSED", "This request was already handled", 409)
        grant.status, grant.approved_by_user_id = "active", scope.user_id
        grant.expires_at = grant.expires_at or datetime.now(UTC) + timedelta(days=7)
    elif action == "decline":
        if grant.status == "requested":
            grant.status = "declined"
    elif grant.status == "active":
        grant.status, grant.revoked_at = "revoked", datetime.now(UTC)
    await record(
        session,
        f"pi_saas.support_access_{action}",
        scope=scope,
        entity_type="pi_support_grant",
        entity_id=grant.id,
        details={"scope": grant.scope},
    )
    await session.commit()
    return await support_access(scope, session)


# -------------------------------------------------------------------------- whatsapp


@router.get("/whatsapp")
async def whatsapp(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.read")
    row = await _account(session, scope)
    views = {}
    for environment in ("production", "test"):
        environment_id = (
            row.test_environment_id if environment == "test" else row.production_environment_id
        )
        connection = await session.scalar(
            select(PiProviderConnection).where(
                PiProviderConnection.tenant_id == row.tenant_id,
                PiProviderConnection.environment_id == environment_id,
            )
        )
        views[environment] = _connection_view(connection)
    settings = request.app.state.settings
    return {
        **views,
        # Honest availability: without a configured provider key setup cannot start.
        "provider_available": settings.kapso_api_key is not None,
        "new_number_countries": settings.kapso_setup_countries,
    }


@router.post("/whatsapp/setup")
async def whatsapp_setup(
    data: connections.SetupRequest, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    row = await _account(session, scope)
    connection = await connections.start_setup(
        session, request.app.state.settings, request.app.state.http, scope, row, data
    )
    await session.commit()
    return _connection_view(connection)


@router.post("/whatsapp/confirm")
async def whatsapp_confirm(
    data: connections.ConfirmRequest, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """After the setup page redirects back. The redirect's number is only a hint: the
    provider API is asked which numbers this business actually authorized."""
    scope.require("pi.whatsapp.manage")
    row = await _account(session, scope)
    connection = await connections.confirm_setup(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        row,
        data.environment,
        data.phone_number_id,
    )
    await session.commit()
    return _connection_view(connection)


@router.post("/whatsapp/number-request")
async def number_request(
    data: connections.NumberRequest, scope: Scope, session: Session
) -> dict[str, Any]:
    row = await _account(session, scope)
    connection = await connections.request_number(session, scope, row, data)
    await session.commit()
    return _connection_view(connection)


class EnvironmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["production", "test"] = "production"


@router.post("/whatsapp/number-request/confirm")
async def confirm_number_quote(
    data: EnvironmentInput, scope: Scope, session: Session
) -> dict[str, Any]:
    row = await _account(session, scope)
    connection = await connections.confirm_number_quote(session, scope, row, data.environment)
    await session.commit()
    return _connection_view(connection)


@router.post("/whatsapp/health")
async def whatsapp_health(
    data: EnvironmentInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("pi.read")
    row = await _account(session, scope)
    connection = await connections.check_health(
        session, request.app.state.settings, request.app.state.http, row, data.environment
    )
    await session.commit()
    return _connection_view(connection)


class DisconnectInput(EnvironmentInput):
    remove_from_provider: bool = False


@router.post("/whatsapp/disconnect")
async def whatsapp_disconnect(
    data: DisconnectInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    row = await _account(session, scope)
    connection = await connections.disconnect(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        row,
        data.environment,
        data.remove_from_provider,
    )
    await session.commit()
    return _connection_view(connection)


@router.get("/whatsapp/numbers")
async def whatsapp_numbers(
    scope: Scope, session: Session, environment: Literal["production", "test"] = "production"
) -> list[dict[str, Any]]:
    """Numbers from the platform pool this business can choose (or was offered)."""
    from app.modules.pi_saas import number_pool

    scope.require("pi.whatsapp.manage")
    row = await _account(session, scope)
    target = connections.pi_target(row, environment)
    return [
        {**number_pool.view(n), "offered_to_you": n.status == "reserved"}
        for n in await number_pool.available(session, target)
    ]


@router.post("/whatsapp/numbers/{pool_id}/choose")
async def choose_whatsapp_number(
    pool_id: UUID, data: EnvironmentInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Connects the number now, or holds it until the business is approved and paid."""
    from app.modules.pi_saas import number_pool

    row = await _account(session, scope)
    result = await number_pool.pick(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        connections.pi_target(row, data.environment),
        pool_id,
    )
    await session.commit()
    if result["state"] == "connected":
        return {**_connection_view(result["connection"]), "state": "connected"}
    return {"status": "held", "state": "held", "number": result["number"], "gate": result["gate"]}


@router.delete("/whatsapp/numbers/hold")
async def release_whatsapp_hold(
    scope: Scope, session: Session, environment: Literal["production", "test"] = "production"
) -> dict[str, Any]:
    from app.modules.pi_saas import number_pool

    row = await _account(session, scope)
    await number_pool.release_hold(session, scope, connections.pi_target(row, environment))
    await session.commit()
    return {"released": True}


@router.get("/whatsapp/access")
async def whatsapp_access(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    """What still stands between this business and a connected WhatsApp number."""
    from app.modules.pi_saas.access_gate import whatsapp_gate
    from app.modules.pi_saas.models import PiPoolNumber

    scope.require("pi.read")
    gate = await whatsapp_gate(session, request.app.state.settings, scope.tenant_id)
    held = await session.scalar(
        select(PiPoolNumber).where(
            PiPoolNumber.status == "reserved",
            PiPoolNumber.assigned_tenant_id == scope.tenant_id,
            PiPoolNumber.held_until.is_not(None),
        )
    )
    return {
        **gate.view(),
        "held": (
            {"display_phone_number": held.display_phone_number, "held_until": held.held_until}
            if held is not None
            else None
        ),
    }


# --------------------------------------------------------------------------- billing


def _plan_view(plan: PiPlan, online: bool) -> dict[str, Any]:
    return {
        "key": plan.key,
        "name": plan.name,
        "description": plan.description,
        "monthly_price": str(plan.monthly_price) if plan.monthly_price is not None else None,
        "currency": plan.currency,
        "trial_days": plan.trial_days,
        "allowances": plan.allowances,
        "features": plan.features,
        "purchasable": online and plan.monthly_price is not None and bool(plan.stripe_price_id),
        "manual_monthly_price_pkr": str(plan.manual_monthly_price_pkr)
        if plan.manual_monthly_price_pkr is not None
        else None,
    }


@router.get("/plans")
async def public_plans(request: Request, session: Session) -> list[dict[str, Any]]:
    """Public plan list for the pricing page. No prices are invented: a plan without an
    operator-set price is shown as "price on request"."""
    online = bool(
        request.app.state.settings.pi_billing_stripe_secret_key
        and request.app.state.settings.pi_billing_stripe_webhook_secret
    )
    rows = await session.scalars(
        select(PiPlan)
        .where(PiPlan.status == "available", PiPlan.visibility == "public")
        .order_by(PiPlan.sort_order)
    )
    return [_plan_view(p, online) for p in rows]


@router.get("/billing")
async def billing_view(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("pi.billing.read")
    row = await _account(session, scope)
    subscription = await session.scalar(
        select(PiSubscription).where(PiSubscription.tenant_id == row.tenant_id)
    )
    online = bool(
        request.app.state.settings.pi_billing_stripe_secret_key
        and request.app.state.settings.pi_billing_stripe_webhook_secret
    )
    plans = list(
        await session.scalars(
            select(PiPlan)
            .where(
                PiPlan.status == "available",
                (PiPlan.visibility == "public")
                | (PiPlan.key == (subscription.plan_key if subscription else "")),
            )
            .order_by(PiPlan.sort_order)
        )
    )
    plan = next((p for p in plans if subscription and p.key == subscription.plan_key), None)
    usage = await usage_for(session, row.tenant_id, row.production_environment_id)
    test_usage = await usage_for(session, row.tenant_id, row.test_environment_id)
    seats = await session.scalar(
        select(func.count()).select_from(active_memberships_for(row.tenant_id).subquery())
    )
    invoices = await session.scalars(
        select(PiPlatformInvoice)
        .where(PiPlatformInvoice.tenant_id == row.tenant_id)
        .order_by(PiPlatformInvoice.created_at.desc())
        .limit(24)
    )
    current = await entitlement(session, row.tenant_id, row.production_environment_id)
    return {
        "subscription": {
            "plan": subscription.plan_key if subscription else None,
            "status": subscription.status if subscription else None,
            "entitled": current.sending,
            "reason": current.reason,
            "trial_ends_at": subscription.trial_ends_at if subscription else None,
            "current_period_end": subscription.current_period_end if subscription else None,
            "grace_ends_at": subscription.grace_ends_at if subscription else None,
            "cancel_at_period_end": subscription.cancel_at_period_end if subscription else False,
            "spend_limit": str(subscription.spend_limit)
            if subscription and subscription.spend_limit is not None
            else None,
            "managed_online": bool(subscription and subscription.external_customer_id),
            "billing_provider": subscription.billing_provider if subscription else None,
        },
        "plan": _plan_view(plan, online) if plan else None,
        "plans": [_plan_view(p, online) for p in plans],
        "usage": {
            "period": month().isoformat(),
            "messages_sent": str(usage.get("messages_out", Decimal(0))),
            "messages_received": str(usage.get("messages_in", Decimal(0))),
            "ai_tokens": str(usage.get("ai_tokens", Decimal(0))),
            "ai_cost": str(usage.get("ai_cost", Decimal(0))),
            "media_items": str(usage.get("media_items", Decimal(0))),
            "seats": int(seats or 0),
            "storage_mb": str(await storage_used_mb(session, row.tenant_id)),
            "test_messages_sent": str(test_usage.get("messages_out", Decimal(0))),
        },
        "invoices": [
            {
                "number": i.number,
                "status": i.status,
                "amount_due": str(i.amount_due),
                "amount_paid": str(i.amount_paid),
                "currency": i.currency,
                "period_start": i.period_start,
                "period_end": i.period_end,
                "url": i.hosted_url,
            }
            for i in invoices
        ],
        "online_checkout": online,
    }


def active_memberships_for(tenant_id: UUID) -> Any:
    return select(Membership.id).where(
        Membership.tenant_id == tenant_id, Membership.status == "active"
    )


class PlanChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern=r"^[a-z0-9_-]{1,32}$")


@router.post("/billing/checkout")
async def billing_checkout(
    data: PlanChoice, request: Request, auth: Auth, scope: Scope, session: Session
) -> dict[str, str]:
    row = await _account(session, scope)
    if scope.environment_id != row.production_environment_id:
        raise BusinessRuleViolation(
            "TEST_BILLING_DISABLED", "Checkout is unavailable in the test workspace", 409
        )
    url = await billing.checkout(
        session,
        request.app.state.settings,
        request.app.state.http,
        scope,
        row,
        data.plan,
        auth.user.email,
    )
    await session.commit()
    return {"url": url}


@router.post("/billing/portal")
async def billing_portal(request: Request, scope: Scope, session: Session) -> dict[str, str]:
    row = await _account(session, scope)
    return {
        "url": await billing.portal(
            session, request.app.state.settings, request.app.state.http, scope, row
        )
    }


@router.post("/billing/cancel")
async def billing_cancel(request: Request, scope: Scope, session: Session) -> dict[str, Any]:
    row = await _account(session, scope)
    await billing.cancel(session, request.app.state.settings, request.app.state.http, scope, row)
    await session.commit()
    return await billing_view(request, scope, session)


class SpendLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


@router.put("/billing/spend-limit")
async def spend_limit(
    data: SpendLimit, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("pi.billing.manage")
    subscription = await billing.subscription_for(session, scope.tenant_id)
    subscription.spend_limit = data.amount
    await record(
        session,
        "pi_saas.spend_limit_changed",
        scope=scope,
        entity_type="pi_subscription",
        entity_id=subscription.id,
        details={"amount": str(data.amount) if data.amount is not None else None},
    )
    await session.commit()
    return await billing_view(request, scope, session)


# ------------------------------------------------------------------------------ team


class TeamInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    role: Literal["admin", "manager", "member", "viewer", "billing"]


class TeamRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["owner", "admin", "manager", "member", "viewer", "billing"]


async def _role_id(session: AsyncSession, tenant_id: UUID, key: str) -> UUID:
    role = await session.scalar(
        select(Role.id).where(Role.tenant_id == tenant_id, Role.key == key, Role.is_system)
    )
    if role is None:
        raise BusinessRuleViolation("ROLE_UNAVAILABLE", "This role is not available")
    return UUID(str(role))


@router.get("/team")
async def team(scope: Scope, session: Session) -> dict[str, Any]:
    scope.require("admin.members.read")
    from app.core.pagination import Pagination

    page = await MemberService(session, scope).search(Pagination(page=1, page_size=100), None)
    return {
        "members": [
            {
                "membership_id": m.membership_id,
                "user_id": m.user_id,
                "email": m.email,
                "display_name": m.display_name,
                "status": m.status,
                "roles": m.roles,
                "joined_at": m.joined_at,
            }
            for m in page.items
        ],
        "roles": [
            {
                "key": key,
                "name": name,
                "description": description,
                "permissions": [
                    {"key": p, "label": PERMISSIONS[p].label, "group": PERMISSIONS[p].group}
                    for p in sorted(SYSTEM_ROLES[key][2])
                    if p in PERMISSIONS
                    and (p.startswith(("pi.", "customers.", "admin.members")) or key == "owner")
                ],
            }
            for key, (name, description) in CLIENT_ROLES.items()
        ],
    }


@router.post("/team", status_code=201)
async def invite(
    data: TeamInvite, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("admin.members.manage")
    current = await entitlement(session, scope.tenant_id)
    seats = current.allowances.get("seats")
    used = await session.scalar(
        select(func.count()).select_from(active_memberships_for(scope.tenant_id).subquery())
    )
    if seats is not None and int(used or 0) >= int(seats):
        raise BusinessRuleViolation(
            "SEAT_LIMIT", "Your plan's team seats are all in use. Upgrade to add more people.", 409
        )
    settings = request.app.state.settings
    http = OutboundClient(settings, request.app.state.http)
    member = await MemberService(session, scope).add(
        MemberCreate(
            email=data.email,
            display_name=data.display_name,
            role_ids=[await _role_id(session, scope.tenant_id, data.role)],
        ),
        http,
        settings,
        "pi",
    )
    await session.commit()
    return {
        "membership_id": member.membership_id,
        "email": member.email,
        "roles": member.roles,
        "invite_link": member.invite_link,
    }


@router.put("/team/{membership_id}")
async def change_role(
    membership_id: UUID, data: TeamRole, scope: Scope, session: Session
) -> dict[str, Any]:
    scope.require("admin.members.manage")
    member = await MemberService(session, scope).update_roles(
        membership_id, [await _role_id(session, scope.tenant_id, data.role)]
    )
    await session.commit()
    return {"membership_id": member.membership_id, "roles": member.roles}


@router.delete("/team/{membership_id}", status_code=204)
async def remove_member(membership_id: UUID, scope: Scope, session: Session) -> None:
    await MemberService(session, scope).revoke(membership_id)
    await session.commit()


# ------------------------------------------------------------- teach pi / ask owner


def _draft_view(d: PiKnowledgeDraft) -> dict[str, Any]:
    return {
        "id": d.id,
        "origin": d.origin,
        "title": d.title,
        "content": d.content,
        "customer_visible": d.customer_visible,
        "status": d.status,
        "created_at": d.created_at,
        "source_note": (
            d.source_text[:600] if d.origin in {"website", "owner_upload", "owner_audio"} else None
        ),
    }


@router.get("/knowledge/drafts")
async def drafts(scope: Scope, session: Session, status: str = "draft") -> list[dict[str, Any]]:
    scope.require("pi.knowledge.manage")
    rows = await session.scalars(
        WorkspaceRepository(session, PiKnowledgeDraft, scope)
        .select()
        .where(PiKnowledgeDraft.status == status[:16])
        .order_by(PiKnowledgeDraft.created_at.desc())
        .limit(100)
    )
    return [_draft_view(d) for d in rows]


@router.post("/knowledge/drafts", status_code=201)
async def add_draft(data: teach.DraftInput, scope: Scope, session: Session) -> dict[str, Any]:
    draft = await teach.create_draft(session, scope, data)
    await session.commit()
    return _draft_view(draft)


@router.patch("/knowledge/drafts/{draft_id}")
async def edit_draft(
    draft_id: UUID, data: teach.DraftUpdate, scope: Scope, session: Session
) -> dict[str, Any]:
    draft = await teach.update_draft(session, scope, draft_id, data)
    await session.commit()
    return _draft_view(draft)


@router.post("/knowledge/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: UUID, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    draft = await teach.publish_draft(
        session, scope, draft_id, request.app.state.settings.knowledge_upload_max_bytes
    )
    await session.commit()
    return _draft_view(draft)


@router.post("/knowledge/drafts/{draft_id}/discard", status_code=204)
async def discard_draft(draft_id: UUID, scope: Scope, session: Session) -> None:
    await teach.discard_draft(session, scope, draft_id)
    await session.commit()


@router.post("/knowledge/teach", status_code=201)
async def teach_pi(
    data: teach.TeachInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    if not await hit(request, "pi-teach", str(scope.tenant_id), 60, 3600):
        raise HTTPException(status_code=429)
    from app.ai.manager import build_llm_manager

    manager = build_llm_manager(
        request.app.state.settings, request.app.state.http, request.app.state.sessions
    )
    draft = await teach.teach(session, scope, manager, data)
    await session.commit()
    return _draft_view(draft)


class WebsiteImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=10, max_length=300)


@router.post("/knowledge/upload", status_code=201)
async def teach_from_file(
    request: Request,
    scope: Scope,
    session: Session,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """PDF, Word, text, photo or voice note -> a draft to review (never published here)."""
    scope.require("pi.knowledge.manage")
    if not await hit(request, "pi-teach-file", str(scope.tenant_id), 30, 3600):
        raise HTTPException(status_code=429)
    from app.ai.manager import build_llm_manager
    from app.modules.pi_saas.teach_files import teach_file

    settings = request.app.state.settings
    limit = settings.media_max_bytes
    try:
        raw = await file.read(limit + 1)
    finally:
        await file.close()
    manager = build_llm_manager(settings, request.app.state.http, request.app.state.sessions)
    draft = await teach_file(session, scope, manager, raw, file.filename or "", limit)
    await session.commit()
    return _draft_view(draft)


@router.post("/knowledge/website", status_code=201)
async def website(
    data: WebsiteImport, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    if not await hit(request, "pi-website", str(scope.tenant_id), 20, 3600):
        raise HTTPException(status_code=429)
    draft = await teach.import_website(
        session,
        request.app.state.settings,
        OutboundClient(request.app.state.settings, request.app.state.http),
        scope,
        data.url,
    )
    await session.commit()
    return _draft_view(draft)


@router.get("/staff-requests")
async def staff_requests(scope: Scope, session: Session) -> list[dict[str, Any]]:
    service = PiService(session, scope)
    rows = await teach.open_requests(session, scope)
    visible = {
        c
        for c in await session.scalars(
            service.conversations.select().with_only_columns(PiConversation.id)
        )
    }
    return [
        {
            "id": r.id,
            "conversation_id": r.conversation_id,
            "customer_id": r.customer_id,
            "question": r.question,
            "context": r.context_summary,
            "created_at": r.created_at,
        }
        for r in rows
        if r.conversation_id in visible
    ]


@router.post("/staff-requests/{request_id}/answer")
async def answer_staff_request(
    request_id: UUID, data: teach.AnswerInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    staff_request = await session.scalar(
        WorkspaceRepository(session, PiStaffRequest, scope)
        .select()
        .where(PiStaffRequest.id == request_id)
    )
    if staff_request is not None:
        # Visibility follows the conversation (members see only assigned ones).
        await PiService(session, scope).conversations.get(staff_request.conversation_id)
    row = await teach.answer_request(
        session, scope, request_id, data, request.app.state.settings.knowledge_upload_max_bytes
    )
    await session.commit()
    if row.reply_message_id:
        await request.app.state.queue.enqueue(
            "send_pi_message", str(row.reply_message_id), job_id=f"send:{row.reply_message_id}"
        )
    return {"id": row.id, "status": row.status}


# ------------------------------------------------------------------------ test pi


@router.post("/playground")
async def playground(
    data: PlaygroundInput, request: Request, scope: Scope, session: Session
) -> dict[str, Any]:
    """Preview Pi's reply with current knowledge and rules. Nothing is sent or saved."""
    if not await hit(request, "pi-playground", str(scope.tenant_id), 120, 3600):
        raise HTTPException(status_code=429)
    return await preview(
        session,
        request.app.state.settings,
        request.app.state.http,
        request.app.state.sessions,
        scope,
        data,
    )


# ------------------------------------------------------------------------------ home


@router.get("/home")
async def home(scope: Scope, session: Session) -> dict[str, Any]:
    """Is Pi active, what did it do this week, and what needs attention — counted only
    over conversations this member may see. No sample or estimated numbers."""
    scope.require("pi.read")
    row = await _account(session, scope)
    service = PiService(session, scope)
    visible = service.conversations.select().with_only_columns(PiConversation.id)
    since = datetime.now(UTC) - timedelta(days=7)

    async def count(statement: Any) -> int:
        return int(await session.scalar(statement) or 0)

    conversations = await count(
        select(func.count())
        .select_from(PiConversation)
        .where(service.conversations.predicate(), PiConversation.last_message_at >= since)
    )
    replies = await count(
        select(func.count())
        .select_from(PiMessage)
        .where(
            service.messages.predicate(),
            PiMessage.conversation_id.in_(visible),
            PiMessage.sender_type == "ai",
            PiMessage.status.in_(["sent", "delivered", "read"]),
            PiMessage.created_at >= since,
        )
    )
    handed = await count(
        select(func.count())
        .select_from(PiHandoff)
        .where(
            service.handoffs.predicate(),
            PiHandoff.conversation_id.in_(visible),
            PiHandoff.status.in_(ACTIVE_HANDOFF),
        )
    )
    approvals = await count(
        select(func.count())
        .select_from(PiMessage)
        .where(
            service.messages.predicate(),
            PiMessage.conversation_id.in_(visible),
            PiMessage.status == "pending_approval",
        )
    )
    questions = await count(
        select(func.count())
        .select_from(PiStaffRequest)
        .where(
            WorkspaceRepository(session, PiStaffRequest, scope).predicate(),
            PiStaffRequest.conversation_id.in_(visible),
            PiStaffRequest.status == "open",
        )
    )
    leads = await count(
        select(func.count(func.distinct(PiAgentRun.conversation_id)))
        .select_from(PiAgentRun)
        .where(
            WorkspaceRepository(session, PiAgentRun, scope).predicate(),
            PiAgentRun.conversation_id.in_(visible),
            PiAgentRun.intent.in_(["requirement", "quote", "order", "pricing"]),
            PiAgentRun.created_at >= since,
        )
    )
    provider_failures = await count(
        select(func.count())
        .select_from(PiHandoff)
        .where(
            service.handoffs.predicate(),
            PiHandoff.conversation_id.in_(visible),
            PiHandoff.reason == "provider_failure",
            PiHandoff.created_at >= datetime.now(UTC) - timedelta(days=1),
        )
    )
    unread = await count(
        select(func.coalesce(func.sum(PiConversation.unread_count), 0)).where(
            service.conversations.predicate(), PiConversation.status == "open"
        )
    )
    plan = await entitlement(session, row.tenant_id, scope.environment_id)
    readiness = await onboarding.readiness(session, row)
    actions: list[dict[str, str]] = []
    if row.setup_state not in {"active", "paused"}:
        actions += [
            {"kind": "setup", "label": i["label"], "href": "/setup"}
            for i in readiness
            if not i["done"]
        ]
    if row.setup_state == "action_required":
        actions.append(
            {
                "kind": "problem",
                "label": "Pi has stopped: fix the issue",
                "href": "/settings/whatsapp",
            }
        )
    if provider_failures:
        actions.append(
            {
                "kind": "problem",
                "label": f"Pi couldn't reply to {provider_failures} conversation"
                f"{'s' if provider_failures != 1 else ''} today (AI unavailable). "
                "They were sent to your team.",
                "href": "/inbox?mode=human",
            }
        )
    if not plan.sending or plan.reason:
        actions.append({"kind": "billing", "label": "Check your plan", "href": "/settings/billing"})
    if approvals:
        actions.append(
            {
                "kind": "approvals",
                "label": f"{approvals} replies to approve",
                "href": "/inbox?filter=approvals",
            }
        )
    if questions:
        actions.append(
            {
                "kind": "questions",
                "label": f"{questions} questions for you",
                "href": "/inbox?filter=questions",
            }
        )
    if handed:
        actions.append(
            {
                "kind": "handoffs",
                "label": f"{handed} conversations need a person",
                "href": "/inbox?mode=human",
            }
        )
    return {
        "name": row.name,
        "setup_state": row.setup_state,
        "active": row.setup_state == "active" and plan.automation,
        "plan_reason": plan.reason,
        "metrics": {
            "conversations_7d": conversations,
            "pi_replies_7d": replies,
            "enquiries_7d": leads,
            "waiting_for_team": handed,
            "pending_approval": approvals,
            "open_questions": questions,
            "ai_unavailable_24h": provider_failures,
            "unread": unread,
        },
        "next_actions": actions[:8],
    }
