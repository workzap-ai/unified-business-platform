"""The untouched text of a message that held personal data, kept encrypted for a short time.

The message log keeps the redacted copy (pi Brain spec 6.3). The original is kept here only so a
person can look into abuse or a dispute, encrypted, and deleted when `expires_at` passes (30 days).
Nothing reads it for learning or for replies.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args

RETENTION_DAYS = 30


class PiQuarantine(WorkspaceRow):
    __tablename__ = "pi_quarantine"
    __table_args__ = workspace_args(
        "pi_quarantine",
        scoped_fk("pi_quarantine", "message_id", "pi_messages"),
        Index("ix_pi_quarantine_expires", "expires_at"),
    )
    message_id: Mapped[UUID] = mapped_column(Uuid)
    kinds: Mapped[list[str]] = mapped_column(JSONB, default=list)
    payload: Mapped[str] = mapped_column(Text)  # encrypted
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # never show the payload
        return f"<PiQuarantine {self.id} {self.kinds}>"
