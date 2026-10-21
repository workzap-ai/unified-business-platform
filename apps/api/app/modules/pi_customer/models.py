from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
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


class CustomerPasskey(Record, Base):
    """A pi Customer's passkey (Face ID / fingerprint), tied to their WhatsApp number.
    Customers have no account, so the number (digits only) is the owner. Only the
    credential's public key is stored; the face or fingerprint stays on the device."""

    __tablename__ = "customer_passkeys"
    __table_args__ = (Index("ix_customer_passkeys_phone", "phone"),)
    phone: Mapped[str] = mapped_column(String(20))
    credential_id: Mapped[str] = mapped_column(String(1400), unique=True)  # base64url
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    name: Mapped[str] = mapped_column(String(80))
    transports: Mapped[str] = mapped_column(String(120), default="", server_default="")
    backed_up: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerFace(Record, Base):
    """A pi Customer's saved face for the check after the WhatsApp code (up to three
    per number). Only an encrypted face code is kept, never a photo."""

    __tablename__ = "customer_faces"
    __table_args__ = (Index("ix_customer_faces_phone", "phone"),)
    phone: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    code_encrypted: Mapped[str] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerSignInLock(Record, Base):
    """Wrong face or fingerprint tries in a row for one number, and the lock."""

    __tablename__ = "customer_sign_in_locks"
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerShareLink(Record, Base):
    """A view-only link a customer makes to show their requests to someone else (a boss,
    a partner). It shows requests and next steps only: no chat, no files, no quotes.
    Only a hash of the token is stored; it expires after seven days."""

    __tablename__ = "customer_share_links"
    __table_args__ = (Index("ix_customer_share_links_phone", "phone"),)
    phone: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # One conversation, or all of the customer's conversations when empty.
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    views: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class CustomerPrefs(Record, Base):
    """A customer's own settings for pi Customer, by WhatsApp number."""

    __tablename__ = "customer_prefs"
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    # "auto" mirrors the language of the customer's last message.
    language: Mapped[str] = mapped_column(String(16), default="auto", server_default="auto")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
