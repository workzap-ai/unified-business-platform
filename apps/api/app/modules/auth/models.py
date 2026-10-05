from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
)
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
    # Second sign-in step (face or fingerprint): wrong tries in a row, and the lock.
    second_factor_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    second_factor_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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


class UserPasskey(Record, Base):
    """A passkey (WebAuthn credential): Face ID, Touch ID, Windows Hello, an Android
    fingerprint or a security key. The face or fingerprint never leaves the device;
    only the credential's public key is stored here."""

    __tablename__ = "user_passkeys"
    __table_args__ = (Index("ix_user_passkeys_user", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    credential_id: Mapped[str] = mapped_column(String(1400), unique=True)  # base64url
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    name: Mapped[str] = mapped_column(String(80))
    transports: Mapped[str] = mapped_column(String(120), default="", server_default="")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserFace(Record, Base):
    """A saved face for the second sign-in step (up to three per person). Only an
    encrypted face code (embedding) is kept, never a photo."""

    __tablename__ = "user_faces"
    __table_args__ = (Index("ix_user_faces_user", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    code_encrypted: Mapped[str] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
