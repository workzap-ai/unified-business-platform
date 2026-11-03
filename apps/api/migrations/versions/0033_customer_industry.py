"""customer industry

Revision ID: 0033_customer_industry
Revises: 0032_sign_in_pin

The industry pi recognised from what a customer said about their business: a primary
industry pack, up to two secondary ones and how sure pi is. Only written when the
workspace turns on "industry_packs" in its knowledge settings.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_customer_industry"
down_revision = "0032_sign_in_pin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("industry_primary", sa.String(80), nullable=True))
    op.add_column(
        "customers",
        sa.Column(
            "industry_secondary",
            postgresql.ARRAY(sa.String(80)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("customers", sa.Column("industry_confidence", sa.Numeric(3, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "industry_confidence")
    op.drop_column("customers", "industry_secondary")
    op.drop_column("customers", "industry_primary")
