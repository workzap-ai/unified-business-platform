"""The workspace's blocklist: WhatsApp numbers pi no longer answers (one row set per workspace).

A row is one exact number, or a prefix of at least ``MIN_PREFIX`` digits (a bulk-created range of
numbers). Messages from a blocked sender are not stored and never reach the brain or a model; the
row only counts them (``hits``) so the team can see the block is working.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args

KINDS = ("number", "prefix")
SOURCES = ("manual", "chat", "bulk")
MIN_PREFIX = 6  # a country code alone (62, 92) can never be blocked by accident


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiBlockedContact(WorkspaceRow):
    __tablename__ = "pi_blocked_contacts"
    __table_args__ = workspace_args(
        "pi_blocked_contacts",
        UniqueConstraint(
            "tenant_id", "environment_id", "value", name="uq_pi_blocked_contacts_value"
        ),
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint(_in("source", SOURCES), name="source"),
        Index("ix_pi_blocked_contacts_active", "tenant_id", "environment_id", "active"),
    )
    value: Mapped[str] = mapped_column(String(15))  # digits only, with country code
    kind: Mapped[str] = mapped_column(String(8), default="number", server_default="number")
    reason: Mapped[str] = mapped_column(String(200), default="", server_default="")
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    source: Mapped[str] = mapped_column(String(8), default="manual", server_default="manual")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    blocked_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    hits: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
