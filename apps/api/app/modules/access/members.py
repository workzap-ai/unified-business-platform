from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page, Pagination
from app.modules.access.models import MembershipRole, Role
from app.modules.access.schemas import MemberCreate, MemberView
from app.modules.access.service import assign_roles, owner_count
from app.modules.audit.service import record
from app.modules.auth.crypto import hash_password
from app.modules.auth.models import AuthSession, UserCredential
from app.modules.memberships.models import Membership
from app.modules.users.models import PlatformUser
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope


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

    async def add(self, data: MemberCreate) -> MemberView:
        self.scope.require("admin.members.manage")
        user = await self.session.scalar(
            select(PlatformUser).where(PlatformUser.email == data.email)
        )
        if user is None:
            if not data.initial_password:
                raise BusinessRuleViolation(
                    "PASSWORD_REQUIRED", "An initial password is required for new accounts"
                )
            user = PlatformUser(email=data.email, display_name=data.display_name)
            self.session.add(user)
            await self.session.flush()
            self.session.add(
                UserCredential(
                    user_id=user.id,
                    password_hash=hash_password(data.initial_password),
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
        return await self._view(existing, user)

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
        await assign_roles(self.session, self.scope.tenant_id, membership_id, role_ids)

    async def _is_owner(self) -> bool:
        if self.scope.membership_id is None:
            return False
        found = await self.session.scalar(
            select(Role.id)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == self.scope.tenant_id,
                MembershipRole.membership_id == self.scope.membership_id,
                Role.key == "owner",
            )
        )
        return found is not None

    async def _membership(self, membership_id: UUID) -> tuple[Membership, PlatformUser]:
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
