"""pi template sends: many numbers at once, and the history of every send

Revision ID: 0072_pi_template_sends
Revises: 0071_pi_meeting_documents

One new table (nothing existing is touched, no backfill):
  pi_template_sends  one row per template message to one number: queued, then handed to pi's outbound
                     path. Keeps who, which template and values, the consent note, the status and
                     the ids of the conversation and message the real WhatsApp status is read from.
Used only by the Templates page (bulk send and history). Unique per batch and number.
Locks: CREATE TABLE on a new empty table; no lock on any existing table.
Rollback: downgrade drops the table (messages already sent stay in the inbox).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0072_pi_template_sends"
down_revision = "0071_pi_meeting_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_template_sends",
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("person", sa.String(length=120), server_default="", nullable=False),
        sa.Column("template_name", sa.String(length=512), nullable=False),
        sa.Column("template_language", sa.String(length=16), nullable=False),
        sa.Column(
            "values", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("source", sa.String(length=10), server_default="paste", nullable=False),
        sa.Column("consent_note", sa.String(length=300), server_default="", nullable=False),
        sa.Column("created_by", sa.String(length=80), server_default="", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="queued", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('queued', 'sent', 'failed', 'skipped', 'cancelled')",
            name=op.f("ck_pi_template_sends_status"),
        ),
        sa.CheckConstraint(
            "source IN ('single', 'paste', 'customers', 'nori')",
            name=op.f("ck_pi_template_sends_source"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_template_sends_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_template_sends_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_template_sends")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_template_sends_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "batch_id", "phone", name="uq_pi_template_send_phone"
        ),
    )
    op.create_index(
        "ix_pi_template_sends_created",
        "pi_template_sends",
        ["tenant_id", "environment_id", "created_at"],
    )
    op.create_index(
        "ix_pi_template_sends_queue",
        "pi_template_sends",
        ["tenant_id", "environment_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_template_sends_queue", table_name="pi_template_sends")
    op.drop_index("ix_pi_template_sends_created", table_name="pi_template_sends")
    op.drop_table("pi_template_sends")
