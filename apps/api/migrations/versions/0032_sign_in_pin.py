"""sign-in PIN

Revision ID: 0032_sign_in_pin
Revises: 0031_pi_receipts

An optional 6-digit PIN as the second sign-in step (after the password), for
computers without a fingerprint or face unlock. Only an Argon2id hash is stored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_sign_in_pin"
down_revision = "0031_pi_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_credentials",
        sa.Column("second_factor_pin_hash", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_credentials", "second_factor_pin_hash")
