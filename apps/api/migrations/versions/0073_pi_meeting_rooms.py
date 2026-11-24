"""pi video rooms (PMB-5 Phase 1): a room per meeting, and who a room says spoke

Revision ID: 0073_pi_meeting_rooms
Revises: 0072_pi_template_sends

docs/pi-saas/pi-meeting-rooms.md. Additive: one new table (`pi_meeting_rooms`) and one nullable
column on `pi_meeting_participants` (`stream_user_id`, with a partial unique index). Nothing is
renamed, dropped or backfilled.

Code writes to them only when the workspace flag `response_rules.brain.meeting_room` is on
(default off) and the video provider's key and secret are configured. Apply 0073 BEFORE deploying
the code that uses it.
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE ROW
EXCLUSIVE lock on `pi_meetings` and `environments`; ADD COLUMN (nullable, no default) is a metadata
change; the partial index is built on a small table.
Rollback: downgrade drops the index, the column and the table (room rows are lost; transcript lines
already stored stay).
"""

import sqlalchemy as sa
from alembic import op

revision = "0073_pi_meeting_rooms"
down_revision = "0072_pi_template_sends"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_rooms"
STATES = "'created', 'live', 'ended', 'failed'"
TRANSCRIPT_STATES = "'none', 'pending', 'done', 'failed'"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), server_default="stream", nullable=False),
        sa.Column("call_id", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=10), server_default="created", nullable=False),
        sa.Column("transcript_state", sa.String(length=10), server_default="none", nullable=False),
        sa.Column("lines", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(f"state IN ({STATES})", name=op.f(f"ck_{TABLE}_state")),
        sa.CheckConstraint(
            f"transcript_state IN ({TRANSCRIPT_STATES})", name=op.f(f"ck_{TABLE}_transcript_state")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "meeting_id"],
            ["pi_meetings.tenant_id", "pi_meetings.environment_id", "pi_meetings.id"],
            name=f"fk_{TABLE}_meeting_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{TABLE}_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{TABLE}_scope_id"),
    )
    op.create_index(
        "uq_pi_meeting_rooms_meeting",
        TABLE,
        ["tenant_id", "environment_id", "meeting_id"],
        unique=True,
    )
    op.create_index("uq_pi_meeting_rooms_call", TABLE, ["provider", "call_id"], unique=True)
    op.add_column(
        "pi_meeting_participants", sa.Column("stream_user_id", sa.String(length=80), nullable=True)
    )
    op.create_index(
        "uq_pi_meeting_participants_stream",
        "pi_meeting_participants",
        ["tenant_id", "environment_id", "meeting_id", "stream_user_id"],
        unique=True,
        postgresql_where=sa.text("stream_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_pi_meeting_participants_stream", table_name="pi_meeting_participants")
    op.drop_column("pi_meeting_participants", "stream_user_id")
    op.drop_index("uq_pi_meeting_rooms_call", table_name=TABLE)
    op.drop_index("uq_pi_meeting_rooms_meeting", table_name=TABLE)
    op.drop_table(TABLE)
