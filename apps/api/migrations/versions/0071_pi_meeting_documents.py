"""pi meeting documents: the designed summary PDF and deck made from a meeting's approved insights

Revision ID: 0071_pi_meeting_documents
Revises: 0070_pi_meeting_bots

docs/pi-saas/pi-meeting-documents.md. Additive: one new table (`pi_meeting_documents`). Nothing
existing is renamed, dropped or backfilled. A row is a draft or an approved document of kind
`summary_pdf` or `deck_pptx`; its bytes (at most 4 MB, drawn from text the team already approved)
sit in `data`, which a list never reads.

Code writes to it only when the workspace flag `response_rules.brain.meeting_intel` is on, a person
asks for a document, and the meeting has approved insights. Apply 0071 BEFORE deploying the code
that uses it. Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a
brief SHARE ROW EXCLUSIVE lock on `pi_meetings` and `environments`.
Rollback: downgrade drops the table (the documents are lost; they can be made again from the
approved insights).
"""

import sqlalchemy as sa
from alembic import op

revision = "0071_pi_meeting_documents"
down_revision = "0070_pi_meeting_bots"
branch_labels = None
depends_on = None

TABLE = "pi_meeting_documents"


def upgrade() -> None:
    op.create_table(
        TABLE,
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
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=10), server_default="draft", nullable=False),
        sa.Column("title", sa.String(length=200), server_default="", nullable=False),
        sa.Column("language", sa.String(length=4), server_default="en", nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("insight_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dropped_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("kind IN ('summary_pdf', 'deck_pptx')", name=op.f(f"ck_{TABLE}_kind")),
        sa.CheckConstraint("status IN ('draft', 'approved')", name=op.f(f"ck_{TABLE}_status")),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 4000000", name=op.f(f"ck_{TABLE}_size")),
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
    op.create_index(
        "ix_pi_meeting_documents_meeting",
        TABLE,
        ["tenant_id", "environment_id", "meeting_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_meeting_documents_meeting", table_name=TABLE)
    op.drop_table(TABLE)
