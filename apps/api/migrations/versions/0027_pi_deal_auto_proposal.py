"""pi deal auto proposal

Revision ID: 0027_pi_deal_auto_proposal
Revises: 0025_billing_proration_dunning

When pi confirms a customer's brief, it makes the proposal itself (prices from the
catalog) and sends it when every line is priced.
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_pi_deal_auto_proposal"
down_revision = "0025_billing_proration_dunning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_deal_settings",
        sa.Column("auto_proposal", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pi_deal_settings", "auto_proposal")
