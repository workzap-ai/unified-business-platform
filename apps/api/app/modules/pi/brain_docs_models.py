"""Solution documents and quotes in pi's brain flow (pi Brain spec, Part 5).

pi drafts the solution document from the noted problems; Workzap prices the quote; a Workzap
reviewer approves each before anything reaches the person (R-DOC-00). A revision is a new
version, and the old one is marked superseded (R-QUOTE-08).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
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

KINDS = ("solution", "quote")
STATUSES = ("draft", "in_review", "approved", "sent", "superseded")
PREFIX = {"solution": "SD", "quote": "Q"}


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiBrainDocument(WorkspaceRow):
    __tablename__ = "pi_brain_documents"
    __table_args__ = workspace_args(
        "pi_brain_documents",
        scoped_fk("pi_brain_documents", "customer_id", "customers"),
        UniqueConstraint(
            "tenant_id",
            "environment_id",
            "kind",
            "number",
            "version",
            name="uq_pi_brain_documents_version",
        ),
        Index("ix_pi_brain_documents_status", "tenant_id", "environment_id", "status"),
        Index("ix_pi_brain_documents_offer", "tenant_id", "environment_id", "offer_id"),
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint(_in("status", STATUSES), name="status"),
        CheckConstraint(_in("drafted_by", ("pi", "staff")), name="drafted_by"),
    )
    customer_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    # Every version of one document and its quote share an offer.
    offer_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(8))
    number: Mapped[int] = mapped_column(Integer)  # SD-0001, Q-0001
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # The quote's solution document (same version), and the problems it covers.
    solution_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    problem_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # The English copy Workzap's team works from, when the person's language is not English.
    content_en: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="", server_default="")
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="draft", server_default="draft")
    drafted_by: Mapped[str] = mapped_column(String(8), default="pi", server_default="pi")
    approved_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The rendered PDF kept as one of the customer's files, once approved.
    file_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    @property
    def ref(self) -> str:
        base = f"{PREFIX[self.kind]}-{self.number:04d}"
        return base if self.version == 1 else f"{base}-v{self.version}"
