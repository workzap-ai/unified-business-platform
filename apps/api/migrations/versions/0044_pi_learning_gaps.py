"""pi learning gaps: industry-scoped wordings, seeded examples, lesson canary, reply audit

Revision ID: 0044_pi_learning_gaps
Revises: 0043_pi_solution_learning
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_pi_learning_gaps"
down_revision = "0043_pi_solution_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An example seeded from a pack or a golden conversation has no pi message behind it. The
    # composite foreign key is not enforced while message_id is NULL.
    op.alter_column("pi_learning_examples", "message_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "pi_learning_examples",
        sa.Column("source", sa.String(length=16), server_default="live", nullable=False),
    )
    op.add_column(
        "pi_question_arms",
        sa.Column("industry", sa.String(length=80), server_default="", nullable=False),
    )
    op.add_column(
        "pi_learning_lessons",
        sa.Column("canary_since", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pi_experiences",
        sa.Column(
            "lesson_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )
    op.create_table(
        "pi_reply_audits",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("pack_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lesson_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("example_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("arm_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("linter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False),
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
            name="fk_pi_reply_audits_message_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_reply_audits_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_reply_audits_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_reply_audits")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_reply_audits_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "message_id", name="uq_pi_reply_audits_msg"
        ),
    )
    op.create_index("ix_pi_reply_audits_created", "pi_reply_audits", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pi_reply_audits_created", table_name="pi_reply_audits")
    op.drop_table("pi_reply_audits")
    op.drop_column("pi_experiences", "lesson_ids")
    op.drop_column("pi_learning_lessons", "canary_since")
    op.drop_column("pi_question_arms", "industry")
    op.drop_column("pi_learning_examples", "source")
    op.alter_column("pi_learning_examples", "message_id", existing_type=sa.Uuid(), nullable=False)
