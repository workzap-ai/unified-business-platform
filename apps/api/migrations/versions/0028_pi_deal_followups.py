"""pi deal follow-ups

Revision ID: 0028_pi_deal_followups
Revises: 0027_pi_deal_auto_proposal

pi nudges a customer when a proposal goes unopened or unanswered, or an invoice is due
or overdue. One switch per business, on by default.
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_pi_deal_followups"
down_revision = "0027_pi_deal_auto_proposal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_deal_settings",
        sa.Column("auto_followups", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pi_deal_settings", "auto_followups")
