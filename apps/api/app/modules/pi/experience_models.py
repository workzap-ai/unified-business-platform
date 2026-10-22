"""What happened after each pi reply (pi Brain spec 8.2, 8.3 and 11.8).

One row per pi message once its outcome is known. The row holds no message text at all: only the
situation key, the outcome signals and the reward. That keeps personal data out of the learning
store by construction (R-PRIV-07); a text-bearing example bank can come later behind the redaction
gate. Offers accepted, quotes approved and payments are never part of `reward`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Integer, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, scoped_fk, workspace_args


class PiExperience(WorkspaceRow):
    __tablename__ = "pi_experiences"
    __table_args__ = workspace_args(
        "pi_experiences",
        scoped_fk("pi_experiences", "message_id", "pi_messages"),
        scoped_fk("pi_experiences", "conversation_id", "pi_conversations"),
        UniqueConstraint("tenant_id", "environment_id", "message_id", name="uq_pi_experiences_msg"),
        Index("ix_pi_experiences_scored", "scored_at"),
    )
    message_id: Mapped[UUID] = mapped_column(Uuid)
    conversation_id: Mapped[UUID] = mapped_column(Uuid)
    situation: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    signals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reward: Mapped[int] = mapped_column(Integer, default=0)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
