"""pi memory ledgers: decisions, rejections, document texts, delivered and verified markers

Revision ID: 0056_pi_memory_ledgers
Revises: 0055_pi_execution_runs

docs/pi-saas/pi-memory-entities-and-lifecycle.md, E1 to E3 and E6b (marker only). Additive only:

* `pi_decisions`: what the owner decided (offer, yes, decline, revision request, approval), with the
  words (redacted), the message it came from, validity and `supersedes_id`; a newer decision on the
  same subject supersedes the older one, the old row is kept.
* `pi_rejections`: what the owner said no to (an idea, the offer), read by the idea filter.
* `pi_document_texts`: the redacted text of a customer's file, one row per page, sheet or section.
* three nullable columns on `pi_brain_documents`: `delivered_at`, `verified_at`, `verified_by`. Set
  only by staff; NULL means "not marked".

Nothing is backfilled and nothing existing is renamed, dropped or retyped. The new tables are empty;
the new columns are catalogue-only (nullable, no default). Code does not read any of it unless the
workspace is in pi_mode "brain", and the readers tolerate the tables being absent.

Order of deployment: apply 0056 BEFORE deploying the code, or after: the readers are guarded (an
undefined table or column is reported as "unavailable", the writers run in a savepoint).
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE ROW
EXCLUSIVE lock on the referenced tables (customers, pi_problems, customer_files, environments);
ADD COLUMN takes a brief ACCESS EXCLUSIVE lock on pi_brain_documents (catalogue change only).
Rollback: downgrade drops the three tables and the three columns (everything stored in them is
lost); or revert the code and leave them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_pi_memory_ledgers"
down_revision = "0055_pi_execution_runs"
branch_labels = None
depends_on = None


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
        "pi_decisions",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("subject_ref", sa.String(length=60), server_default="", nullable=False),
        sa.Column("actor", sa.String(length=8), server_default="owner", nullable=False),
        sa.Column("owner_words", sa.Text(), server_default="", nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=12), server_default="active", nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint(
            "kind IN ('offer', 'yes', 'decline', 'revision_request', 'approval', "
            "'document_approval', 'other')",
            name=op.f("ck_pi_decisions_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'withdrawn')", name=op.f("ck_pi_decisions_status")
        ),
        sa.CheckConstraint("actor IN ('owner', 'staff', 'pi')", name=op.f("ck_pi_decisions_actor")),
        _fk("pi_decisions", "customer_id", "customers"),
        _fk("pi_decisions", "problem_id", "pi_problems"),
        _fk("pi_decisions", "supersedes_id", "pi_decisions"),
        *_scope("pi_decisions"),
    )
    op.create_index(
        "uq_pi_decisions_source",
        "pi_decisions",
        ["tenant_id", "environment_id", "customer_id", "kind", "subject_ref", "source_message_id"],
        unique=True,
        postgresql_where=sa.text("source_message_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pi_decisions_active",
        "pi_decisions",
        ["tenant_id", "environment_id", "customer_id", "subject_ref"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_pi_decisions_customer",
        "pi_decisions",
        ["tenant_id", "environment_id", "customer_id", "status"],
    )

    op.create_table(
        "pi_rejections",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=True),
        sa.Column("target_kind", sa.String(length=12), nullable=False),
        sa.Column("target_key", sa.String(length=140), server_default="", nullable=False),
        sa.Column("idea_hash", sa.String(length=64), server_default="", nullable=False),
        sa.Column("idea_text", sa.String(length=500), server_default="", nullable=False),
        sa.Column("owner_words", sa.Text(), server_default="", nullable=False),
        sa.Column("reason", sa.String(length=300), server_default="", nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=10), server_default="active", nullable=False),
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        *_base(),
        sa.CheckConstraint(
            "target_kind IN ('idea', 'offer', 'document', 'price', 'option')",
            name=op.f("ck_pi_rejections_target_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'reversed', 'expired')", name=op.f("ck_pi_rejections_status")
        ),
        _fk("pi_rejections", "customer_id", "customers"),
        _fk("pi_rejections", "problem_id", "pi_problems"),
        *_scope("pi_rejections"),
    )
    op.create_index(
        "uq_pi_rejections_source",
        "pi_rejections",
        [
            "tenant_id",
            "environment_id",
            "customer_id",
            "target_kind",
            "target_key",
            "source_message_id",
        ],
        unique=True,
        postgresql_where=sa.text("source_message_id IS NOT NULL"),
    )
    op.create_index(
        "ix_pi_rejections_customer",
        "pi_rejections",
        ["tenant_id", "environment_id", "customer_id", "status"],
    )

    op.create_table(
        "pi_document_texts",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("customer_file_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("content_hash", sa.String(length=64), server_default="", nullable=False),
        *_base(),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_pi_document_texts_ordinal")),
        _fk("pi_document_texts", "customer_id", "customers"),
        _fk("pi_document_texts", "customer_file_id", "customer_files"),
        *_scope("pi_document_texts"),
    )
    op.create_index(
        "uq_pi_document_texts_ref",
        "pi_document_texts",
        ["tenant_id", "environment_id", "customer_file_id", "ordinal"],
        unique=True,
    )
    op.create_index(
        "ix_pi_document_texts_customer",
        "pi_document_texts",
        ["tenant_id", "environment_id", "customer_id"],
    )

    op.add_column(
        "pi_brain_documents", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "pi_brain_documents", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("pi_brain_documents", sa.Column("verified_by", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_brain_documents", "verified_by")
    op.drop_column("pi_brain_documents", "verified_at")
    op.drop_column("pi_brain_documents", "delivered_at")
    op.drop_index("ix_pi_document_texts_customer", table_name="pi_document_texts")
    op.drop_index("uq_pi_document_texts_ref", table_name="pi_document_texts")
    op.drop_table("pi_document_texts")
    op.drop_index("ix_pi_rejections_customer", table_name="pi_rejections")
    op.drop_index("uq_pi_rejections_source", table_name="pi_rejections")
    op.drop_table("pi_rejections")
    op.drop_index("ix_pi_decisions_customer", table_name="pi_decisions")
    op.drop_index("uq_pi_decisions_active", table_name="pi_decisions")
    op.drop_index("uq_pi_decisions_source", table_name="pi_decisions")
    op.drop_table("pi_decisions")
