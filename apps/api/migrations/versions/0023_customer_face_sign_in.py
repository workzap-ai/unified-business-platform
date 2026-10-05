"""customer face sign-in

Revision ID: 0023_customer_face_sign_in
Revises: 0022_passkey_site

pi Customer's check after the WhatsApp code: up to three saved faces per number
(encrypted face codes only) and a wrong-tries counter with a lock.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_customer_face_sign_in"
down_revision = "0022_passkey_site"
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
        "customer_faces",
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code_encrypted", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *_record(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_faces")),
    )
    op.create_index("ix_customer_faces_phone", "customer_faces", ["phone"], unique=False)
    op.create_table(
        "customer_sign_in_locks",
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        *_record(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_sign_in_locks")),
        sa.UniqueConstraint("phone", name=op.f("uq_customer_sign_in_locks_phone")),
    )


def downgrade() -> None:
    op.drop_table("customer_sign_in_locks")
    op.drop_index("ix_customer_faces_phone", table_name="customer_faces")
    op.drop_table("customer_faces")
