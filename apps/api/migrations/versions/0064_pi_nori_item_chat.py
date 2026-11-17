"""pi Nori Platform board: a card remembers the pi chat it came from

Revision ID: 0064_pi_nori_item_chat
Revises: 0063_pi_nori_board

One nullable column on the new, small pi_nori_items table (no default, no backfill, no index):
conversation_id, the pi chat of a registry number whose message made the card, so the team can open
the chat and reply from the inbox. Locks: ADD COLUMN nullable, instant.
Rollback: downgrade drops the column (cards stay, the link to the chat is lost).
"""

import sqlalchemy as sa
from alembic import op

revision = "0064_pi_nori_item_chat"
down_revision = "0063_pi_nori_board"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pi_nori_items", sa.Column("conversation_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_nori_items", "conversation_id")
