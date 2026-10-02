"""email verification

Revision ID: 0017_email_verification
Revises: 0016_password_reset_tokens

Self-service "verify your email": platform_users.email_verified_at (null until the
owner clicks the link) plus a short-lived, single-use token table, the same
digest-only shape as password_reset_tokens.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_email_verification"
down_revision = "0016_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "email_verification_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_email_verification_tokens_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_verification_tokens_token_hash")),
    )
    op.create_index(
        "ix_email_verification_tokens_user", "email_verification_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_user", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_column("platform_users", "email_verified_at")
