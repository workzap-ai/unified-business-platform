from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class Role(TenantRow):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_roles_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_roles_tenant_key"),
        CheckConstraint("key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="key_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
    )
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="", server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RolePermission(TenantRow):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="CASCADE",
            name="fk_role_permissions_role",
        ),
        UniqueConstraint("tenant_id", "role_id", "permission", name="uq_role_permissions_entry"),
    )
    role_id: Mapped[UUID] = mapped_column()
    permission: Mapped[str] = mapped_column(String(60))


class MembershipRole(TenantRow):
    __tablename__ = "membership_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_membership",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="RESTRICT",
            name="fk_membership_roles_role",
        ),
        UniqueConstraint("tenant_id", "membership_id", "role_id", name="uq_membership_roles_entry"),
        Index("ix_membership_roles_role", "tenant_id", "role_id"),
    )
    membership_id: Mapped[UUID] = mapped_column()
    role_id: Mapped[UUID] = mapped_column()
