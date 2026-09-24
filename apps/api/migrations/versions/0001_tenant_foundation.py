"""Global users and tenant-owned organization foundation.

Revision ID: 0001_tenant_foundation
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_tenant_foundation"
down_revision = None
branch_labels = None
depends_on = None


def record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def tenant_column() -> sa.Column:
    return sa.Column(
        "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "platform_users",
        *record_columns(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint("email"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="status"),
        sa.CheckConstraint(
            "email = lower(btrim(email)) AND position('@' in email) > 1", name="email_normalized"
        ),
        sa.CheckConstraint("length(btrim(display_name)) > 0", name="display_name_nonempty"),
    )
    op.create_table(
        "tenants",
        *record_columns(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint("slug"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="status"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        sa.CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    )
    op.create_table(
        "tenant_memberships",
        *record_columns(),
        tenant_column(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("platform_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_memberships_tenant_id"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="status"),
    )
    op.create_index(
        "ix_memberships_user_status_tenant",
        "tenant_memberships",
        ["user_id", "status", "tenant_id"],
    )
    op.create_table(
        "branches",
        *record_columns(),
        tenant_column(),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_branches_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_branches_tenant_code"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        sa.CheckConstraint("code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="code_format"),
    )
    op.create_index("ix_branches_tenant_name_id", "branches", ["tenant_id", "name", "id"])
    op.create_table(
        "departments",
        *record_columns(),
        tenant_column(),
        sa.Column("branch_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_departments_tenant_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_departments_tenant_code"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "branch_id"], ["branches.tenant_id", "branches.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name="name_nonempty"),
        sa.CheckConstraint("code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="code_format"),
    )
    op.create_index("ix_departments_tenant_branch", "departments", ["tenant_id", "branch_id"])
    op.create_index("ix_departments_tenant_name_id", "departments", ["tenant_id", "name", "id"])


def downgrade() -> None:
    op.drop_table("departments")
    op.drop_table("branches")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("platform_users")
