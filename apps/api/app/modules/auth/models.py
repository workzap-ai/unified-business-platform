from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
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


class PasswordResetToken(Record, Base):
    """One-time, short-lived token for self-service password reset.

    Only a SHA-256 digest is stored, never the raw token (matching AuthSession).
    Requesting a new reset invalidates any earlier unused token for the same user.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_user", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerificationToken(Record, Base):
    """One-time, short-lived token proving the owner of `platform_users.email` clicked
    the link sent there. Same digest-only, single-use shape as PasswordResetToken."""

    __tablename__ = "email_verification_tokens"
    __table_args__ = (Index("ix_email_verification_tokens_user", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemberInviteToken(Record, Base):
    """One-time, short-lived token letting a newly invited member set their first real
    password. The placeholder credential created at invite time (a hash of a random
    value never given to anyone) cannot be entered by anyone until this is accepted."""

    __tablename__ = "member_invite_tokens"
    __table_args__ = (Index("ix_member_invite_tokens_user", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Record, Base):
    """Opaque server-side session. Only a SHA-256 digest of the token is stored.

    Active tenant/environment/branch are server-held selections, validated against
    membership on every request rather than trusted from the browser.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires", "expires_at"),
        CheckConstraint("audience IN ('owner_os', 'pi')", name="audience"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # Which application issued the session. A Pi customer session is only accepted by
    # /api/v1/pi-app routes, and an Owner OS session only by the others.
    audience: Mapped[str] = mapped_column(String(16), default="owner_os", server_default="owner_os")
    active_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    active_environment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    active_branch_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
