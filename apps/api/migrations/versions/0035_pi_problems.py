"""pi problems

Revision ID: 0035_pi_problems
Revises: 0034_conversation_flow_state

The problems pi notes in brain mode (pi Brain spec, Part 4): a row per problem with its
groups, every change as a revision, and links between problems that may share a root.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_pi_problems"
down_revision = "0034_conversation_flow_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_problem_groups",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.String(length=8), server_default="pi", nullable=False),
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
            "created_by IN ('pi', 'person')", name=op.f("ck_pi_problem_groups_created_by")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_problem_groups_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_problem_groups_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_problem_groups_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_problem_groups")),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "customer_id",
            "category",
            name="uq_pi_problem_groups_cat",
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_problem_groups_scope_id"
        ),
    )
    op.create_table(
        "pi_problems",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("title_local", sa.String(length=200), server_default="", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("user_words", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("subtype", sa.String(length=60), server_default="", nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("frequency", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("since", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trigger", sa.String(length=200), server_default="", nullable=False),
        sa.Column("impact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "severity_stated", sa.String(length=10), server_default="unknown", nullable=False
        ),
        sa.Column(
            "severity_inferred", sa.String(length=10), server_default="unknown", nullable=False
        ),
        sa.Column("severity_score", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("current_workaround", sa.Text(), server_default="", nullable=False),
        sa.Column("systems_mentioned", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("who_notices", sa.String(length=200), server_default="", nullable=False),
        sa.Column(
            "person_believes_cause", sa.String(length=300), server_default="", nullable=False
        ),
        sa.Column("requested_solution", sa.String(length=300), server_default="", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("source_message_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("pii_redacted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("merged_into", sa.Uuid(), nullable=True),
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
            "severity_inferred IN ('low', 'medium', 'high', 'critical', 'unknown')",
            name=op.f("ck_pi_problems_severity_inferred"),
        ),
        sa.CheckConstraint(
            "severity_stated IN ('low', 'medium', 'high', 'critical', 'unknown')",
            name=op.f("ck_pi_problems_severity_stated"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'corrected', 'merged', 'split', 'in_document', 'quoted', 'in_build', 'resolved', 'withdrawn')",
            name=op.f("ck_pi_problems_status"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_pi_problems_confidence_range")
        ),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_pi_problems_title_nonempty")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_problems_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "group_id"],
            [
                "pi_problem_groups.tenant_id",
                "pi_problem_groups.environment_id",
                "pi_problem_groups.id",
            ],
            name="fk_pi_problems_group_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_problems_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_problems_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_problems")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "number", name="uq_pi_problems_number"
        ),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_problems_scope_id"),
    )
    op.create_index(
        "ix_pi_problems_customer",
        "pi_problems",
        ["tenant_id", "environment_id", "customer_id", "status"],
        unique=False,
    )
    op.create_table(
        "pi_problem_links",
        sa.Column("from_id", sa.Uuid(), nullable=False),
        sa.Column("to_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("created_by", sa.String(length=8), server_default="pi", nullable=False),
        sa.Column("status", sa.String(length=12), server_default="suggested", nullable=False),
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
            "status IN ('suggested', 'confirmed', 'rejected')",
            name=op.f("ck_pi_problem_links_status"),
        ),
        sa.CheckConstraint(
            "type IN ('same_root_suspected', 'causes', 'same_area', 'duplicate_across_contacts', 'blocks')",
            name=op.f("ck_pi_problem_links_type"),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name=op.f("ck_pi_problem_links_confidence_range")
        ),
        sa.CheckConstraint("from_id <> to_id", name=op.f("ck_pi_problem_links_distinct")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "from_id"],
            ["pi_problems.tenant_id", "pi_problems.environment_id", "pi_problems.id"],
            name="fk_pi_problem_links_from_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "to_id"],
            ["pi_problems.tenant_id", "pi_problems.environment_id", "pi_problems.id"],
            name="fk_pi_problem_links_to_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_problem_links_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_problem_links_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_problem_links")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "from_id", "to_id", "type", name="uq_pi_problem_links"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_problem_links_scope_id"
        ),
    )
    op.create_table(
        "pi_problem_revisions",
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("by", sa.String(length=8), server_default="pi", nullable=False),
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
            "by IN ('pi', 'person', 'staff')", name=op.f("ck_pi_problem_revisions_by")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "problem_id"],
            ["pi_problems.tenant_id", "pi_problems.environment_id", "pi_problems.id"],
            name="fk_pi_problem_revisions_problem_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_problem_revisions_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_problem_revisions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_problem_revisions")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_problem_revisions_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "problem_id", "revision", name="uq_pi_problem_revisions"
        ),
    )


def downgrade() -> None:
    op.drop_table("pi_problem_revisions")
    op.drop_table("pi_problem_links")
    op.drop_index("ix_pi_problems_customer", table_name="pi_problems")
    op.drop_table("pi_problems")
    op.drop_table("pi_problem_groups")
