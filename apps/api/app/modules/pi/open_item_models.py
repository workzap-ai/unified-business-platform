"""The open items pi keeps per business (platform spec v1.4, 17.7 and the 17.9 sketch `open_item`).

An open item is something the owner asked that is not finished: a question pi could not answer,
a request (a document, a call, a person, a timeline), a handoff to a person, a follow-up pi
promised. It stays until it is answered or the owner drops it; it is never dropped by a counter.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

KINDS = ("owner_question", "owner_request", "pending_handoff", "promised_followup")
STATUSES = ("open", "answered", "dropped")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PiOpenItem(WorkspaceRow):
    __tablename__ = "pi_open_items"
    __table_args__ = workspace_args(
        "pi_open_items",
        scoped_fk("pi_open_items", "conversation_id", "pi_conversations"),
        Index("ix_pi_open_items_open", "tenant_id", "environment_id", "status", "created_at"),
        Index("ix_pi_open_items_conversation", "tenant_id", "environment_id", "conversation_id"),
        CheckConstraint(_in("kind", KINDS), name="kind"),
        CheckConstraint(_in("status", STATUSES), name="status"),
    )
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    # What was asked, as a short tag the code can match again: "timeline", "human", "question",
    # "followup" (or the staff request id for a handoff).
    key: Mapped[str] = mapped_column(String(40), default="", server_default="")
    text: Mapped[str] = mapped_column(Text, default="", server_default="")  # redacted
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)  # the staff request, if any
    language: Mapped[str] = mapped_column(String(12), default="en", server_default="en")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    surfaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
