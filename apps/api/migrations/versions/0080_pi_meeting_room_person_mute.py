"""pi video rooms: the host can mute one person (and let them speak again)

Revision ID: 0080_pi_meeting_room_person_mute
Revises: 0079_pi_meeting_agents

Additive: one nullable column on `pi_meeting_participants` (`muted_at`), no default, no rewrite.
Code reads it only for people in a video room. Apply 0080 BEFORE deploying the code that reads it
(the ORM selects every column). Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0080_pi_meeting_room_person_mute"
down_revision = "0079_pi_meeting_agents"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_participants"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("muted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "muted_at")
