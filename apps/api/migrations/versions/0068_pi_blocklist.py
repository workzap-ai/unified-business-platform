"""pi blocklist: numbers pi no longer answers

Revision ID: 0068_pi_blocklist
Revises: 0067_pi_nori_thread

One new table (nothing existing is touched, no backfill):
  pi_blocked_contacts  one row per blocked WhatsApp number, or per blocked prefix of six or more
                       digits: the reason, a note, who blocked it and how often it tried since.
Read on every inbound message (one indexed query); written only when the team blocks or unblocks.
Locks: CREATE TABLE on a new empty table; no lock on any existing table.
Rollback: downgrade drops the table (blocked senders are answered again; nothing else depends on it).
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_pi_blocklist"
down_revision = "0067_pi_nori_thread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_blocked_contacts",
        sa.Column("value", sa.String(length=15), nullable=False),
        sa.Column("kind", sa.String(length=8), server_default="number", nullable=False),
        sa.Column("reason", sa.String(length=200), server_default="", nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("source", sa.String(length=8), server_default="manual", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("blocked_by", sa.Uuid(), nullable=True),
        sa.Column("hits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "kind IN ('number', 'prefix')", name=op.f("ck_pi_blocked_contacts_kind")
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'chat', 'bulk')", name=op.f("ck_pi_blocked_contacts_source")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_blocked_contacts_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_blocked_contacts_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_blocked_contacts")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_blocked_contacts_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "value", name="uq_pi_blocked_contacts_value"
        ),
    )
    op.create_index(
        "ix_pi_blocked_contacts_active",
        "pi_blocked_contacts",
        ["tenant_id", "environment_id", "active"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_blocked_contacts_active", table_name="pi_blocked_contacts")
    op.drop_table("pi_blocked_contacts")
