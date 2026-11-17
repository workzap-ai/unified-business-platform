"""pi Nori Platform board: remember which WhatsApp message a card came from

Revision ID: 0066_pi_nori_item_message
Revises: 0065_pi_nori_forward

Additive, one nullable column on a small table (no backfill, no index):
  pi_nori_items.message_id   the inbound pi message a registry person's card was filed from; used to
                             hand that message's photo or file to nori as a signed link. NULL for
                             older cards and for cards that are not from WhatsApp.
Locks: ADD COLUMN nullable, instant.
Rollback: downgrade drops the column (nothing else depends on it).
"""

import sqlalchemy as sa
from alembic import op

revision = "0066_pi_nori_item_message"
down_revision = "0065_pi_nori_forward"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pi_nori_items", sa.Column("message_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_nori_items", "message_id")
