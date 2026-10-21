"""pi customer share links and prefs

Revision ID: 0024_pi_customer_share_prefs
Revises: 0023_customer_face_sign_in

pi Customer dashboard v2: view-only links a customer can forward (seven days, token
hash only) and the customer's own settings (language, when they last looked).
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_pi_customer_share_prefs"
down_revision = "0023_customer_face_sign_in"
branch_labels = None
depends_on = None


def _record() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "customer_share_links",
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views", sa.Integer(), server_default="0", nullable=False),
        *_record(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_share_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_customer_share_links_token_hash")),
    )
    op.create_index(
        "ix_customer_share_links_phone", "customer_share_links", ["phone"], unique=False
    )
    op.create_table(
        "customer_prefs",
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=16), server_default="auto", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_record(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_prefs")),
        sa.UniqueConstraint("phone", name=op.f("uq_customer_prefs_phone")),
    )


def downgrade() -> None:
    op.drop_table("customer_prefs")
    op.drop_index("ix_customer_share_links_phone", table_name="customer_share_links")
    op.drop_table("customer_share_links")
