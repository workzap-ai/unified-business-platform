from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, LargeBinary, String
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
