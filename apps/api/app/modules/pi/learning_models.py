"""The learning brain's stores (pi Brain spec 8.2 and 11.8).

* examples: the best real exchanges, redacted, shown to pi as reference material for a similar
  situation. Never rules, never learned from a rule break, never anything with personal data.
* question arms: candidate wordings for one question slot, with success statistics.
* changes: the audit log of every automatic or staff change, with the evidence and a way back.
* runs: one row per nightly run, with the digest.

All rows belong to one workspace. Nothing here is read unless the workspace has switched learning
on (`response_rules.brain.learning_frozen` exactly False).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


class PiLearningExample(WorkspaceRow):
    __tablename__ = "pi_learning_examples"
    __table_args__ = workspace_args(
        "pi_learning_examples",
        scoped_fk("pi_learning_examples", "message_id", "pi_messages"),
        Index("ix_pi_learning_examples_status", "status", "language"),
    )
    message_id: Mapped[UUID] = mapped_column(Uuid)  # pi's reply this was made from
    situation: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    language: Mapped[str] = mapped_column(String(12), default="en")
    person_text: Mapped[str] = mapped_column(Text, default="")  # redacted
    reply_text: Mapped[str] = mapped_column(Text, default="")  # redacted
    reward: Mapped[int] = mapped_column(Integer, default=0)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="candidate")
    source_contacts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    redaction_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0"))
    embedding: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    retired_reason: Mapped[str] = mapped_column(String(200), default="")


class PiQuestionArm(WorkspaceRow):
    __tablename__ = "pi_question_arms"
    __table_args__ = workspace_args(
        "pi_question_arms", Index("ix_pi_question_arms_slot", "slot", "language")
    )
    slot: Mapped[str] = mapped_column(String(24))  # scope, frequency, impact, since, workaround
    language: Mapped[str] = mapped_column(String(12), default="en")
    text: Mapped[str] = mapped_column(String(300))
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="testing")
    traffic_cap: Mapped[float] = mapped_column(Float, default=1.0)
    created_by: Mapped[str] = mapped_column(String(12), default="seed")


class PiLearningChange(WorkspaceRow):
    __tablename__ = "pi_learning_changes"
    __table_args__ = workspace_args(
        "pi_learning_changes", Index("ix_pi_learning_changes_created", "created_at")
    )
    kind: Mapped[str] = mapped_column(String(32))
    speed: Mapped[str] = mapped_column(String(8), default="daily")
    risk: Mapped[str] = mapped_column(String(8), default="low")
    target_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="live")
    reason: Mapped[str] = mapped_column(String(300), default="")
    decided_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiLearningRun(WorkspaceRow):
    __tablename__ = "pi_learning_runs"
    __table_args__ = workspace_args(
        "pi_learning_runs", Index("ix_pi_learning_runs_started", "started_at")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    digest: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
