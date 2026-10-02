from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import Record


class PlatformUser(Record, Base):
    __tablename__ = "platform_users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="status"),
        CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1", name="email_normalized"
        ),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_nonempty"),
    )
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    # Null until the owner clicks the link from the verification email. Informational
    # only for now (nothing is gated on it); both apps show a "verify your email" nudge.
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None
