"""pi meetings: chapters of a meeting, with their times, made from its transcript

Revision ID: 0082_pi_meeting_chapters
Revises: 0081_pi_meeting_room_live

Additive: one JSONB column with a default on `pi_meetings`. `chapters` holds the chapters pi made
from the transcript (a title, one sentence and the start and end time of each, a few KB at most).
Key moments are not stored: they are read from the approved findings. The value goes with the
meeting when it is erased. Apply 0082 BEFORE deploying the code that reads it (the ORM selects
every column). Rollback: downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0082_pi_meeting_chapters"
down_revision = "0081_pi_meeting_room_live"
branch_labels = None
depends_on = None

TABLE = "pi_meetings"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "chapters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column(TABLE, "chapters")
