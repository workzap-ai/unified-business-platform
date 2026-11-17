"""pi nori credits bridge: idempotency keys, replay keys and the audit trail

Revision ID: 0062_pi_nori_bridge_log
Revises: 0061_pi_meeting_analysis

One new table, `pi_nori_bridge_log` (nothing existing is touched, no backfill). It holds, with no
message text and no whole phone number:
  kind 'inbound'  one row per WhatsApp message id sent to nori (a retry never replies twice)
  kind 'replay'   one row per accepted send-door request (timestamp + signature, kept 24 hours)
  kind 'send'     one audit row per send-door request after its signature passed
Rows are removed by the bridge itself (replay 24 hours, inbound 7 days, audit 90 days).
Needed only when a workspace turns on response_rules.nori_bridge; with the flag off nothing reads
or writes it, but apply 0062 BEFORE deploying code that has the bridge hook (the hook is inert
without NORI_BASE_URL, so the order only matters once the variables are set).
Locks: CREATE TABLE and CREATE INDEX on a new empty table; no lock on any existing table.
Rollback: downgrade drops the table (the audit trail and the replay keys are lost); or leave it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0062_pi_nori_bridge_log"
down_revision = "0061_pi_meeting_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_nori_bridge_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(80), server_default="", nullable=False),
        sa.Column("recipient_mask", sa.String(24), server_default="", nullable=False),
        sa.Column("recipient_hash", sa.String(64), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_nori_bridge_log")),
    )
    op.create_index(
        "uq_pi_nori_bridge_log_key",
        "pi_nori_bridge_log",
        ["kind", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_index(
        "ix_pi_nori_bridge_log_kind_created", "pi_nori_bridge_log", ["kind", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_pi_nori_bridge_log_kind_created", table_name="pi_nori_bridge_log")
    op.drop_index("uq_pi_nori_bridge_log_key", table_name="pi_nori_bridge_log")
    op.drop_table("pi_nori_bridge_log")
