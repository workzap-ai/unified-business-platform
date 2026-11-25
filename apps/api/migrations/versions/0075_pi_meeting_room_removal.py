"""pi video rooms: staff can remove a person from a live room

Revision ID: 0075_pi_meeting_room_removal
Revises: 0074_pi_meeting_room_audio

docs/pi-saas/pi-meeting-rooms-limits.md. Additive: one nullable column on
`pi_meeting_participants` (`removed_at`), no default, no rewrite. Code reads it only for people
in a video room. Apply 0075 BEFORE deploying the code that reads it (the ORM selects every column).
Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0075_pi_meeting_room_removal"
down_revision = "0074_pi_meeting_room_audio"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_participants"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "removed_at")
