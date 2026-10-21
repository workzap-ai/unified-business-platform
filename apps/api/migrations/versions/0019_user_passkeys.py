"""user passkeys

Revision ID: 0019_user_passkeys
Revises: 0018_member_invite_tokens

Sign in with Face ID, Touch ID, Windows Hello or an Android fingerprint (WebAuthn
passkeys). Only each credential's public key is stored; biometrics stay on the device.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_user_passkeys"
down_revision = "0018_member_invite_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_passkeys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.String(length=1400), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("transports", sa.String(length=120), server_default="", nullable=False),
        sa.Column("backed_up", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_user_passkeys_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_user_passkeys_credential_id")),
    )
    op.create_index("ix_user_passkeys_user", "user_passkeys", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_passkeys_user", table_name="user_passkeys")
    op.drop_table("user_passkeys")
