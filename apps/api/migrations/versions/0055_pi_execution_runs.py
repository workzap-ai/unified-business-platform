"""pi controlled execution (Level 3): one row per run

Revision ID: 0055_pi_execution_runs
Revises: 0054_payment_idempotency

Additive only: one new table, `pi_execution_runs`, holding the sealed snapshot of a run (scope, tasks,
execution records, audit chain). Nothing is read from or written to it unless the workspace is in
pi_mode "brain" with response_rules.brain.level3_exec exactly true (default off). No existing table is
touched, so there is nothing to backfill. Rollback: downgrade drops the table (runs and their audit
trail are lost), or revert the code and leave the table.

Note: the repository also holds non-numbered revisions; this one chains from the numbered head 0054.
"""

import sqlalchemy as sa
from alembic import op

revision = "0055_pi_execution_runs"
down_revision = "0054_payment_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_execution_runs",
        sa.Column("run_ref", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="proposed", nullable=False),
        sa.Column("snapshot", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("head_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
            "status IN ('proposed', 'approved', 'in_progress', 'implemented', 'failed')",
            name=op.f("ck_pi_execution_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_execution_runs_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_execution_runs_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_execution_runs")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_execution_runs_scope_id"
        ),
    )
    op.create_index(
        "ix_pi_execution_runs_customer",
        "pi_execution_runs",
        ["tenant_id", "environment_id", "customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_execution_runs_customer", table_name="pi_execution_runs")
    op.drop_table("pi_execution_runs")
