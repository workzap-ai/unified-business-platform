from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class Branch(TenantRow):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id"),
        UniqueConstraint("tenant_id", "code", name="uq_branches_tenant_code"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        CheckConstraint("code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="code_format"),
        Index("ix_branches_tenant_name_id", "tenant_id", "name", "id"),
    )
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(80))
