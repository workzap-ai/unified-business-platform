from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record, TenantRow, WorkspaceRow, workspace_args


class PlatformProduct(Record, Base):
    """Installable software products (e.g. PI). Not the business catalog."""

    __tablename__ = "platform_products"
    __table_args__ = (
        CheckConstraint("key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="key_format"),
        CheckConstraint("status IN ('available', 'deprecated')", name="status"),
    )
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="available", server_default="available")
    features: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, server_default="{}"
    )


class TenantProductInstallation(TenantRow):
    __tablename__ = "tenant_product_installations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_tenant_product_installations_tenant_id"),
        UniqueConstraint("tenant_id", "product_id", name="uq_tenant_product_installations_product"),
        CheckConstraint("status IN ('installed', 'suspended')", name="status"),
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_products.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), default="installed", server_default="installed")
    installed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnvironmentProductInstallation(WorkspaceRow):
    __tablename__ = "environment_product_installations"
    __table_args__ = workspace_args(
        "environment_product_installations",
        ForeignKeyConstraint(
            ["tenant_id", "installation_id"],
            ["tenant_product_installations.tenant_id", "tenant_product_installations.id"],
            ondelete="CASCADE",
            name="fk_environment_product_installations_installation",
        ),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "installation_id",
            name="uq_environment_product_installations_entry",
        ),
    )
    installation_id: Mapped[UUID] = mapped_column(Uuid)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    disabled_features: Mapped[list[str]] = mapped_column(
        ARRAY(String(60)), default=list, server_default="{}"
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
