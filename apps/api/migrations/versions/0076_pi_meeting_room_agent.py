"""pi video rooms: the room agent (pi speaks): mode, mute, and who holds the room

Revision ID: 0076_pi_meeting_room_agent
Revises: 0075_pi_meeting_room_removal

Additive: five columns on `pi_meeting_rooms`, all with a default or nullable (no rewrite).
`pi_mode` is 'off' or 'speak', `pi_muted` is the host's mute switch, `pi_intake` lets pi lead with a
lone customer, `agent_id` and `agent_beat_at` say which agent process holds the room and when it
last answered (one agent per call). Apply 0076 BEFORE deploying the code that reads it.
Rollback: downgrade drops the columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0076_pi_meeting_room_agent"
down_revision = "0075_pi_meeting_room_removal"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("pi_mode", sa.String(8), nullable=False, server_default="off"))
    op.add_column(
        TABLE, sa.Column("pi_muted", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column(
        TABLE, sa.Column("pi_intake", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column(TABLE, sa.Column("agent_id", sa.String(40), nullable=True))
    op.add_column(TABLE, sa.Column("agent_beat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_pi_meeting_rooms_pi_mode", TABLE, "pi_mode IN ('off','speak')")


def downgrade() -> None:
    op.drop_constraint("ck_pi_meeting_rooms_pi_mode", TABLE, type_="check")
    for column in ("agent_beat_at", "agent_id", "pi_intake", "pi_muted", "pi_mode"):
        op.drop_column(TABLE, column)
