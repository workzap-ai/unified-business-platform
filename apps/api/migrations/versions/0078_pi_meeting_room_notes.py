"""pi video rooms: pi's notes of the call survive an agent restart

Revision ID: 0078_pi_meeting_room_notes
Revises: 0077_pi_meeting_room_state

Additive: one nullable-with-default JSONB column on `pi_meeting_rooms`. `pi_notes` holds what pi
noted during the call (short redacted facts, the language the person asked for, the suggestions
given and the last few lines said), at most about 6 KB, so a restarted agent carries on instead of
asking everything again. It goes with the room when the meeting is erased.
Apply 0078 BEFORE deploying the code that reads it.
Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0078_pi_meeting_room_notes"
down_revision = "0077_pi_meeting_room_state"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "pi_notes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "pi_notes")
