from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


class InventoryLocation(WorkspaceRow):
    __tablename__ = "inventory_locations"
    __table_args__ = workspace_args(
        "inventory_locations",
        UniqueConstraint("tenant_id", "environment_id", "code", name="uq_inventory_locations_code"),
        ForeignKeyConstraint(
            ["tenant_id", "branch_id"],
            ["branches.tenant_id", "branches.id"],
            ondelete="RESTRICT",
            name="fk_inventory_locations_branch",
        ),
        CheckConstraint("code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="code_format"),
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        Index(
            "uq_inventory_locations_default",
            "tenant_id",
            "environment_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(40))
    branch_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")


class StockLevel(WorkspaceRow):
    __tablename__ = "stock_levels"
    __table_args__ = workspace_args(
        "stock_levels",
        scoped_fk("stock_levels", "variant_id", "catalog_variants"),
        scoped_fk("stock_levels", "location_id", "inventory_locations"),
        UniqueConstraint(
            "tenant_id", "environment_id", "variant_id", "location_id", name="uq_stock_levels_item"
        ),
        CheckConstraint("on_hand >= 0", name="on_hand_nonnegative"),
        CheckConstraint("reserved >= 0", name="reserved_nonnegative"),
    )
    variant_id: Mapped[UUID] = mapped_column(Uuid)
    location_id: Mapped[UUID] = mapped_column(Uuid)
    on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StockMovement(WorkspaceRow):
    """Append-only ledger. Every stock change is a movement with its resulting balance."""

    __tablename__ = "stock_movements"
    __table_args__ = workspace_args(
        "stock_movements",
        scoped_fk("stock_movements", "variant_id", "catalog_variants"),
        scoped_fk("stock_movements", "location_id", "inventory_locations"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
        CheckConstraint(
            "kind IN ('receipt', 'adjustment', 'sale', 'return', 'transfer_in', 'transfer_out')",
            name="kind",
        ),
        CheckConstraint("balance_after >= 0", name="balance_nonnegative"),
        Index(
            "uq_stock_movements_idempotency",
            "tenant_id",
            "environment_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_stock_movements_variant_created",
            "tenant_id",
            "environment_id",
            "variant_id",
            "created_at",
        ),
    )
    variant_id: Mapped[UUID] = mapped_column(Uuid)
    location_id: Mapped[UUID] = mapped_column(Uuid)
    quantity: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(240), default="", server_default="")
    balance_after: Mapped[int] = mapped_column(Integer)
    ref_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(80))
