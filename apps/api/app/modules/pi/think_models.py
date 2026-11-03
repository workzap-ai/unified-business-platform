"""What the thinking step leaves behind (pi platform spec Book 5, 11.2): one row per pi message
saying which move it made and why (`pi_move_log`), and the hypothesis ledger of a conversation
(`pi_hypotheses`). Written only when `response_rules.brain.thinking` is on.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

CONFIDENCES = ("low", "medium", "high")
STATUSES = ("open", "confirmed", "dropped")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiMoveLog(WorkspaceRow):
    """The move behind one pi message (spec 3.3), for the variety rules and the audit."""

    __tablename__ = "pi_move_log"
    __table_args__ = workspace_args(
        "pi_move_log",
        scoped_fk("pi_move_log", "conversation_id", "pi_conversations"),
        scoped_fk("pi_move_log", "message_id", "pi_messages"),
        Index("ix_pi_move_log_conversation", "tenant_id", "environment_id", "conversation_id"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    move: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    had_question: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class PiHypothesis(WorkspaceRow):
    """One entry of the hypothesis ledger (spec 3.5). Confirmed only by the owner."""

    __tablename__ = "pi_hypotheses"
    __table_args__ = workspace_args(
        "pi_hypotheses",
        scoped_fk("pi_hypotheses", "conversation_id", "pi_conversations"),
        Index("ix_pi_hypotheses_conversation", "tenant_id", "environment_id", "conversation_id"),
        CheckConstraint(_in("confidence", CONFIDENCES), name="confidence"),
        CheckConstraint(_in("status", STATUSES), name="status"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    text: Mapped[str] = mapped_column(String(300))
    evidence_for: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    evidence_against: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    confidence: Mapped[str] = mapped_column(String(8), default="low", server_default="low")
    cheapest_test: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    ignored: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
