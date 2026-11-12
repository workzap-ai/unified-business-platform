"""The Nori Platform board's two tables (workspace data, one row set per Workzap workspace).

``pi_nori_numbers``: WhatsApp numbers the team added by hand (or nori told pi about) so pi knows
the sender is a nori user, and of which nori workspace. ``pi_nori_items``: the facts about a board
card that the generic task row has no place for (which nori workspace, who, which department, what
kind of item). The card itself is a ``pi_tasks`` row with the key ``board:nori:<ref>``.
"""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

ITEM_KINDS = ("feature", "problem", "feedback", "module", "question", "change", "note")
SOURCES = ("nori", "whatsapp", "manual")
NUMBER_SOURCES = ("manual", "nori")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiNoriNumber(WorkspaceRow):
    __tablename__ = "pi_nori_numbers"
    __table_args__ = workspace_args(
        "pi_nori_numbers",
        UniqueConstraint("tenant_id", "environment_id", "phone", name="uq_pi_nori_numbers_phone"),
        CheckConstraint(_in("source", NUMBER_SOURCES), name="source"),
    )
    phone: Mapped[str] = mapped_column(String(15))
    workspace: Mapped[str] = mapped_column(String(120))
    person: Mapped[str] = mapped_column(String(120), default="", server_default="")
    department: Mapped[str] = mapped_column(String(80), default="", server_default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    source: Mapped[str] = mapped_column(String(10), default="manual", server_default="manual")


class PiNoriItem(WorkspaceRow):
    __tablename__ = "pi_nori_items"
    __table_args__ = workspace_args(
        "pi_nori_items",
        scoped_fk("pi_nori_items", "task_id", "pi_tasks"),
        UniqueConstraint("tenant_id", "environment_id", "ref", name="uq_pi_nori_items_ref"),
        Index("ix_pi_nori_items_task", "tenant_id", "environment_id", "task_id"),
        CheckConstraint(_in("item_kind", ITEM_KINDS), name="item_kind"),
        CheckConstraint(_in("source", SOURCES), name="source"),
    )
    task_id: Mapped[UUID] = mapped_column(Uuid)
    ref: Mapped[str] = mapped_column(String(80))
    item_kind: Mapped[str] = mapped_column(String(12), default="note", server_default="note")
    nori_workspace: Mapped[str] = mapped_column(String(120), default="", server_default="")
    person: Mapped[str] = mapped_column(String(120), default="", server_default="")
    department: Mapped[str] = mapped_column(String(80), default="", server_default="")
    phone_mask: Mapped[str] = mapped_column(String(24), default="", server_default="")
    source: Mapped[str] = mapped_column(String(10), default="manual", server_default="manual")
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)
