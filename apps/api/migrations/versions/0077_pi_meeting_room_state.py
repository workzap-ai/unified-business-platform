"""pi video rooms: what pi has already done in a call survives an agent restart

Revision ID: 0077_pi_meeting_room_state
Revises: 0076_pi_meeting_room_agent

Additive: four columns on `pi_meeting_rooms`, all with a default or nullable (no rewrite).
`pi_spoken` counts pi's turns (the per-call speech cap), `pi_disclosed` is whether the AI disclosure
was spoken, `pi_halted` is whether an emergency stopped pi for the rest of the call, and
`pi_last_spoke_at` is when pi last spoke (the pause between turns). A restarted agent reads them, so
it does not introduce itself again or start the cap afresh; an emergency stays stopped.
Apply 0077 BEFORE deploying the code that reads it.
Rollback: downgrade drops the columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0077_pi_meeting_room_state"
down_revision = "0076_pi_meeting_room_agent"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("pi_spoken", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        TABLE,
        sa.Column("pi_disclosed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        TABLE,
        sa.Column("pi_halted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(TABLE, sa.Column("pi_last_spoke_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("pi_last_spoke_at", "pi_halted", "pi_disclosed", "pi_spoken"):
        op.drop_column(TABLE, column)
