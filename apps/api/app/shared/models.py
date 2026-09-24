from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Record:
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantRow(Record, Base):
    __abstract__ = True
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )


class WorkspaceRow(Record, Base):
    """Business data owned by one tenant environment (see ADR 0005).

    Tables must include workspace_args() so the environment reference is tied to the
    same tenant and child rows can reference (tenant_id, environment_id, id).
    """

    __abstract__ = True
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )
    environment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


def workspace_args(table: str, *extra: Any) -> tuple[Any, ...]:
    return (
        ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            ondelete="RESTRICT",
            name=f"fk_{table}_environment",
        ),
        UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{table}_scope_id"),
        *extra,
    )


def scoped_fk(table: str, column: str, target: str) -> ForeignKeyConstraint:
    """Composite reference that cannot cross tenant or environment boundaries."""
    return ForeignKeyConstraint(
        ["tenant_id", "environment_id", column],
        [f"{target}.tenant_id", f"{target}.environment_id", f"{target}.id"],
        ondelete="RESTRICT",
        name=f"fk_{table}_{column}",
    )
