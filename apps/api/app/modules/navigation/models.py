from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import TenantRow


class NavigationPreference(TenantRow):
    """A user's custom order for one navigation section. Defaults stay in the registry."""

    __tablename__ = "navigation_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "section", name="uq_navigation_preferences_entry"),
        CheckConstraint("section IN ('main', 'admin')", name="section"),
        CheckConstraint("jsonb_typeof(item_order) = 'array'", name="order_array"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("platform_users.id", ondelete="CASCADE"))
    section: Mapped[str] = mapped_column(String(16))
    item_order: Mapped[list[str]] = mapped_column(JSONB, default=list)
