"""One additive table for the bridge: idempotency keys, replay keys and the audit trail.

Platform-level (no foreign keys), like pi_platform_state: it holds no message text and no whole
phone number, only a masked number and a hash, so it never blocks the erasure of a tenant.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

KINDS = ("inbound", "replay", "send")


class PiNoriBridgeLog(Base):
    __tablename__ = "pi_nori_bridge_log"
    __table_args__ = (
        Index(
            "uq_pi_nori_bridge_log_key",
            "kind",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_pi_nori_bridge_log_kind_created", "kind", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(16))
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tenant_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(80), default="", server_default="")
    recipient_mask: Mapped[str] = mapped_column(String(24), default="", server_default="")
    recipient_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
