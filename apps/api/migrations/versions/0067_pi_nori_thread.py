"""pi Nori Platform board: a ledger of the chat messages sent to nori

Revision ID: 0067_pi_nori_thread
Revises: 0066_pi_nori_item_message

One new table (nothing existing is touched, no backfill):
  pi_nori_thread  one row per pi message that was offered to nori's conversation door: when nori took
                  it, the tries so far and the short reason it was given up on. Unique per message,
                  so a message is sent once and retried a limited number of times.
Read or written only when a workspace has response_rules.nori_bridge.forward_messages true.
Locks: CREATE TABLE on a new empty table; no lock on any existing table.
Rollback: downgrade drops the table (nothing else depends on it; nori keeps what it received).
"""

import sqlalchemy as sa
from alembic import op

revision = "0067_pi_nori_thread"
down_revision = "0066_pi_nori_item_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_nori_thread",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("note", sa.String(length=40), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_nori_thread_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_nori_thread_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_nori_thread")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_nori_thread_scope_id"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "message_id", name="uq_pi_nori_thread_message"
        ),
    )


def downgrade() -> None:
    op.drop_table("pi_nori_thread")
