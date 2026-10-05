"""Platform operator view of every Owner OS workspace (/api/v1/operator/workspaces).

Operational metadata only (name, status, size, products, whether it is a Pi business).
No business records or customer content are returned. Suspending a workspace blocks its
members' requests (active-tenant checks run on every request) and stops Pi automation;
its data is kept.

Super admins and admins (operator.workspaces.manage) can also set up a workspace for
someone and manage who belongs to it. Only a super admin gives, changes or removes a
workspace owner, every workspace keeps at least one owner, and nobody changes their own
membership from here (they use the workspace's own Team page).
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.email import send_platform_template
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.modules.access.dependencies import Session
from app.modules.access.models import MembershipRole, Role
from app.modules.access.service import assign_roles, owner_count
from app.modules.audit.service import record
from app.modules.auth.crypto import digest, hash_password, new_token
from app.modules.auth.models import AuthSession, MemberInviteToken, UserCredential
from app.modules.business_settings.models import BusinessSettings
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.pi_saas.models import PiBusinessAccount
from app.modules.pi_saas.operator import Operator, OperatorContext
from app.modules.products.models import PlatformProduct, TenantProductInstallation
from app.modules.tenants.models import Tenant
from app.modules.tenants.onboarding import provision_tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.workspace_repository import like_pattern

logger = logging.getLogger("platform")
router = APIRouter(prefix="/operator/workspaces", tags=["operator-workspaces"])


def _members(tenant_id: Any) -> Any:
    return (
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.status == "active")
        .scalar_subquery()
    )


@router.get("")
async def workspaces(
    operator: Operator,
    session: Session,
    search: str | None = Query(None, max_length=100),
    kind: Literal["all", "pi", "owner_os"] = "all",
    status: Literal["active", "inactive"] | None = None,
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    query = select(
        Tenant,
        _members(Tenant.id).label("members"),
        select(PiBusinessAccount.setup_state)
        .where(PiBusinessAccount.tenant_id == Tenant.id)
        .scalar_subquery()
        .label("pi_state"),
        select(Membership.id)
        .where(
            Membership.tenant_id == Tenant.id,
            Membership.user_id == operator.user_id,
            Membership.status == "active",
        )
        .exists()
        .label("is_member"),
    )
    if search:
        pattern = like_pattern(search)
        query = query.where(Tenant.name.ilike(pattern) | Tenant.slug.ilike(pattern))
    pi_tenants = select(PiBusinessAccount.tenant_id)
    if kind == "pi":
        query = query.where(Tenant.id.in_(pi_tenants))
    elif kind == "owner_os":
        query = query.where(Tenant.id.not_in(pi_tenants))
    if status:
        query = query.where(Tenant.status == status)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(
        await session.execute(
            query.order_by(Tenant.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    products: dict[Any, list[str]] = {}
    if rows:
        found = await session.execute(
            select(TenantProductInstallation.tenant_id, PlatformProduct.key)
            .join(PlatformProduct, PlatformProduct.id == TenantProductInstallation.product_id)
            .where(
                TenantProductInstallation.tenant_id.in_([r[0].id for r in rows]),
                TenantProductInstallation.status == "installed",
            )
        )
        for tenant_id, key in found:
            products.setdefault(tenant_id, []).append(key)
    return {
        "items": [
            {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "created_at": tenant.created_at,
                "members": int(members or 0),
                "products": sorted(products.get(tenant.id, [])),
                "kind": "pi" if pi_state is not None else "owner_os",
                "pi_setup_state": pi_state,
                # The operator can't suspend a workspace they work in (see set_status).
                "is_member": bool(is_member),
            }
            for tenant, members, pi_state, is_member in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{tenant_id}")
async def workspace(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise ResourceNotFound
    environments = await session.scalars(
        select(Environment)
        .where(Environment.tenant_id == tenant_id)
        .order_by(Environment.created_at)
    )
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    members = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.status == "active")
    )
    await record(
        session,
        "pi_operator.workspace_viewed",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        include_environment=False,
    )
    await session.commit()
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "created_at": tenant.created_at,
        "members": int(members or 0),
        "environments": [
            {"key": e.key, "name": e.name, "kind": e.kind, "status": e.status} for e in environments
        ],
        "pi_business": {"setup_state": account.setup_state, "status": account.status}
        if account
        else None,
    }


class WorkspaceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["active", "inactive"]
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{tenant_id}/status")
async def set_status(
    tenant_id: UUID, data: WorkspaceStatus, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.manage")
    tenant = await session.get(Tenant, tenant_id, with_for_update=True)
    if tenant is None:
        raise ResourceNotFound
    if data.status == "inactive":
        own = await session.scalar(
            select(Membership.id).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == operator.user_id,
                Membership.status == "active",
            )
        )
        if own is not None:
            raise BusinessRuleViolation(
                "OWN_WORKSPACE", "You can't suspend a workspace you are working in"
            )
    before = tenant.status
    tenant.status = data.status
    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id).with_for_update()
    )
    touched = False
    if account is not None and data.status == "inactive" and account.status == "active":
        account.status, account.suspended_by_workspace, touched = "suspended", True, True
    elif (
        account is not None
        and data.status == "active"
        and account.status == "suspended"
        and account.suspended_by_workspace
    ):
        # Only undo the suspension this action caused; a separate business suspension
        # (for example abuse) stays until an operator reinstates that business.
        account.status, account.suspended_by_workspace, touched = "active", False, True
    await record(
        session,
        f"pi_operator.workspace_{'reactivated' if data.status == 'active' else 'suspended'}",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        details={
            "from": before,
            "to": data.status,
            "reason": data.reason,
            "role": operator.role,
            "pi_account_suspended": touched and data.status == "inactive",
        },
        include_environment=False,
    )
    await session.commit()
    return {"id": tenant.id, "status": tenant.status}


# ---- Super admin / admin: create workspaces and manage their members ----------------


def _lower(value: str) -> str:
    return value.strip().lower()


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    owner_email: EmailStr
    owner_name: str = Field("", max_length=160)
    business_type: Literal["service_business", "product_business", "hybrid_business"] = (
        "service_business"
    )

    @field_validator("owner_email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _lower(value)


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    display_name: str = Field("", max_length=160)
    role: str = Field(min_length=2, max_length=40)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return _lower(value)


class MemberRole(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=2, max_length=40)


def _super_admin(operator: OperatorContext) -> bool:
    return operator.role == "owner"


async def _tenant(session: AsyncSession, tenant_id: UUID) -> Tenant:
    # Locked so concurrent owner changes on one workspace are serialized.
    tenant = await session.get(Tenant, tenant_id, with_for_update=True)
    if tenant is None:
        raise ResourceNotFound
    return tenant


async def _role(session: AsyncSession, tenant_id: UUID, key: str) -> Role:
    role = await session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.key == key))
    if role is None:
        raise BusinessRuleViolation("UNKNOWN_ROLE", "This workspace has no such role")
    return role


async def _is_owner(session: AsyncSession, tenant_id: UUID, membership_id: UUID) -> bool:
    found = await session.scalar(
        select(Role.id)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(
            MembershipRole.tenant_id == tenant_id,
            MembershipRole.membership_id == membership_id,
            Role.key == "owner",
        )
    )
    return found is not None


async def _user_for(session: AsyncSession, email: str, name: str) -> tuple[PlatformUser, bool]:
    user = await session.scalar(select(PlatformUser).where(PlatformUser.email == email))
    if user is not None:
        return user, False
    user = PlatformUser(email=email, display_name=name or email.split("@")[0][:160])
    session.add(user)
    await session.flush()
    # Random and never revealed: nobody can sign in until the invitation link is used.
    session.add(
        UserCredential(
            user_id=user.id,
            password_hash=hash_password(new_token()),
            password_changed_at=datetime.now(UTC),
        )
    )
    return user, True


async def _invite(
    request: Request,
    session: AsyncSession,
    user: PlatformUser,
    tenant: Tenant,
    inviter: str,
    is_new: bool,
) -> str | None:
    """New people get a one-time link to set their password; existing people are told
    where to sign in. A failed email never blocks the change."""
    settings = request.app.state.settings
    link: str | None = None
    if is_new:
        token = new_token()
        session.add(
            MemberInviteToken(
                user_id=user.id,
                tenant_id=tenant.id,
                token_hash=digest(token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=settings.member_invite_ttl_minutes),
            )
        )
        link = f"{settings.web_public_url}/accept-invite?token={token}"
    try:
        await send_platform_template(
            settings,
            OutboundClient(settings, request.app.state.http),
            "invitation",
            [user.email],
            {
                "name": user.display_name,
                "inviter": inviter,
                "workspace": tenant.name,
                "link": link or f"{settings.web_public_url}/login",
            },
        )
    except (BusinessRuleViolation, IntegrationError):
        logger.warning("invitation_email_failed", extra={"user_id": str(user.id)})
    return link


async def _audit(
    session: AsyncSession,
    operator: OperatorContext,
    action: str,
    tenant_id: UUID,
    details: dict[str, Any],
) -> None:
    await record(
        session,
        f"pi_operator.{action}",
        tenant_id=tenant_id,
        actor_user_id=operator.user_id,
        entity_type="tenant",
        entity_id=tenant_id,
        details={"role": operator.role, **details},
        include_environment=False,
    )


@router.post("", status_code=201)
async def create_workspace(
    data: WorkspaceCreate, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    """Set up a workspace for someone; they become its owner (invited if they are new)."""
    operator.require("operator.workspaces.manage")
    owner, is_new = await _user_for(session, data.owner_email, data.owner_name)
    if owner.status != "active":
        raise BusinessRuleViolation("USER_DISABLED", "This account is disabled")
    tenant, environment, _ = await provision_tenant(session, owner, data.name)
    session.add(
        BusinessSettings(
            tenant_id=tenant.id, environment_id=environment.id, business_type=data.business_type
        )
    )
    link = await _invite(request, session, owner, tenant, operator.label, is_new)
    await _audit(
        session,
        operator,
        "workspace_created",
        tenant.id,
        {"owner": str(owner.id), "new_account": is_new},
    )
    await session.commit()
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "invite_link": link}


@router.get("/{tenant_id}/members")
async def members(tenant_id: UUID, operator: Operator, session: Session) -> dict[str, Any]:
    operator.require("operator.workspaces.read")
    if await session.get(Tenant, tenant_id) is None:
        raise ResourceNotFound
    last_seen = (
        select(func.max(AuthSession.last_seen_at))
        .where(AuthSession.user_id == PlatformUser.id)
        .scalar_subquery()
    )
    rows = list(
        await session.execute(
            select(Membership, PlatformUser, last_seen.label("last_seen"))
            .join(PlatformUser, PlatformUser.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id)
            .order_by(Membership.status, PlatformUser.display_name)
        )
    )
    roles: dict[UUID, list[str]] = {}
    for membership_id, key in await session.execute(
        select(MembershipRole.membership_id, Role.key)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(MembershipRole.tenant_id == tenant_id)
        .order_by(Role.key)
    ):
        roles.setdefault(membership_id, []).append(key)
    available = await session.execute(
        select(Role.key, Role.name, Role.description)
        .where(Role.tenant_id == tenant_id)
        .order_by(Role.is_system.desc(), Role.name)
    )
    return {
        "members": [
            {
                "id": m.id,
                "user_id": u.id,
                "name": u.display_name,
                "email": u.email,
                "status": m.status,
                "account_status": u.status,
                "roles": roles.get(m.id, []),
                "joined_at": m.created_at,
                "last_seen_at": seen,
                "is_you": u.id == operator.user_id,
            }
            for m, u, seen in rows
        ],
        "roles": [{"key": k, "name": n, "description": d} for k, n, d in available],
        "can_manage": operator.can("operator.workspaces.manage"),
        "can_manage_owners": _super_admin(operator),
    }


@router.post("/{tenant_id}/members", status_code=201)
async def add_member(
    tenant_id: UUID, data: MemberAdd, request: Request, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.manage")
    tenant = await _tenant(session, tenant_id)
    role = await _role(session, tenant_id, data.role)
    if role.key == "owner" and not _super_admin(operator):
        raise BusinessRuleViolation(
            "SUPER_ADMIN_REQUIRED", "Only a super admin can add owners", 403
        )
    user, is_new = await _user_for(session, data.email, data.display_name)
    if user.id == operator.user_id:
        raise BusinessRuleViolation(
            "OWN_MEMBERSHIP", "Join through the workspace's own Team page instead"
        )
    membership = await session.scalar(
        select(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.user_id == user.id)
        .with_for_update()
    )
    if membership is not None and membership.status == "active":
        raise Conflict("This person is already a member")
    if membership is None:
        membership = Membership(tenant_id=tenant_id, user_id=user.id)
        session.add(membership)
    membership.status = "active"
    await session.flush()
    await assign_roles(session, tenant_id, membership.id, [role.id])
    link = await _invite(request, session, user, tenant, operator.label, is_new)
    await _audit(
        session,
        operator,
        "workspace_member_added",
        tenant_id,
        {"membership": str(membership.id), "new_role": role.key, "new_account": is_new},
    )
    await session.commit()
    return {"id": membership.id, "role": role.key, "invite_link": link}


async def _target(
    session: AsyncSession, operator: OperatorContext, tenant_id: UUID, membership_id: UUID
) -> Membership:
    membership = await session.scalar(
        select(Membership)
        .where(Membership.tenant_id == tenant_id, Membership.id == membership_id)
        .with_for_update()
    )
    if membership is None:
        raise ResourceNotFound
    if membership.user_id == operator.user_id:
        raise BusinessRuleViolation(
            "OWN_MEMBERSHIP", "Change your own access from the workspace's Team page"
        )
    return membership


@router.post("/{tenant_id}/members/{membership_id}/role")
async def change_member_role(
    tenant_id: UUID, membership_id: UUID, data: MemberRole, operator: Operator, session: Session
) -> dict[str, Any]:
    operator.require("operator.workspaces.manage")
    await _tenant(session, tenant_id)
    membership = await _target(session, operator, tenant_id, membership_id)
    if membership.status != "active":
        raise BusinessRuleViolation("NOT_ACTIVE", "Add this person again first")
    role = await _role(session, tenant_id, data.role)
    was_owner = await _is_owner(session, tenant_id, membership.id)
    if (was_owner or role.key == "owner") and not _super_admin(operator):
        raise BusinessRuleViolation(
            "SUPER_ADMIN_REQUIRED", "Only a super admin can change owners", 403
        )
    if (
        was_owner
        and role.key != "owner"
        and await owner_count(session, tenant_id, exclude=membership.id) == 0
    ):
        raise BusinessRuleViolation("LAST_OWNER", "A workspace needs at least one owner")
    await assign_roles(session, tenant_id, membership.id, [role.id])
    await _audit(
        session,
        operator,
        "workspace_member_role_changed",
        tenant_id,
        {"membership": str(membership.id), "new_role": role.key},
    )
    await session.commit()
    return {"id": membership.id, "role": role.key}


@router.delete("/{tenant_id}/members/{membership_id}", status_code=204)
async def remove_member(
    tenant_id: UUID, membership_id: UUID, operator: Operator, session: Session
) -> Response:
    operator.require("operator.workspaces.manage")
    await _tenant(session, tenant_id)
    membership = await _target(session, operator, tenant_id, membership_id)
    if membership.status == "active" and await _is_owner(session, tenant_id, membership.id):
        if not _super_admin(operator):
            raise BusinessRuleViolation(
                "SUPER_ADMIN_REQUIRED", "Only a super admin can remove owners", 403
            )
        if await owner_count(session, tenant_id, exclude=membership.id) == 0:
            raise BusinessRuleViolation("LAST_OWNER", "A workspace needs at least one owner")
    membership.status = "revoked"
    # Their sessions lose this workspace straight away.
    await session.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == membership.user_id,
            AuthSession.active_tenant_id == tenant_id,
        )
        .values(active_tenant_id=None, active_environment_id=None, active_branch_id=None)
    )
    await _audit(
        session, operator, "workspace_member_removed", tenant_id, {"membership": str(membership.id)}
    )
    await session.commit()
    return Response(status_code=204)
