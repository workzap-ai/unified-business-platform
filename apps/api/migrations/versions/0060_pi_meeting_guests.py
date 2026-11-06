"""pi meeting guests: invite links so several people record their own microphone into one meeting

Revision ID: 0060_pi_meeting_guests
Revises: 0059_pi_meeting_media

docs/pi-saas/pi-meeting-brain.md, "PMB-4". Additive only: two new tables, nothing existing is renamed,
dropped or retyped, nothing is backfilled.

* `pi_meeting_invites`: the link a staff member copies. Only the hash of its token is stored, with an
  expiry, a revoke date and the most guests it admits (1 to 20).
* `pi_meeting_guests`: one person who opened an invite and agreed. Only the hash of their own token is
  stored; the row ties them to a speaker (`pi_meeting_participants`) and a slot (1 to 20) so lines
  from several people can be put back in the order they were spoken.

Code writes to them only when the workspace flag `response_rules.brain.meeting_guests` is on (default
off). Apply 0060 BEFORE deploying the code that uses it. Locks: CREATE TABLE takes none on existing
tables; the composite foreign keys take a brief SHARE ROW EXCLUSIVE lock on `pi_meetings`,
`pi_meeting_participants` and `environments`.
Rollback: downgrade drops both tables (invites and guest rows are lost; transcript lines already
stored stay); or revert the code and leave them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_pi_meeting_guests"
down_revision = "0059_pi_meeting_media"
branch_labels = None
depends_on = None

INVITES = "pi_meeting_invites"
GUESTS = "pi_meeting_guests"


def _base() -> list[sa.Column]:
    return [
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
    ]


def _scope(table: str) -> list[sa.schema.SchemaItem]:
    return [
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{table}_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{table}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{table}_scope_id"),
    ]


def _fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "environment_id", column],
        [f"{target}.tenant_id", f"{target}.environment_id", f"{target}.id"],
        name=f"fk_{table}_{column}",
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        INVITES,
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_guests", sa.SmallInteger(), server_default="20", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_base(),
        sa.CheckConstraint("max_guests BETWEEN 1 AND 20", name=op.f(f"ck_{INVITES}_max_guests")),
        _fk(INVITES, "meeting_id", "pi_meetings"),
        *_scope(INVITES),
    )
    op.create_index("uq_pi_meeting_invites_token", INVITES, ["token_hash"], unique=True)
    op.create_index(
        "ix_pi_meeting_invites_meeting", INVITES, ["tenant_id", "environment_id", "meeting_id"]
    )

    op.create_table(
        GUESTS,
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("invite_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=60), server_default="", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint("slot BETWEEN 1 AND 20", name=op.f(f"ck_{GUESTS}_slot")),
        _fk(GUESTS, "meeting_id", "pi_meetings"),
        _fk(GUESTS, "invite_id", INVITES),
        _fk(GUESTS, "participant_id", "pi_meeting_participants"),
        *_scope(GUESTS),
    )
    op.create_index("uq_pi_meeting_guests_token", GUESTS, ["token_hash"], unique=True)
    op.create_index(
        "uq_pi_meeting_guests_slot",
        GUESTS,
        ["tenant_id", "environment_id", "meeting_id", "slot"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_pi_meeting_guests_slot", table_name=GUESTS)
    op.drop_index("uq_pi_meeting_guests_token", table_name=GUESTS)
    op.drop_table(GUESTS)
    op.drop_index("ix_pi_meeting_invites_meeting", table_name=INVITES)
    op.drop_index("uq_pi_meeting_invites_token", table_name=INVITES)
    op.drop_table(INVITES)
