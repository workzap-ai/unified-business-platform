from sqlalchemy import CheckConstraint, String
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
