"""The memory ledgers (docs/pi-saas/pi-memory-entities-and-lifecycle.md, E1 to E3): what the owner
decided, what the owner rejected, and the text pi read from the owner's documents.

* `pi_decisions`: one row per decision (an offer, a yes, a decline, a revision request, an approval
  by staff). A newer statement on the same subject never overwrites an older one: the old row stays,
  its status becomes `superseded`, and the new row points at it (`supersedes_id`).
* `pi_rejections`: what the owner said no to (an idea, the offer). The idea filter reads it, so a
  rejected idea is not offered again; a later yes to the same target reverses it (row kept).
* `pi_document_texts`: the redacted text of a customer's document, one row per page, sheet, slide or
  section, with a reference, so a later question is answered from stored text and not from a guess.

Every row is workspace scoped (tenant, environment, customer) with composite foreign keys, so a row
can never point across a tenant. Written only for workspaces in pi_mode "brain"; with empty tables
nothing changes. Raw text is redacted before it is stored (`safety.redact_pii`).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

DECISION_KINDS = (
    "offer",
    "yes",
    "decline",
    "revision_request",
    "approval",
    "document_approval",
    "other",
)
DECISION_STATUSES = ("active", "superseded", "withdrawn")
DECISION_ACTORS = ("owner", "staff", "pi")
REJECTION_KINDS = ("idea", "offer", "document", "price", "option")
REJECTION_STATUSES = ("active", "reversed", "expired")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiDecision(WorkspaceRow):
    __tablename__ = "pi_decisions"
    __table_args__ = workspace_args(
        "pi_decisions",
        scoped_fk("pi_decisions", "customer_id", "customers"),
        scoped_fk("pi_decisions", "problem_id", "pi_problems"),
        scoped_fk("pi_decisions", "supersedes_id", "pi_decisions"),
        # a replayed message writes nothing twice
        Index(
            "uq_pi_decisions_source",
            "tenant_id",
            "environment_id",
            "customer_id",
            "kind",
            "subject_ref",
            "source_message_id",
            unique=True,
            postgresql_where=text("source_message_id IS NOT NULL"),
        ),
        # one live decision per subject: a newer one supersedes the older one
        Index(
            "uq_pi_decisions_active",
            "tenant_id",
            "environment_id",
            "customer_id",
            "subject_ref",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_pi_decisions_customer", "tenant_id", "environment_id", "customer_id", "status"),
        CheckConstraint(_in("kind", DECISION_KINDS), name="kind"),
        CheckConstraint(_in("status", DECISION_STATUSES), name="status"),
        CheckConstraint(_in("actor", DECISION_ACTORS), name="actor"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    problem_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    subject_ref: Mapped[str] = mapped_column(String(60), default="", server_default="")
    actor: Mapped[str] = mapped_column(String(8), default="owner", server_default="owner")
    owner_words: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active")
    supersedes_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiRejection(WorkspaceRow):
    __tablename__ = "pi_rejections"
    __table_args__ = workspace_args(
        "pi_rejections",
        scoped_fk("pi_rejections", "customer_id", "customers"),
        scoped_fk("pi_rejections", "problem_id", "pi_problems"),
        Index(
            "uq_pi_rejections_source",
            "tenant_id",
            "environment_id",
            "customer_id",
            "target_kind",
            "target_key",
            "source_message_id",
            unique=True,
            postgresql_where=text("source_message_id IS NOT NULL"),
        ),
        Index("ix_pi_rejections_customer", "tenant_id", "environment_id", "customer_id", "status"),
        CheckConstraint(_in("target_kind", REJECTION_KINDS), name="target_kind"),
        CheckConstraint(_in("status", REJECTION_STATUSES), name="status"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    problem_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    target_kind: Mapped[str] = mapped_column(String(12))
    # the idea arm key, or "box:offer", or a document ref: what was said no to
    target_key: Mapped[str] = mapped_column(String(140), default="", server_default="")
    idea_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    idea_text: Mapped[str] = mapped_column(String(500), default="", server_default="")
    owner_words: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PiDocumentText(WorkspaceRow):
    __tablename__ = "pi_document_texts"
    __table_args__ = workspace_args(
        "pi_document_texts",
        scoped_fk("pi_document_texts", "customer_id", "customers"),
        scoped_fk("pi_document_texts", "customer_file_id", "customer_files"),
        Index(
            "uq_pi_document_texts_ref",
            "tenant_id",
            "environment_id",
            "customer_file_id",
            "ordinal",
            unique=True,
        ),
        Index("ix_pi_document_texts_customer", "tenant_id", "environment_id", "customer_id"),
        CheckConstraint("ordinal >= 0", name="ordinal"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    customer_file_id: Mapped[UUID] = mapped_column(Uuid)
    ordinal: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str] = mapped_column(String(80))  # "page 3", "Sheet 2", "Slide 4", "section 1"
    text: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
