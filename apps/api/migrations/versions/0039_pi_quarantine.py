"""pi quarantine

Revision ID: 0039_pi_quarantine
Revises: 0038_pi_brain_payments

The untouched text of a message that held card, ID or password details, kept encrypted for 30
days while the message log keeps only the redacted copy (pi Brain spec 6.3, R-PRIV-02).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_pi_quarantine"
down_revision = "0038_pi_brain_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_quarantine",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("kinds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            ["tenant_id", "environment_id", "message_id"],
            ["pi_messages.tenant_id", "pi_messages.environment_id", "pi_messages.id"],
            name="fk_pi_quarantine_message_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_quarantine_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_quarantine_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_quarantine")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_quarantine_scope_id"),
    )
    op.create_index("ix_pi_quarantine_expires", "pi_quarantine", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pi_quarantine_expires", table_name="pi_quarantine")
    op.drop_table("pi_quarantine")
