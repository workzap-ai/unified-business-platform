"""passkey site

Revision ID: 0022_passkey_site
Revises: 0021_face_sign_in

Remembers which website (Owner OS or the pi app) each passkey was made on, so the
fingerprint step only offers passkeys that can work on the current site.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_passkey_site"
down_revision = "0021_face_sign_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_passkeys",
        sa.Column("rp_id", sa.String(length=255), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_passkeys", "rp_id")
