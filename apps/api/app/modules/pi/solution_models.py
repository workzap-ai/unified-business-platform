"""The stores of solutions that learn (Addendum 2 to the pi Brain v3, Part 3.11).

* idea arms: one quick idea of one problem of one industry, with the statistics that decide how
  often it is given. Seeds come from the industry solutions (Part 4); learned ones start in testing.
* solution memory: what pi gave each business, so it never repeats itself and can open with
  continuity when they come back.
* idea feedback: one row per reaction to an idea, with its score (Part 3.2). Offers, approvals and
  payments are never a signal here.
* idea sources: where a learned idea came from (seed, owner, document, miner, neighbour).
* solution versions: every learned change to an industry's solutions, with the way back.
* catalogue proposals and build fit: what owners keep needing that the catalogue lacks, and which
  Workzap build really solved which problem. Both go to a person and stay out of the chat reward.

All rows belong to one workspace and are read only when learning is on.
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

IDEA_STATUSES = ("active", "testing", "retired", "review", "shadow")
IDEA_SOURCES = ("seed", "owner", "document", "miner", "neighbour")
REACTIONS = ("none", "engaged", "tried", "rejected", "generic")
RESULTS = ("unknown", "worked", "no_change")


class PiIdeaArm(WorkspaceRow):
    __tablename__ = "pi_idea_arms"
    __table_args__ = workspace_args(
        "pi_idea_arms",
        UniqueConstraint("tenant_id", "environment_id", "arm_key", name="uq_pi_idea_arms_key"),
        Index("ix_pi_idea_arms_problem", "industry_key", "problem_id", "language"),
    )
    arm_key: Mapped[str] = mapped_column(String(140))  # "{industry}:{problem}:q1" or ":L<id>"
    industry_key: Mapped[str] = mapped_column(String(80))
    problem_id: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(12), default="en")
    text: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16), default="other")  # get_found, bring_back, ...
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)  # reactions counted
    status: Mapped[str] = mapped_column(String(12), default="active")
    traffic_cap: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(12), default="seed")
    retired_reason: Mapped[str] = mapped_column(String(200), default="")
    generic: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(12), default="1.0")


class PiSolutionMemory(WorkspaceRow):
    __tablename__ = "pi_solution_memory"
    __table_args__ = workspace_args(
        "pi_solution_memory",
        scoped_fk("pi_solution_memory", "customer_id", "customers"),
        scoped_fk("pi_solution_memory", "idea_arm_id", "pi_idea_arms"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "customer_id",
            "idea_arm_id",
            name="uq_pi_solution_memory",
        ),
        Index("ix_pi_solution_memory_customer", "customer_id", "given_at"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)  # the business
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    industry_key: Mapped[str] = mapped_column(String(80))
    problem_id: Mapped[str] = mapped_column(String(60))
    idea_arm_id: Mapped[UUID] = mapped_column(Uuid)
    given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reaction: Mapped[str] = mapped_column(String(12), default="none")
    said_will_try: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_result: Mapped[str] = mapped_column(String(12), default="unknown")
    builds_mentioned: Mapped[list[str]] = mapped_column(JSONB, default=list)
    offer_status: Mapped[str] = mapped_column(String(12), default="none")
    document_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PiIdeaFeedback(WorkspaceRow):
    __tablename__ = "pi_idea_feedback"
    __table_args__ = workspace_args(
        "pi_idea_feedback",
        scoped_fk("pi_idea_feedback", "idea_arm_id", "pi_idea_arms"),
        scoped_fk("pi_idea_feedback", "customer_id", "customers"),
        Index("ix_pi_idea_feedback_arm", "idea_arm_id", "applied"),
    )
    idea_arm_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    industry_key: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(12), default="en")
    signal: Mapped[str] = mapped_column(String(32))
    score: Mapped[int] = mapped_column(Integer, default=0)
    message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)  # counted in the leaderboard


class PiIdeaSource(WorkspaceRow):
    __tablename__ = "pi_idea_sources"
    __table_args__ = workspace_args(
        "pi_idea_sources",
        scoped_fk("pi_idea_sources", "idea_arm_id", "pi_idea_arms"),
        UniqueConstraint(
            "tenant_id", "environment_id", "idea_arm_id", name="uq_pi_idea_sources_arm"
        ),
    )
    idea_arm_id: Mapped[UUID] = mapped_column(Uuid)
    source: Mapped[str] = mapped_column(String(12), default="seed")
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    redaction_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("1"))


class PiSolutionVersion(WorkspaceRow):
    __tablename__ = "pi_solution_versions"
    __table_args__ = workspace_args(
        "pi_solution_versions",
        UniqueConstraint(
            "tenant_id", "environment_id", "industry_key", "version", name="uq_pi_solution_versions"
        ),
        Index("ix_pi_solution_versions_industry", "industry_key", "status"),
    )
    industry_key: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(12))  # "1.1", "1.2": solutions/{industry}@1.1
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="live")  # live, shadow, rolled_back
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiCatalogueProposal(WorkspaceRow):
    __tablename__ = "pi_catalogue_proposals"
    __table_args__ = workspace_args(
        "pi_catalogue_proposals", Index("ix_pi_catprop_status", "status")
    )
    need_text: Mapped[str] = mapped_column(Text)
    industries: Mapped[list[str]] = mapped_column(JSONB, default=list)
    count: Mapped[int] = mapped_column(Integer, default=1)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open, approved, rejected
    reviewer: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiBuildFit(WorkspaceRow):
    """Which Workzap build solved which problem for an industry, learned from delivered projects.
    It never feeds the chat reward (Part 3.6): pi must not learn to steer people towards whatever
    sells."""

    __tablename__ = "pi_build_fit"
    __table_args__ = workspace_args(
        "pi_build_fit", Index("ix_pi_build_fit_problem", "industry_key", "problem_key")
    )
    industry_key: Mapped[str] = mapped_column(String(80))
    problem_key: Mapped[str] = mapped_column(String(60))
    catalogue_key: Mapped[str] = mapped_column(String(40))
    confirmed_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="pending")
