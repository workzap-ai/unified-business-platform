"""The problems pi notes (pi Brain spec, Part 4): one row per thing that is going wrong in a
customer's business, the groups they are sorted into, every change as a revision, and the
links between problems that may share a root. Only workspaces in pi_mode "brain" write these.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.modules.pi import taxonomy
from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiProblemGroup(WorkspaceRow):
    """A set of problems in one category for one customer's business. The person can rename it."""

    __tablename__ = "pi_problem_groups"
    __table_args__ = workspace_args(
        "pi_problem_groups",
        scoped_fk("pi_problem_groups", "customer_id", "customers"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "customer_id",
            "category",
            name="uq_pi_problem_groups_cat",
        ),
        CheckConstraint(_in("created_by", ("pi", "person")), name="created_by"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    category: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(String(8), default="pi", server_default="pi")


class PiProblem(WorkspaceRow):
    __tablename__ = "pi_problems"
    __table_args__ = workspace_args(
        "pi_problems",
        scoped_fk("pi_problems", "customer_id", "customers"),
        scoped_fk("pi_problems", "group_id", "pi_problem_groups"),
        UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "number", name="uq_pi_problems_number"
        ),
        Index("ix_pi_problems_customer", "tenant_id", "environment_id", "customer_id", "status"),
        CheckConstraint(_in("status", taxonomy.STATUSES), name="status"),
        CheckConstraint(_in("severity_stated", taxonomy.SEVERITIES), name="severity_stated"),
        CheckConstraint(_in("severity_inferred", taxonomy.SEVERITIES), name="severity_inferred"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("length(btrim(title)) > 0", name="title_nonempty"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    group_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    number: Mapped[int] = mapped_column(Integer)  # P1, P2... within the customer
    title: Mapped[str] = mapped_column(String(120))  # English, <= 8 words, normalised
    title_local: Mapped[str] = mapped_column(String(200), default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    user_words: Mapped[list[str]] = mapped_column(JSONB, default=list)
    category: Mapped[str] = mapped_column(String(40))
    subtype: Mapped[str] = mapped_column(String(60), default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    frequency: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    since: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    trigger: Mapped[str] = mapped_column(String(200), default="", server_default="")
    impact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    severity_stated: Mapped[str] = mapped_column(
        String(10), default="unknown", server_default="unknown"
    )
    severity_inferred: Mapped[str] = mapped_column(
        String(10), default="unknown", server_default="unknown"
    )
    severity_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    current_workaround: Mapped[str] = mapped_column(Text, default="", server_default="")
    systems_mentioned: Mapped[list[str]] = mapped_column(JSONB, default=list)
    who_notices: Mapped[str] = mapped_column(String(200), default="", server_default="")
    person_believes_cause: Mapped[str] = mapped_column(String(300), default="", server_default="")
    requested_solution: Mapped[str] = mapped_column(String(300), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.8"))
    source_message_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    pii_redacted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    merged_into: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    goal_verb: Mapped[str | None] = mapped_column(String(24), nullable=True)  # spec 7.2
    raised_voluntarily: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )  # B5: raised on their own, not only as an answer
    # B2a (migration 0053): nullable, NULL means "not said". Shapes in problem_fields.py.
    constraints: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tried: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    cause: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class PiProblemRevision(WorkspaceRow):
    """Every change to a problem, so the latest wording shows but history is kept (R-MEM-04)."""

    __tablename__ = "pi_problem_revisions"
    __table_args__ = workspace_args(
        "pi_problem_revisions",
        scoped_fk("pi_problem_revisions", "problem_id", "pi_problems"),
        UniqueConstraint(
            "tenant_id", "environment_id", "problem_id", "revision", name="uq_pi_problem_revisions"
        ),
        CheckConstraint(_in("by", ("pi", "person", "staff")), name="by"),
    )
    problem_id: Mapped[UUID] = mapped_column(Uuid)
    revision: Mapped[int] = mapped_column(Integer)
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(String(24))  # created, correction, enrichment, merged...
    by: Mapped[str] = mapped_column(String(8), default="pi", server_default="pi")


class PiProblemLink(WorkspaceRow):
    """Two problems that may share a root. pi's links are suggestions until confirmed."""

    __tablename__ = "pi_problem_links"
    __table_args__ = workspace_args(
        "pi_problem_links",
        scoped_fk("pi_problem_links", "from_id", "pi_problems"),
        scoped_fk("pi_problem_links", "to_id", "pi_problems"),
        UniqueConstraint(
            "tenant_id", "environment_id", "from_id", "to_id", "type", name="uq_pi_problem_links"
        ),
        CheckConstraint(_in("type", taxonomy.LINK_TYPES), name="type"),
        CheckConstraint(_in("status", taxonomy.LINK_STATUSES), name="status"),
        CheckConstraint(_in("evidence", taxonomy.LINK_EVIDENCE), name="evidence"),
        CheckConstraint("from_id <> to_id", name="distinct"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
    from_id: Mapped[UUID] = mapped_column(Uuid)
    to_id: Mapped[UUID] = mapped_column(Uuid)
    type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.6"))
    created_by: Mapped[str] = mapped_column(String(8), default="pi", server_default="pi")
    status: Mapped[str] = mapped_column(String(12), default="suggested", server_default="suggested")
    evidence: Mapped[str] = mapped_column(
        String(12), default="pi_inferred", server_default="pi_inferred"
    )  # owner_said | pi_inferred | confirmed (spec 4.3)
