"""customer can_approve

Revision ID: 0036_customer_can_approve
Revises: 0035_pi_problems

Whether a contact may say yes to a solution document and approve a quote (pi Brain spec 4.9):
the owner or an authorised admin. Everyone who already exists keeps being able to, so nothing
changes until staff mark a team member as not able to.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_customer_can_approve"
down_revision = "0035_pi_problems"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("can_approve", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("customers", "can_approve")
