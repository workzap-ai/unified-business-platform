"""pi meeting bots: pi joins a Zoom, Meet or Teams call through a bot provider (Recall.ai)

Revision ID: 0070_pi_meeting_bots
Revises: 0069_pi_meeting_pi_mode

docs/pi-saas/pi-meeting-bot.md. Additive: one new table (`pi_meeting_bots`) and the meeting
`source` check widened by one value ('teams'). Nothing is renamed, dropped or backfilled. The
table holds the provider's bot id and status, never the meeting link (it can carry a passcode):
only the link's host and a hash.

Code writes to it only when the workspace flag `response_rules.brain.meeting_bot` is on (default
off) and the provider's key is configured. Apply 0070 BEFORE deploying the code that uses it.
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE ROW
EXCLUSIVE lock on `pi_meetings` and `environments`; replacing the source check scans the (small)
meetings table once under a brief lock.
Rollback: downgrade drops the table (bot rows are lost; transcript lines already stored stay) and
puts the old source check back; it fails only if a meeting with source 'teams' exists, in which case
change those rows first.
"""

import sqlalchemy as sa
from alembic import op

revision = "0070_pi_meeting_bots"
down_revision = "0069_pi_meeting_pi_mode"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_bots"
OLD_SOURCES = "'upload', 'browser', 'native', 'zoom', 'meet'"
NEW_SOURCES = OLD_SOURCES + ", 'teams'"
STATUSES = (
    "'requested', 'joining', 'waiting', 'in_call', 'recording', 'denied', 'ended', 'done', 'failed'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_pi_meetings_source"), "pi_meetings", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_meetings_source"), "pi_meetings", f"source IN ({NEW_SOURCES})"
    )
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
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="requested", nullable=False),
        sa.Column("sub_code", sa.String(length=80), server_default="", nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("host", sa.String(length=80), server_default="", nullable=False),
        sa.Column("bot_name", sa.String(length=100), server_default="", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f(f"ck_{TABLE}_status")),
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
    op.create_index("uq_pi_meeting_bots_external", TABLE, ["provider", "external_id"], unique=True)
    op.create_index(
        "ix_pi_meeting_bots_meeting", TABLE, ["tenant_id", "environment_id", "meeting_id"]
    )
    op.create_index(
        "ix_pi_meeting_bots_url", TABLE, ["tenant_id", "environment_id", "url_hash", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_pi_meeting_bots_url", table_name=TABLE)
    op.drop_index("ix_pi_meeting_bots_meeting", table_name=TABLE)
    op.drop_index("uq_pi_meeting_bots_external", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_constraint(op.f("ck_pi_meetings_source"), "pi_meetings", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_meetings_source"), "pi_meetings", f"source IN ({OLD_SOURCES})"
    )
