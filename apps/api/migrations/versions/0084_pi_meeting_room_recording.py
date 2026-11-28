"""pi video rooms: a room can be recorded (video and audio) for staff, when the host ticks it

Revision ID: 0084_pi_meeting_room_recording
Revises: 0083_pi_meeting_room_present

Additive: three columns on `pi_meeting_rooms`. `record_video` says the host ticked "record the call"
when the room was opened (everyone in it is told first); `recording_state` follows the file
(none, pending, saved, failed) and `recording_tries` bounds the copying. The recording itself is
saved like any meeting recording: in the workspace's own storage bucket, with a retention date.
Apply 0084 BEFORE deploying the code that reads it (the ORM selects every column). Rollback:
downgrade drops the columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0084_pi_meeting_room_recording"
down_revision = "0083_pi_meeting_room_present"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("record_video", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        TABLE,
        sa.Column("recording_state", sa.String(8), nullable=False, server_default="none"),
    )
    op.add_column(
        TABLE, sa.Column("recording_tries", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column(TABLE, "recording_tries")
    op.drop_column(TABLE, "recording_state")
    op.drop_column(TABLE, "record_video")
