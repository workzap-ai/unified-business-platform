"""pi brain documents

Revision ID: 0037_pi_brain_documents
Revises: 0036_customer_can_approve

Solution documents and quotes in pi's brain flow: drafted, reviewed and approved by Workzap
before they reach the person; a revision is a new version (pi Brain spec, Part 5).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_pi_brain_documents"
down_revision = "0036_customer_can_approve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_brain_documents",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("solution_id", sa.Uuid(), nullable=True),
        sa.Column("problem_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("language", sa.String(length=16), server_default="en", nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_en", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="", nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="draft", nullable=False),
        sa.Column("drafted_by", sa.String(length=8), server_default="pi", nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), server_default="", nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=True),
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
            "drafted_by IN ('pi', 'staff')", name=op.f("ck_pi_brain_documents_drafted_by")
        ),
        sa.CheckConstraint(
            "kind IN ('solution', 'quote')", name=op.f("ck_pi_brain_documents_kind")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'approved', 'sent', 'superseded')",
            name=op.f("ck_pi_brain_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_brain_documents_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_brain_documents_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_brain_documents_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_brain_documents")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_brain_documents_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "environment_id",
            "kind",
            "number",
            "version",
            name="uq_pi_brain_documents_version",
        ),
    )
    op.create_index(
        "ix_pi_brain_documents_offer",
        "pi_brain_documents",
        ["tenant_id", "environment_id", "offer_id"],
        unique=False,
    )
    op.create_index(
        "ix_pi_brain_documents_status",
        "pi_brain_documents",
        ["tenant_id", "environment_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pi_brain_documents_status", table_name="pi_brain_documents")
    op.drop_index("ix_pi_brain_documents_offer", table_name="pi_brain_documents")
    op.drop_table("pi_brain_documents")
