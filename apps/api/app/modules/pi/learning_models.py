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

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
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
    # pi's reply this was made from; empty for a seed made from a pack or golden conversation
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="live", server_default="live")
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
    canary_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    # The industry pack key this wording is for ("" = every industry, spec 8.2 situation key).
    industry: Mapped[str] = mapped_column(String(80), default="", server_default="")


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


class PiLearningLesson(WorkspaceRow):
    """A short piece of situational guidance in plain words (spec 8.2 lessons, 8.10 Teach pi).

    LOW-risk lessons (phrasing, order, vocabulary) go live; anything touching money, privacy, the
    offer, follow-ups, approval or advice is HIGH and waits for a second person (`review`).
    """

    __tablename__ = "pi_learning_lessons"
    __table_args__ = workspace_args(
        "pi_learning_lessons", Index("ix_pi_learning_lessons_status", "status")
    )
    text: Mapped[str] = mapped_column(Text)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # state, language, category
    risk: Mapped[str] = mapped_column(String(8), default="high")
    status: Mapped[str] = mapped_column(String(12), default="review")
    created_by: Mapped[str] = mapped_column(String(12), default="staff")
    author_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decided_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    uses: Mapped[int] = mapped_column(Integer, default=0)
    canary_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiLearnedPack(WorkspaceRow):
    """An industry pack pi drafted for businesses that fit no existing pack (spec 8.5 job 5).

    Listening sections may be used once a person approves them; the care sections (what pi refuses
    and protects) always wait for a person and are never live on their own.
    """

    __tablename__ = "pi_learned_packs"
    __table_args__ = workspace_args(
        "pi_learned_packs", Index("ix_pi_learned_packs_status", "status")
    )
    key: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="draft")
    care_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiReplyAudit(WorkspaceRow):
    """The full audit stamp of one pi reply (spec 8.9 "Full audit"): which prompt, pack versions,
    lessons, examples, question wordings and linter result produced it, so any reply can be traced
    to why pi said it. One row per reply message; holds identifiers only, never text."""

    __tablename__ = "pi_reply_audits"
    __table_args__ = workspace_args(
        "pi_reply_audits",
        scoped_fk("pi_reply_audits", "message_id", "pi_messages"),
        UniqueConstraint(
            "tenant_id", "environment_id", "message_id", name="uq_pi_reply_audits_msg"
        ),
        Index("ix_pi_reply_audits_created", "created_at"),
    )
    message_id: Mapped[UUID] = mapped_column(Uuid)  # pi's reply
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # the pi_agent_runs row
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    pack_versions: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    lesson_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    example_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    arm_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    linter: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    frozen: Mapped[bool] = mapped_column(Boolean, default=True)
