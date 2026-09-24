from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record


class UserCredential(Record, Base):
    """Password verifier only (Argon2id). Plaintext is never stored or logged."""

    __tablename__ = "user_credentials"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_users.id", ondelete="CASCADE"), unique=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Record, Base):
    """Opaque server-side session. Only a SHA-256 digest of the token is stored.

    Active tenant/environment/branch are server-held selections, validated against
    membership on every request rather than trusted from the browser.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires", "expires_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="", server_default="")
    active_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    active_environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    active_branch_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
