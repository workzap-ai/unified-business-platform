"""customer passkeys

Revision ID: 0020_customer_passkeys
Revises: 0019_user_passkeys

pi Customer sign-in with Face ID or a fingerprint (WebAuthn passkeys), tied to the
customer's WhatsApp number. Only public keys are stored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_customer_passkeys"
down_revision = "0019_user_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_passkeys",
        sa.Column("phone", sa.String(length=20), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_customer_passkeys_credential_id")),
    )
    op.create_index("ix_customer_passkeys_phone", "customer_passkeys", ["phone"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_customer_passkeys_phone", table_name="customer_passkeys")
    op.drop_table("customer_passkeys")
