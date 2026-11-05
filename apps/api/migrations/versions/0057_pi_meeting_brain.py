"""pi meeting brain: meetings, participants, transcript segments, insights

Revision ID: 0057_pi_meeting_brain
Revises: 0056_pi_memory_ledgers

docs/pi-saas/pi-meeting-brain.md, PMB-1. Additive only: four new tables, nothing existing is renamed,
dropped or retyped, nothing is backfilled.

* `pi_meetings`: one recording or imported meeting, its consent, status, retention and storage key.
* `pi_meeting_participants`: speaker labels ("Speaker 1") and, only when a person maps one, the customer.
* `pi_meeting_segments`: the redacted transcript with timestamps; `tsv` is a stored generated column
  (config 'simple', so Urdu and Roman Urdu are matched as written) with a GIN index for search.
* `pi_meeting_insights`: what the analysis found, each with its basis (stated, inferred, estimate,
  recommendation), the transcript segments it came from, and its review state. A CHECK stops an
  inferred item from carrying an owner or a due date as if it had been stated.

Code reads none of it unless the workspace is in pi_mode "brain" with `brain.meeting_intel` on, and the
tables are empty. Apply 0057 BEFORE deploying the code (the routes need the tables).
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE ROW
EXCLUSIVE lock on `customers` and `environments`.
Rollback: downgrade drops the four tables (everything stored in them is lost); or revert the code and
leave them.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057_pi_meeting_brain"
down_revision = "0056_pi_memory_ledgers"
branch_labels = None
depends_on = None

SOURCES = "'upload', 'browser', 'native', 'zoom', 'meet'"
STATUSES = "'created', 'uploaded', 'transcribing', 'analysing', 'review', 'approved', 'failed'"
ROLES = "'customer', 'staff', 'other', 'unknown'"
KINDS = (
    "'summary', 'problem', 'requirement_explicit', 'requirement_implicit', 'root_cause', "
    "'impact', 'decision', 'commitment', 'action', 'question', 'risk', 'next_step'"
)
BASES = "'stated', 'inferred', 'estimate', 'recommendation'"
REVIEWS = "'pending', 'approved', 'rejected', 'edited'"


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
        "pi_meetings",
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), server_default="", nullable=False),
        sa.Column("source", sa.String(length=10), server_default="upload", nullable=False),
        sa.Column("status", sa.String(length=12), server_default="created", nullable=False),
        sa.Column("language", sa.String(length=12), server_default="", nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_by", sa.Uuid(), nullable=True),
        sa.Column("consent_note", sa.String(length=300), server_default="", nullable=False),
        sa.Column("recording_key", sa.String(length=300), nullable=True),
        sa.Column("recording_mime", sa.String(length=60), server_default="", nullable=False),
        sa.Column("recording_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_reason", sa.String(length=300), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_base(),
        sa.CheckConstraint(f"source IN ({SOURCES})", name=op.f("ck_pi_meetings_source")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=op.f("ck_pi_meetings_status")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_pi_meetings_attempts")),
        _fk("pi_meetings", "customer_id", "customers"),
        *_scope("pi_meetings"),
    )
    op.create_index(
        "uq_pi_meetings_external",
        "pi_meetings",
        ["tenant_id", "environment_id", "source", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.create_index(
        "ix_pi_meetings_status", "pi_meetings", ["tenant_id", "environment_id", "status"]
    )
    op.create_index(
        "ix_pi_meetings_customer",
        "pi_meetings",
        ["tenant_id", "environment_id", "customer_id", "created_at"],
    )

    op.create_table(
        "pi_meeting_participants",
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("role", sa.String(length=10), server_default="unknown", nullable=False),
        sa.Column("mapped_customer_id", sa.Uuid(), nullable=True),
        sa.Column("mapped_user_id", sa.Uuid(), nullable=True),
        *_base(),
        sa.CheckConstraint(f"role IN ({ROLES})", name=op.f("ck_pi_meeting_participants_role")),
        _fk("pi_meeting_participants", "meeting_id", "pi_meetings"),
        _fk("pi_meeting_participants", "mapped_customer_id", "customers"),
        *_scope("pi_meeting_participants"),
    )
    op.create_index(
        "uq_pi_meeting_participants_label",
        "pi_meeting_participants",
        ["tenant_id", "environment_id", "meeting_id", "label"],
        unique=True,
    )

    op.create_table(
        "pi_meeting_segments",
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("text_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', text)", persisted=True),
            nullable=True,
        ),
        *_base(),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_pi_meeting_segments_ordinal")),
        sa.CheckConstraint(
            "start_ms >= 0 AND end_ms >= start_ms", name=op.f("ck_pi_meeting_segments_span")
        ),
        _fk("pi_meeting_segments", "meeting_id", "pi_meetings"),
        _fk("pi_meeting_segments", "participant_id", "pi_meeting_participants"),
        *_scope("pi_meeting_segments"),
    )
    op.create_index(
        "uq_pi_meeting_segments_ordinal",
        "pi_meeting_segments",
        ["tenant_id", "environment_id", "meeting_id", "ordinal"],
        unique=True,
    )
    op.create_index(
        "ix_pi_meeting_segments_search", "pi_meeting_segments", ["tsv"], postgresql_using="gin"
    )

    op.create_table(
        "pi_meeting_insights",
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("basis", sa.String(length=14), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("edited_text", sa.Text(), server_default="", nullable=False),
        sa.Column("confidence", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "segment_refs",
            postgresql.ARRAY(sa.Integer()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("owner_label", sa.String(length=60), server_default="", nullable=False),
        sa.Column("due_text", sa.String(length=80), server_default="", nullable=False),
        sa.Column("review_status", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brain_ref", sa.String(length=60), server_default="", nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint(f"kind IN ({KINDS})", name=op.f("ck_pi_meeting_insights_kind")),
        sa.CheckConstraint(f"basis IN ({BASES})", name=op.f("ck_pi_meeting_insights_basis")),
        sa.CheckConstraint(
            f"review_status IN ({REVIEWS})", name=op.f("ck_pi_meeting_insights_review_status")
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 100", name=op.f("ck_pi_meeting_insights_confidence")
        ),
        sa.CheckConstraint(
            "(basis = 'stated') OR (owner_label = '' AND due_text = '')",
            name=op.f("ck_pi_meeting_insights_stated_only"),
        ),
        _fk("pi_meeting_insights", "meeting_id", "pi_meetings"),
        _fk("pi_meeting_insights", "participant_id", "pi_meeting_participants"),
        *_scope("pi_meeting_insights"),
    )
    op.create_index(
        "ix_pi_meeting_insights_meeting",
        "pi_meeting_insights",
        ["tenant_id", "environment_id", "meeting_id", "review_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_meeting_insights_meeting", table_name="pi_meeting_insights")
    op.drop_table("pi_meeting_insights")
    op.drop_index("ix_pi_meeting_segments_search", table_name="pi_meeting_segments")
    op.drop_index("uq_pi_meeting_segments_ordinal", table_name="pi_meeting_segments")
    op.drop_table("pi_meeting_segments")
    op.drop_index("uq_pi_meeting_participants_label", table_name="pi_meeting_participants")
    op.drop_table("pi_meeting_participants")
    op.drop_index("ix_pi_meetings_customer", table_name="pi_meetings")
    op.drop_index("ix_pi_meetings_status", table_name="pi_meetings")
    op.drop_index("uq_pi_meetings_external", table_name="pi_meetings")
    op.drop_table("pi_meetings")
