"""The Solution Box tables (pi platform spec Book 5, 4.3, 5.3 and 11.2): the map as shared versions,
the box that collects a customer's problems and its lifecycle, and the log of every offer decision.
Only workspaces in pi_mode "brain" write these.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.pi import box
from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

OFFER_RULES = ("R1", "R2", "R3", "B")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiMapVersion(WorkspaceRow):
    """One shared version of a customer's problem map (spec 4.3)."""

    __tablename__ = "pi_map_versions"
    __table_args__ = workspace_args(
        "pi_map_versions",
        scoped_fk("pi_map_versions", "customer_id", "customers"),
        UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "version", name="uq_pi_map_versions"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer)
    map_json: Mapped[dict[str, Any]] = mapped_column("json", JSONB, default=dict)
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Where the owner saw each node (node id -> [row, column]); the next version keeps them there.
    positions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiSolutionBox(WorkspaceRow):
    """The box that collects a customer's problems; its state is the lifecycle in spec 5.3."""

    __tablename__ = "pi_solution_boxes"
    __table_args__ = workspace_args(
        "pi_solution_boxes",
        scoped_fk("pi_solution_boxes", "customer_id", "customers"),
        scoped_fk("pi_solution_boxes", "map_version_id", "pi_map_versions"),
        scoped_fk("pi_solution_boxes", "parent_box_id", "pi_solution_boxes"),
        UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "version", name="uq_pi_solution_boxes"
        ),
        Index("ix_pi_solution_boxes_customer", "tenant_id", "environment_id", "customer_id"),
        CheckConstraint(_in("state", box.STATES), name="state"),
        CheckConstraint("version >= 1", name="version_positive"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(
        String(16), default="collecting", server_default="collecting"
    )
    map_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    owner_ranking: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_box_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)


class PiOfferLog(WorkspaceRow):
    """Every offer decision: the rule that held and why it was blocked (spec 5.7 canOffer)."""

    __tablename__ = "pi_offer_log"
    __table_args__ = workspace_args(
        "pi_offer_log",
        scoped_fk("pi_offer_log", "conversation_id", "pi_conversations"),
        Index("ix_pi_offer_log_conversation", "tenant_id", "environment_id", "conversation_id"),
        CheckConstraint(_in("rule", OFFER_RULES), name="rule"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    rule: Mapped[str] = mapped_column(String(2))
    allowed: Mapped[bool] = mapped_column(Boolean)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
