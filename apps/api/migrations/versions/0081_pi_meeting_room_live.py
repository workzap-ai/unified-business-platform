"""pi video rooms: a live view of the call (captions, translation, staff tips, live notes)

Revision ID: 0081_pi_meeting_room_live
Revises: 0080_pi_meeting_room_person_mute

Additive: one JSONB column with a default on `pi_meeting_rooms`. `live` holds the newest few lines
of the call (redacted, with their translation), the tips pi has for staff and the notes it took, at
most about 14 KB, so people see captions in the language they read and staff see what pi suggests.
It goes with the room when the meeting is erased. Apply 0081 BEFORE deploying the code that reads
it (the ORM selects every column). Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0081_pi_meeting_room_live"
down_revision = "0080_pi_meeting_room_person_mute"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "live", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "live")
