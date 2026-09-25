from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.access.service import membership_grants
from app.modules.auth.dependencies import Auth
from app.modules.business_settings.capabilities import business_permissions
from app.modules.environments.models import Environment
from app.modules.memberships.models import Membership
from app.modules.tenants.context import active_memberships
from app.shared.errors import BusinessRuleViolation, PermissionDenied
from app.shared.scope import WorkspaceScope

Session = Annotated[AsyncSession, Depends(get_session)]


async def workspace_scope(request: Request, auth: Auth, session: Session) -> WorkspaceScope:
    """Server-held workspace selection, revalidated against active membership per request."""
    selected = auth.session
    expected_tenant = request.headers.get("x-workspace-tenant")
    expected_environment = request.headers.get("x-workspace-environment")
    if (expected_tenant and expected_tenant != str(selected.active_tenant_id)) or (
        expected_environment and expected_environment != str(selected.active_environment_id)
    ):
        raise BusinessRuleViolation(
            "WORKSPACE_CHANGED",
            "Your workspace changed in another tab. Refresh before continuing.",
            status=409,
        )
    if selected.active_tenant_id is None or selected.active_environment_id is None:
        raise BusinessRuleViolation(
            "WORKSPACE_NOT_SELECTED", "Choose a workspace to continue", status=409
        )
    membership = await session.scalar(
        active_memberships(auth.user.id).where(Membership.tenant_id == selected.active_tenant_id)
    )
    if membership is None:
        raise PermissionDenied
    environment = await session.scalar(
        select(Environment.id).where(
            Environment.tenant_id == selected.active_tenant_id,
            Environment.id == selected.active_environment_id,
            Environment.status == "active",
        )
    )
    if environment is None:
        raise BusinessRuleViolation(
            "WORKSPACE_NOT_SELECTED", "Choose an environment to continue", status=409
        )
    permissions, _roles = await membership_grants(session, membership.tenant_id, membership.id)
    permissions = await business_permissions(
        session, membership.tenant_id, environment, permissions
    )
    return WorkspaceScope(
        tenant_id=membership.tenant_id,
        environment_id=environment,
        permissions=permissions,
        user_id=auth.user.id,
        membership_id=membership.id,
        branch_id=selected.active_branch_id,
        actor_label=auth.user.display_name[:80],
        request_id=getattr(request.state, "request_id", None),
    )


Scope = Annotated[WorkspaceScope, Depends(workspace_scope)]


def require(*permissions: str) -> Callable[..., Awaitable[WorkspaceScope]]:
    async def dependency(scope: Scope) -> WorkspaceScope:
        scope.require(*permissions)
        return scope

    dependency.__name__ = "require_" + "_".join(p.replace(".", "_") for p in permissions)
    return dependency
