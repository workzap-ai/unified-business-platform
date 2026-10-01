"""password reset tokens

Revision ID: 0016_password_reset_tokens
Revises: 0015_backfill_pi_bookings_work

Self-service "forgot password": a short-lived, single-use token emailed to the account
holder. Only its SHA-256 digest is stored, the same pattern as auth_sessions.token_hash.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_password_reset_tokens"
down_revision = "0015_backfill_pi_bookings_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
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
            name=op.f("fk_password_reset_tokens_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(
        "ix_password_reset_tokens_user", "password_reset_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
