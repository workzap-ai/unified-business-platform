"""pi Nori Platform board: remember nori's ref for a number, and which cards went back to nori

Revision ID: 0065_pi_nori_forward
Revises: 0064_pi_nori_item_chat

Additive, nullable or defaulted columns on two small tables (no backfill, no index):
  pi_nori_numbers.nori_ref        nori's own ref for a number it pushed ("nori-link:..." or
                                  "nori-member:..."); NULL for a number added by hand
  pi_nori_items.forward_ref       the ref to send back to nori with the card (copied from the number)
  pi_nori_items.forwarded_at      when nori took the card; NULL while it is still owed
  pi_nori_items.forward_attempts  tries so far (the sweep stops after a few)
  pi_nori_items.forward_note      the short reason a card was given up on
Locks: ADD COLUMN nullable or with a constant default, instant.
Rollback: downgrade drops the columns (nothing else depends on them).
"""

import sqlalchemy as sa
from alembic import op

revision = "0065_pi_nori_forward"
down_revision = "0064_pi_nori_item_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pi_nori_numbers", sa.Column("nori_ref", sa.String(80), nullable=True))
    op.add_column("pi_nori_items", sa.Column("forward_ref", sa.String(80), nullable=True))
    op.add_column(
        "pi_nori_items", sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "pi_nori_items",
        sa.Column("forward_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("pi_nori_items", sa.Column("forward_note", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_nori_items", "forward_note")
    op.drop_column("pi_nori_items", "forward_attempts")
    op.drop_column("pi_nori_items", "forwarded_at")
    op.drop_column("pi_nori_items", "forward_ref")
    op.drop_column("pi_nori_numbers", "nori_ref")
