"""pi meetings: what pi does in a meeting (off, listen, speak)

Revision ID: 0062_pi_meeting_pi_mode
Revises: 0061_pi_meeting_analysis

One column on `pi_meetings` (`pi_mode`, NOT NULL, default 'off') and a CHECK that it is one of
off, listen, speak. Every existing meeting becomes 'off' (the default is applied without rewriting
the table), so nothing changes for a workspace until a person chooses a mode for a meeting and the
workspace flag `brain.meeting_voice` is on. Additive only. Apply 0062 BEFORE deploying the code
that reads it.
Locks: ADD COLUMN with a constant default is instant on PostgreSQL 11+; the CHECK scans the (small)
meetings table once under a brief lock.
Rollback: downgrade drops the check and the column (the chosen modes are lost; nothing else).
"""

import sqlalchemy as sa
from alembic import op

revision = "0062_pi_meeting_pi_mode"
down_revision = "0061_pi_meeting_analysis"
branch_labels = None
depends_on = None

TABLE = "pi_meetings"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("pi_mode", sa.String(length=8), nullable=False, server_default="off"),
    )
    op.create_check_constraint(
        op.f(f"ck_{TABLE}_pi_mode"), TABLE, "pi_mode IN ('off', 'listen', 'speak')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f(f"ck_{TABLE}_pi_mode"), TABLE, type_="check")
    op.drop_column(TABLE, "pi_mode")
