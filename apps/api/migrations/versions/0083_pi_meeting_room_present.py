"""pi video rooms: what pi is presenting in the room (a recap, one slide at a time)

Revision ID: 0083_pi_meeting_room_present
Revises: 0082_pi_meeting_chapters

Additive: one JSONB column with a default on `pi_meeting_rooms`. `present` holds the slides pi is
showing (plain redacted text from what the team approved and what was noted), the slide on show and
a version, a few KB at most; it is emptied when the presentation stops and goes with the room when
the meeting is erased. Apply 0083 BEFORE deploying the code that reads it (the ORM selects every
column). Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0083_pi_meeting_room_present"
down_revision = "0082_pi_meeting_chapters"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "present", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "present")
