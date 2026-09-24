from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class Department(TenantRow):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_departments_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_departments_tenant_code"),
        ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="RESTRICT"
        ),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        CheckConstraint("code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="code_format"),
        Index("ix_departments_tenant_branch", "tenant_id", "branch_id"),
        Index("ix_departments_tenant_name_id", "tenant_id", "name", "id"),
    )
    branch_id: Mapped[UUID | None] = mapped_column(nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(80))
