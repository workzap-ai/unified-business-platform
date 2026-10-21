"""face sign-in

Revision ID: 0021_face_sign_in
Revises: 0020_customer_passkeys

The second sign-in step after the password: up to three saved faces per person
(encrypted face codes only, never photos), plus a wrong-tries counter and lock for
that step.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_face_sign_in"
down_revision = "0020_customer_passkeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_credentials",
        sa.Column("second_factor_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_credentials",
        sa.Column("second_factor_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "user_faces",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code_encrypted", sa.Text(), nullable=False),
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
            name=op.f("fk_user_faces_user_id_platform_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_faces")),
    )
    op.create_index("ix_user_faces_user", "user_faces", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_faces_user", table_name="user_faces")
    op.drop_table("user_faces")
    op.drop_column("user_credentials", "second_factor_locked_until")
    op.drop_column("user_credentials", "second_factor_failures")
