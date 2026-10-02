"""member invite tokens

Revision ID: 0018_member_invite_tokens
Revises: 0017_email_verification

Self-service "accept your invite": when a new member is added by email, the account
is created immediately (so roles can be assigned right away) with a placeholder
credential nobody can enter, and this token lets them set their first real password.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018_member_invite_tokens"
down_revision = "0018_payment_link_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_invite_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            ["user_id"],
            ["platform_users.id"],
            name=op.f("fk_member_invite_tokens_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_member_invite_tokens_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_invite_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_member_invite_tokens_token_hash")),
    )
    op.create_index(
        "ix_member_invite_tokens_user", "member_invite_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_member_invite_tokens_user", table_name="member_invite_tokens")
    op.drop_table("member_invite_tokens")
