"""A business groups several contacts so their problems can be sorted together (pi Brain spec
4.9). The owner is the first contact to name it; anyone else who names the same business joins
once the owner or an admin approves, or Workzap staff links them directly.

No `owner_customer_id` here on purpose: the owner is simply the contact (or contacts) with
`Customer.business_id` pointing here and `business_role = "owner"`. A back-reference would make
`customers` and `pi_businesses` reference each other, a cycle `Base.metadata.sorted_tables` cannot
order (it then ignores those foreign keys for sorting, which `customers.merge`'s safe-delete-order
logic and future cascading-delete code rely on being correct).
"""

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.models import WorkspaceRow, workspace_args


class PiBusiness(WorkspaceRow):
    __tablename__ = "pi_businesses"
    __table_args__ = workspace_args(
        "pi_businesses",
        UniqueConstraint("tenant_id", "environment_id", "name_key", name="uq_pi_businesses_name"),
        CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
    )
    name: Mapped[str] = mapped_column(String(160))  # as a contact first said it
    name_key: Mapped[str] = mapped_column(String(160))  # casefolded, for matching
