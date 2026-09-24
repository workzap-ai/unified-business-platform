from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class Membership(TenantRow):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id"),
        CheckConstraint("status IN ('active', 'revoked')", name="status"),
        Index("ix_memberships_user_status_tenant", "user_id", "status", "tenant_id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
