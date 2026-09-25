from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.models import MembershipRole, Role, RolePermission
from app.modules.access.permissions import SYSTEM_ROLES, validate
from app.modules.audit.service import record
from app.modules.memberships.models import Membership
from app.shared.errors import BusinessRuleViolation, Conflict, ResourceNotFound
from app.shared.scope import WorkspaceScope


async def membership_grants(
    session: AsyncSession, tenant_id: UUID, membership_id: UUID
) -> tuple[frozenset[str], list[str]]:
    rows = await session.execute(
        select(Role.key, RolePermission.permission)
        .select_from(MembershipRole)
        .join(
            Role,
            (Role.id == MembershipRole.role_id) & (Role.tenant_id == MembershipRole.tenant_id),
        )
        .outerjoin(
            RolePermission,
            (RolePermission.role_id == Role.id) & (RolePermission.tenant_id == Role.tenant_id),
        )
        .where(MembershipRole.tenant_id == tenant_id, MembershipRole.membership_id == membership_id)
    )
    roles: set[str] = set()
    permissions: set[str] = set()
    for role_key, permission in rows:
        roles.add(role_key)
        if permission:
            permissions.add(permission)
    return frozenset(permissions), sorted(roles)


async def seed_system_roles(session: AsyncSession, tenant_id: UUID) -> dict[str, Role]:
    # Two multi-row statements rather than one INSERT per role and permission: remote
    # databases (Neon) cost a network round trip per statement.
    ids = {key: uuid4() for key in SYSTEM_ROLES}
    await session.execute(
        insert(Role).values(
            [
                {
                    "id": ids[key],
                    "tenant_id": tenant_id,
                    "key": key,
                    "name": name,
                    "description": description,
                    "is_system": True,
                }
                for key, (name, description, _permissions) in SYSTEM_ROLES.items()
            ]
        )
    )
    await session.execute(
        insert(RolePermission).values(
            [
                {"id": uuid4(), "tenant_id": tenant_id, "role_id": ids[key], "permission": p}
                for key, (_name, _description, permissions) in SYSTEM_ROLES.items()
                for p in sorted(permissions)
            ]
        )
    )
    rows = await session.scalars(select(Role).where(Role.id.in_(list(ids.values()))))
    return {role.key: role for role in rows}


async def assign_roles(
    session: AsyncSession, tenant_id: UUID, membership_id: UUID, role_ids: Sequence[UUID]
) -> None:
    found = set(
        await session.scalars(
            select(Role.id).where(Role.tenant_id == tenant_id, Role.id.in_(list(role_ids)))
        )
    )
    if found != set(role_ids):
        raise ResourceNotFound
    await session.execute(
        delete(MembershipRole).where(
            MembershipRole.tenant_id == tenant_id, MembershipRole.membership_id == membership_id
        )
    )
    session.add_all(
        MembershipRole(tenant_id=tenant_id, membership_id=membership_id, role_id=r)
        for r in sorted(found)
    )
    await session.flush()


async def owner_count(session: AsyncSession, tenant_id: UUID, *, exclude: UUID | None) -> int:
    statement = (
        select(func.count(func.distinct(MembershipRole.membership_id)))
        .join(Role, (Role.id == MembershipRole.role_id) & (Role.tenant_id == tenant_id))
        .join(
            Membership,
            (Membership.id == MembershipRole.membership_id) & (Membership.tenant_id == tenant_id),
        )
        .where(
            MembershipRole.tenant_id == tenant_id,
            Role.key == "owner",
            Membership.status == "active",
        )
    )
    if exclude is not None:
        statement = statement.where(MembershipRole.membership_id != exclude)
    return int(await session.scalar(statement) or 0)


class RoleService:
    def __init__(self, session: AsyncSession, scope: WorkspaceScope) -> None:
        self.session, self.scope = session, scope

    async def search(self) -> list[tuple[Role, list[str], int]]:
        roles = (
            await self.session.scalars(
                select(Role)
                .where(Role.tenant_id == self.scope.tenant_id)
                .order_by(Role.is_system.desc(), Role.name)
                .limit(200)
            )
        ).all()
        perms = await self.session.execute(
            select(RolePermission.role_id, RolePermission.permission).where(
                RolePermission.tenant_id == self.scope.tenant_id
            )
        )
        counts = await self.session.execute(
            select(MembershipRole.role_id, func.count())
            .where(MembershipRole.tenant_id == self.scope.tenant_id)
            .group_by(MembershipRole.role_id)
        )
        by_role: dict[UUID, list[str]] = {}
        for role_id, permission in perms:
            by_role.setdefault(role_id, []).append(permission)
        count_map = {role_id: int(n) for role_id, n in counts}
        return [(r, sorted(by_role.get(r.id, [])), count_map.get(r.id, 0)) for r in roles]

    async def create(self, key: str, name: str, description: str, permissions: set[str]) -> Role:
        self.scope.require("admin.roles.manage")
        try:
            granted = validate(permissions)
        except ValueError:
            raise BusinessRuleViolation("UNKNOWN_PERMISSION", "Unknown permission") from None
        # Custom roles cannot grant more than the creating administrator holds.
        if not granted <= self.scope.permissions:
            raise BusinessRuleViolation("PERMISSION_ESCALATION", "Cannot grant held-back access")
        try:
            async with self.session.begin_nested():
                role = Role(
                    tenant_id=self.scope.tenant_id, key=key, name=name, description=description
                )
                self.session.add(role)
                await self.session.flush()
        except IntegrityError:
            raise Conflict("A role with this key already exists") from None
        self.session.add_all(
            RolePermission(tenant_id=self.scope.tenant_id, role_id=role.id, permission=p)
            for p in sorted(granted)
        )
        await self.session.flush()
        await record(
            self.session,
            "role.created",
            scope=self.scope,
            entity_type="role",
            entity_id=role.id,
            details={"key": key, "permissions": sorted(granted)},
            include_environment=False,
        )
        return role

    async def update(
        self, role_id: UUID, name: str, description: str, permissions: set[str]
    ) -> Role:
        self.scope.require("admin.roles.manage")
        role = await self.session.scalar(
            select(Role)
            .where(Role.tenant_id == self.scope.tenant_id, Role.id == role_id)
            .with_for_update()
        )
        if role is None:
            raise ResourceNotFound
        if role.is_system:
            raise BusinessRuleViolation("SYSTEM_ROLE", "System roles cannot be modified")
        try:
            granted = validate(permissions)
        except ValueError:
            raise BusinessRuleViolation("UNKNOWN_PERMISSION", "Unknown permission") from None
        if not granted <= self.scope.permissions:
            raise BusinessRuleViolation("PERMISSION_ESCALATION", "Cannot grant held-back access")
        role.name, role.description = name, description
        await self.session.execute(
            delete(RolePermission).where(
                RolePermission.tenant_id == self.scope.tenant_id, RolePermission.role_id == role.id
            )
        )
        self.session.add_all(
            RolePermission(tenant_id=self.scope.tenant_id, role_id=role.id, permission=p)
            for p in sorted(granted)
        )
        await self.session.flush()
        await record(
            self.session,
            "role.updated",
            scope=self.scope,
            entity_type="role",
            entity_id=role.id,
            details={"permissions": sorted(granted)},
            include_environment=False,
        )
        return role

    async def delete(self, role_id: UUID) -> None:
        self.scope.require("admin.roles.manage")
        role = await self.session.scalar(
            select(Role).where(Role.tenant_id == self.scope.tenant_id, Role.id == role_id)
        )
        if role is None:
            raise ResourceNotFound
        if role.is_system:
            raise BusinessRuleViolation("SYSTEM_ROLE", "System roles cannot be deleted")
        try:
            async with self.session.begin_nested():
                await self.session.delete(role)
                await self.session.flush()
        except IntegrityError:
            raise Conflict("Remove this role from members before deleting it") from None
        await record(
            self.session,
            "role.deleted",
            scope=self.scope,
            entity_type="role",
            entity_id=role_id,
            include_environment=False,
        )
