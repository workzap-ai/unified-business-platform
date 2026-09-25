from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args
from app.shared.money import MONEY_SQL


class CatalogCategory(WorkspaceRow):
    __tablename__ = "catalog_categories"
    __table_args__ = workspace_args(
        "catalog_categories",
        UniqueConstraint("tenant_id", "environment_id", "slug", name="uq_catalog_categories_slug"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="", server_default="")


class CatalogProduct(WorkspaceRow):
    __tablename__ = "catalog_products"
    __table_args__ = workspace_args(
        "catalog_products",
        CheckConstraint(
            "offering_type IN ('service', 'product', 'hybrid', 'package')", name="offering_type"
        ),
        scoped_fk("catalog_products", "category_id", "catalog_categories"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        Index("ix_catalog_products_scope_status", "tenant_id", "environment_id", "status"),
        Index(
            "ix_catalog_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )
    name: Mapped[str] = mapped_column(String(200))
    offering_type: Mapped[str] = mapped_column(
        String(16), default="service", server_default="service"
    )
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    category_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    # Only approved products are exposed to PI through controlled tools.
    pi_visible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class CatalogVariant(WorkspaceRow):
    __tablename__ = "catalog_variants"
    __table_args__ = workspace_args(
        "catalog_variants",
        scoped_fk("catalog_variants", "product_id", "catalog_products"),
        UniqueConstraint("tenant_id", "environment_id", "sku", name="uq_catalog_variants_sku"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_format"),
        CheckConstraint("sku ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'", name="sku_format"),
        CheckConstraint(
            "low_stock_threshold IS NULL OR low_stock_threshold >= 0", name="threshold"
        ),
        Index("ix_catalog_variants_product", "tenant_id", "environment_id", "product_id"),
    )
    product_id: Mapped[UUID] = mapped_column(Uuid)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(MONEY_SQL)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    low_stock_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
