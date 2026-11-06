"""pi meeting media: the saved audio and video parts of a recorded meeting

Revision ID: 0059_pi_meeting_media
Revises: 0058_backfill_pi_meetings_perms

docs/pi-saas/pi-meeting-brain.md. Additive only: two new tables, nothing existing is renamed, dropped
or retyped, nothing is backfilled.

* `pi_meeting_media`: one stored part of a meeting's recording (audio or video): its key, size, position
  in the meeting and the date until which it is kept. With a storage bucket connected (the S3 connection
  in Settings -> Integrations) the bytes live in that bucket and the key names the object.
* `pi_meeting_media_data`: the bytes of a part when NO bucket is connected (audio only, capped per
  meeting). Kept apart from the metadata so listing parts never reads audio.

Code writes to them only for a meeting whose recording the person chose to save. Apply 0059 BEFORE
deploying the code that saves recordings (the routes need the tables).
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE ROW
EXCLUSIVE lock on `pi_meetings` and `environments`.
Rollback: downgrade drops both tables (audio kept in the database is lost; files in a bucket stay there);
or revert the code and leave them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0059_pi_meeting_media"
down_revision = "0058_backfill_pi_meetings_perms"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_media"
DATA = "pi_meeting_media_data"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=5), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("mime", sa.String(length=60), server_default="", nullable=False),
        sa.Column("bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("offset_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("kind IN ('audio', 'video')", name=op.f(f"ck_{TABLE}_kind")),
        sa.CheckConstraint(
            "ordinal >= 0 AND bytes >= 0 AND offset_ms >= 0 AND duration_ms >= 0",
            name=op.f(f"ck_{TABLE}_ranges"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "meeting_id"],
            ["pi_meetings.tenant_id", "pi_meetings.environment_id", "pi_meetings.id"],
            name=f"fk_{TABLE}_meeting_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{TABLE}_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{TABLE}_scope_id"),
    )
    # a part is stored once: sending it again replaces the same row and the same object
    op.create_index(
        "uq_pi_meeting_media_part",
        TABLE,
        ["tenant_id", "environment_id", "meeting_id", "kind", "ordinal"],
        unique=True,
    )

    op.create_table(
        DATA,
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
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
            ["tenant_id", "environment_id", "media_id"],
            [f"{TABLE}.tenant_id", f"{TABLE}.environment_id", f"{TABLE}.id"],
            name=f"fk_{DATA}_media_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{DATA}_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{DATA}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{DATA}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{DATA}_scope_id"),
    )
    op.create_index(
        "uq_pi_meeting_media_data_media",
        DATA,
        ["tenant_id", "environment_id", "media_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_pi_meeting_media_data_media", table_name=DATA)
    op.drop_table(DATA)
    op.drop_index("uq_pi_meeting_media_part", table_name=TABLE)
    op.drop_table(TABLE)
