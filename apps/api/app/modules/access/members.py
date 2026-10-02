import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audience import Audience
from app.core.config import Settings
from app.core.pagination import Page, Pagination
from app.integrations.email import send_platform_template
from app.integrations.errors import IntegrationError
from app.integrations.http import OutboundClient
from app.modules.access.models import MembershipRole, Role, RolePermission
from app.modules.access.schemas import MemberCreate, MemberView
from app.modules.access.service import assign_roles, membership_grants, owner_count
from app.modules.audit.service import record
from app.modules.auth.crypto import digest, hash_password, new_token
from app.modules.auth.models import AuthSession, MemberInviteToken, UserCredential
from app.modules.memberships.models import Membership
from app.modules.tenants.models import Tenant
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope

logger = logging.getLogger("platform")


class MemberService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope

    async def _roles(self, membership_ids: list[UUID]) -> dict[UUID, list[tuple[UUID, str]]]:
        rows = await self.session.execute(
            select(MembershipRole.membership_id, Role.id, Role.key)
            .join(
                Role, (Role.id == MembershipRole.role_id) & (Role.tenant_id == self.scope.tenant_id)
            )
            .where(
                MembershipRole.tenant_id == self.scope.tenant_id,
                MembershipRole.membership_id.in_(membership_ids),
            )
            .order_by(Role.key)
        )
        grouped: dict[UUID, list[tuple[UUID, str]]] = {}
        for membership_id, role_id, key in rows:
            grouped.setdefault(membership_id, []).append((role_id, key))
        return grouped

    @staticmethod
    def _build(
        membership: Membership, user: PlatformUser, roles: list[tuple[UUID, str]]
    ) -> MemberView:
        return MemberView(
            membership_id=membership.id,
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=membership.status,
            roles=[k for _, k in roles],
            role_ids=[i for i, _ in roles],
            joined_at=membership.created_at,
        )

    async def _view(self, membership: Membership, user: PlatformUser) -> MemberView:
        roles = await self._roles([membership.id])
        return self._build(membership, user, roles.get(membership.id, []))

    async def search(self, page: Pagination, search: str | None) -> Page[MemberView]:
        statement = (
            select(Membership, PlatformUser)
            .join(PlatformUser, PlatformUser.id == Membership.user_id)
            .where(Membership.tenant_id == self.scope.tenant_id)
        )
        if search:
            term = f"%{search.lower().replace('%', '').replace('_', '')}%"
            statement = statement.where(
                func.lower(PlatformUser.display_name).like(term) | PlatformUser.email.like(term)
            )
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await self.session.execute(
                statement.order_by(PlatformUser.display_name, Membership.id)
                .offset(page.offset)
                .limit(page.page_size)
            )
        ).all()
        roles = await self._roles([m.id for m, _ in rows])
        items = [self._build(m, u, roles.get(m.id, [])) for m, u in rows]
        return Page(items=items, total=int(total or 0), page=page.page, page_size=page.page_size)

    async def add(
        self,
        data: MemberCreate,
        http: OutboundClient,
        settings: Settings,
        audience: Audience = "owner_os",
    ) -> MemberView:
        self.scope.require("admin.members.manage")
        user = await self.session.scalar(
            select(PlatformUser).where(PlatformUser.email == data.email)
        )
        is_new_account = user is None
        if user is None:
            user = PlatformUser(email=data.email, display_name=data.display_name)
            self.session.add(user)
            await self.session.flush()
            self.session.add(
                UserCredential(
                    user_id=user.id,
                    # Random and never revealed: nobody can sign in until the
                    # invitation link below is used to set a real password.
                    password_hash=hash_password(new_token()),
                    password_changed_at=datetime.now(UTC),
                )
            )
        existing = await self.session.scalar(
            select(Membership).where(
                Membership.tenant_id == self.scope.tenant_id, Membership.user_id == user.id
            )
        )
        if existing is not None and existing.status == "active":
            raise Conflict("This person is already a member")
        if existing is None:
            existing = Membership(tenant_id=self.scope.tenant_id, user_id=user.id)
            self.session.add(existing)
        else:
            existing.status = "active"
        await self.session.flush()
        await self._assign(existing.id, data.role_ids)
        await record(
            self.session,
            "member.added",
            scope=self.scope,
            entity_type="membership",
            entity_id=existing.id,
            include_environment=False,
        )
        invite_link = await self._invite(user, http, settings, audience, is_new_account)
        view = await self._view(existing, user)
        return view.model_copy(update={"invite_link": invite_link})

    async def _invite(
        self,
        user: PlatformUser,
        http: OutboundClient,
        settings: Settings,
        audience: Audience,
        is_new_account: bool,
    ) -> str | None:
        """New accounts get a one-time link to set their first password; an existing
        person added to another workspace already has one, so they just get pointed
        at sign-in. Either way, a failed send never blocks adding the member."""
        base = settings.pi_app_public_url if audience == "pi" else settings.web_public_url
        invite_link: str | None = None
        if is_new_account:
            current = datetime.now(UTC)
            token = new_token()
            self.session.add(
                MemberInviteToken(
                    user_id=user.id,
                    tenant_id=self.scope.tenant_id,
                    token_hash=digest(token),
                    expires_at=current + timedelta(minutes=settings.member_invite_ttl_minutes),
                )
            )
            invite_link = f"{base}/accept-invite?token={token}"
            link = invite_link
        else:
            link = f"{base}/{'sign-in' if audience == 'pi' else 'login'}"
        tenant_name = await self.session.scalar(
            select(Tenant.name).where(Tenant.id == self.scope.tenant_id)
        )
        try:
            await send_platform_template(
                settings,
                http,
                "invitation",
                [user.email],
                {
                    "name": user.display_name,
                    "inviter": self.scope.actor_label,
                    "workspace": tenant_name or "your workspace",
                    "link": link,
                },
            )
        except (BusinessRuleViolation, IntegrationError):
            logger.warning("invitation_email_failed", extra={"user_id": str(user.id)})
        return invite_link

    async def _assign(self, membership_id: UUID, role_ids: list[UUID]) -> None:
        roles = (
            await self.session.scalars(
                select(Role).where(Role.tenant_id == self.scope.tenant_id, Role.id.in_(role_ids))
            )
        ).all()
        if len(roles) != len(set(role_ids)):
            raise ResourceNotFound
        # Only owners may grant the owner role; nobody can grant access they lack.
        if any(r.key == "owner" for r in roles) and not await self._is_owner():
            raise BusinessRuleViolation("OWNER_REQUIRED", "Only owners can assign ownership")
        if self.scope.membership_id is None:
            raise BusinessRuleViolation("MEMBERSHIP_REQUIRED", "An active membership is required")
        held, _ = await membership_grants(
            self.session, self.scope.tenant_id, self.scope.membership_id
        )
        granted = set(
            await self.session.scalars(
                select(RolePermission.permission).where(
                    RolePermission.tenant_id == self.scope.tenant_id,
                    RolePermission.role_id.in_(role_ids),
                )
            )
        )
        if not granted <= held:
            raise BusinessRuleViolation(
                "PERMISSION_ESCALATION", "Cannot grant permissions you do not hold"
            )
        await assign_roles(self.session, self.scope.tenant_id, membership_id, role_ids)

    async def _is_owner(self, membership_id: UUID | None = None) -> bool:
        membership_id = membership_id or self.scope.membership_id
        if membership_id is None:
            return False
        found = await self.session.scalar(
            select(Role.id)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == self.scope.tenant_id,
                MembershipRole.membership_id == membership_id,
                Role.key == "owner",
            )
        )
        return found is not None

    async def _ensure_can_manage(self, target: Membership) -> None:
        """Owners are managed only by owners; nobody manages someone with more access."""
        if self.scope.membership_id is None:
            raise BusinessRuleViolation("MEMBERSHIP_REQUIRED", "An active membership is required")
        if await self._is_owner(target.id) and not await self._is_owner():
            raise BusinessRuleViolation("OWNER_REQUIRED", "Only owners can change an owner")
        held, _ = await membership_grants(
            self.session, self.scope.tenant_id, self.scope.membership_id
        )
        target_grants, _ = await membership_grants(self.session, self.scope.tenant_id, target.id)
        if not target_grants <= held:
            raise BusinessRuleViolation(
                "PERMISSION_ESCALATION", "Cannot change a member who holds access you do not"
            )

    async def _membership(self, membership_id: UUID) -> tuple[Membership, PlatformUser]:
        # Serialize ownership changes across different target members.
        await self.session.scalar(
            select(Tenant.id).where(Tenant.id == self.scope.tenant_id).with_for_update()
        )
        row = (
            await self.session.execute(
                select(Membership, PlatformUser)
                .join(PlatformUser, PlatformUser.id == Membership.user_id)
                .where(Membership.tenant_id == self.scope.tenant_id, Membership.id == membership_id)
                .with_for_update(of=Membership)
            )
        ).first()
        if row is None:
            raise ResourceNotFound
        return row[0], row[1]

    async def update_roles(self, membership_id: UUID, role_ids: list[UUID]) -> MemberView:
        self.scope.require("admin.members.manage")
        membership, user = await self._membership(membership_id)
        await self._ensure_can_manage(membership)
        owner_ids = set(
            await self.session.scalars(
                select(Role.id).where(Role.tenant_id == self.scope.tenant_id, Role.key == "owner")
            )
        )
        keeps_owner = bool(owner_ids & set(role_ids))
        if (
            not keeps_owner
            and await owner_count(self.session, self.scope.tenant_id, exclude=membership.id) == 0
        ):
            raise BusinessRuleViolation("LAST_OWNER", "A workspace needs at least one owner")
        await self._assign(membership.id, role_ids)
        await record(
            self.session,
            "member.roles_updated",
            scope=self.scope,
            entity_type="membership",
            entity_id=membership.id,
            include_environment=False,
        )
        return await self._view(membership, user)

    async def revoke(self, membership_id: UUID) -> None:
        self.scope.require("admin.members.manage")
        membership, _user = await self._membership(membership_id)
        if membership.id == self.scope.membership_id:
            raise BusinessRuleViolation("SELF_REVOKE", "You cannot remove yourself")
        await self._ensure_can_manage(membership)
        if await owner_count(self.session, self.scope.tenant_id, exclude=membership.id) == 0:
            raise BusinessRuleViolation("LAST_OWNER", "A workspace needs at least one owner")
        membership.status = "revoked"
        # Sessions pointing at this tenant lose their workspace selection immediately.
        await self.session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == membership.user_id,
                AuthSession.active_tenant_id == self.scope.tenant_id,
            )
            .values(active_tenant_id=None, active_environment_id=None, active_branch_id=None)
        )
        await self.session.flush()
        await record(
            self.session,
            "member.revoked",
            scope=self.scope,
            entity_type="membership",
            entity_id=membership.id,
            include_environment=False,
        )
