from sqlalchemy import Boolean, CheckConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class Environment(TenantRow):
    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_environments_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_environments_tenant_key"),
        CheckConstraint("kind IN ('production', 'staging', 'development')", name="kind"),
        CheckConstraint("status IN ('active', 'archived')", name="status"),
        CheckConstraint("key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="key_format"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        Index(
            "uq_environments_one_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
