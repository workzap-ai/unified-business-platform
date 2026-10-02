"""payment link tokens

Revision ID: 0018_payment_link_tokens
Revises: 0017_email_verification

Pay-by-link / QR: a nullable, unique-indexed digest column plus an expiry on both
``pi_manual_payments`` (Pi subscription payments) and ``pi_payment_requests`` (a
business collecting from its own customer), the same digest-only shape as
``password_reset_tokens``/``email_verification_tokens``. No raw token is ever stored.

Note: at the time this was written, 0017 was already taken by a concurrent session's
"email verification" migration, so this follows it rather than 0016.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_payment_link_tokens"
down_revision = "0017_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_manual_payments", sa.Column("link_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "pi_manual_payments",
        sa.Column("link_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_pi_manual_payment_link_token", "pi_manual_payments", ["link_token_hash"]
    )

    op.add_column(
        "pi_payment_requests", sa.Column("link_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "pi_payment_requests",
        sa.Column("link_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_pi_payment_requests_link_token", "pi_payment_requests", ["link_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_pi_payment_requests_link_token", "pi_payment_requests", type_="unique"
    )
    op.drop_column("pi_payment_requests", "link_expires_at")
    op.drop_column("pi_payment_requests", "link_token_hash")

    op.drop_constraint("uq_pi_manual_payment_link_token", "pi_manual_payments", type_="unique")
    op.drop_column("pi_manual_payments", "link_expires_at")
    op.drop_column("pi_manual_payments", "link_token_hash")
