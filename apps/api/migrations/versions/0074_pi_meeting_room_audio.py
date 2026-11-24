"""pi video rooms: record each voice briefly to write the transcript in Urdu and other languages

Revision ID: 0074_pi_meeting_room_audio
Revises: 0073_pi_meeting_rooms

docs/pi-saas/pi-meeting-rooms-stt.md. Additive: two columns on `pi_meeting_rooms`, both NOT NULL with a
constant default (`audio` false, `stt_tries` 0), so no existing row changes meaning and no
rewrite of the (tiny) table is needed on PostgreSQL 11 and later.

Code uses them only when the workspace flag `response_rules.brain.meeting_room_audio` is on
(default off). Apply 0074 BEFORE deploying the code that reads them (the ORM selects every column).
Rollback: downgrade drops both columns (nothing else refers to them).
"""

import sqlalchemy as sa
from alembic import op

revision = "0074_pi_meeting_room_audio"
down_revision = "0073_pi_meeting_rooms"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("audio", sa.Boolean(), server_default=sa.text("false"), nullable=False)
    )
    op.add_column(TABLE, sa.Column("stt_tries", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column(TABLE, "stt_tries")
    op.drop_column(TABLE, "audio")
