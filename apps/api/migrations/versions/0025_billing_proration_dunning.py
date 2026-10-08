"""pi billing proration, dunning and invoice pdf

Revision ID: 0025_billing_proration_dunning
Revises: 0026_pi_deal_documents

Plan-change-with-proration needs no schema of its own (Stripe is the source of truth,
confirmed through the existing subscription-updated webhook handling); this migration
only adds the staged-dunning tracking on ``pi_subscriptions`` and the invoice PDF link
on ``pi_platform_invoices``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_billing_proration_dunning"
down_revision = "0026_pi_deal_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_subscriptions",
        sa.Column("dunning_stage", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "pi_subscriptions",
        sa.Column("dunning_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pi_platform_invoices",
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pi_platform_invoices", "pdf_url")
    op.drop_column("pi_subscriptions", "dunning_last_sent_at")
    op.drop_column("pi_subscriptions", "dunning_stage")
