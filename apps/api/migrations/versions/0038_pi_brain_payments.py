"""pi brain payments

Revision ID: 0038_pi_brain_payments
Revises: 0037_pi_brain_documents

Where a bank transfer for an approved quote stands (pending, claimed, confirmed, failed). Only
Workzap staff confirm a payment; the customer only claims it (pi Brain spec R-PAY-05, R-PAY-06).
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_pi_brain_payments"
down_revision = "0037_pi_brain_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_brain_payments",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="pending", nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference", sa.String(length=120), server_default="", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
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
            "status IN ('pending', 'claimed', 'confirmed', 'failed')",
            name=op.f("ck_pi_brain_payments_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_pi_brain_payments_customer_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "quote_id"],
            [
                "pi_brain_documents.tenant_id",
                "pi_brain_documents.environment_id",
                "pi_brain_documents.id",
            ],
            name="fk_pi_brain_payments_quote_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_brain_payments_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_brain_payments_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_brain_payments")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_brain_payments_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "quote_id", name="uq_pi_brain_payments_quote"
        ),
    )
    op.create_index(
        "ix_pi_brain_payments_status",
        "pi_brain_payments",
        ["tenant_id", "environment_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pi_brain_payments_status", table_name="pi_brain_payments")
    op.drop_table("pi_brain_payments")
