"""customer files

Revision ID: 0029_customer_files
Revises: 0028_pi_deal_followups

Files kept for a customer in the database (documents and photos sent on WhatsApp, team
uploads, receipts), so attachments work without S3.
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_customer_files"
down_revision = "0028_pi_deal_followups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_files",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("uploaded_by_label", sa.String(length=80), nullable=False),
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
            "source IN ('whatsapp', 'upload', 'receipt')", name=op.f("ck_customer_files_source")
        ),
        sa.CheckConstraint(
            "size > 0 AND size <= 26214400", name=op.f("ck_customer_files_size_range")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_customer_files_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_customer_files_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "customer_id"],
            ["customers.tenant_id", "customers.environment_id", "customers.id"],
            name="fk_customer_files_customer_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_files")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_customer_files_scope_id"),
    )
    op.create_index(
        "ix_customer_files_customer",
        "customer_files",
        ["tenant_id", "environment_id", "customer_id", "created_at"],
    )
    op.create_index(
        "uq_customer_files_message",
        "customer_files",
        ["tenant_id", "environment_id", "message_id"],
        unique=True,
        postgresql_where=sa.text("message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_customer_files_ref",
        "customer_files",
        ["tenant_id", "environment_id", "ref_type", "ref_id"],
    )


def downgrade() -> None:
    op.drop_table("customer_files")
