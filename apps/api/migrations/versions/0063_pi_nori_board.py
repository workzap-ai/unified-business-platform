"""pi Nori Platform board: the number registry and the facts about nori cards

Revision ID: 0063_pi_nori_board
Revises: 0062_pi_nori_bridge_log

Two new tables (nothing existing is touched, no backfill):
  pi_nori_numbers  WhatsApp numbers the team added by hand so pi knows the sender is a nori user and
                   of which nori workspace. Unique per workspace and number.
  pi_nori_items    one row per board card of kind "nori": nori workspace, person, department, kind,
                   masked number, source and nori's own link. The card is a pi_tasks row.
Read or written only when a workspace has response_rules.nori_bridge.enabled and .board true.
Locks: CREATE TABLE and CREATE INDEX on new empty tables; no lock on any existing table.
Rollback: downgrade drops both tables (the registry and the card facts are lost; the cards stay as
plain team-board cards); or leave them.

NOTE: 0062 also exists on the pi/meeting-brain branch (pi_meeting_pi_mode). Whoever merges both must
re-chain one of them; this file follows pi_nori_bridge_log because that is the branch it was built on.
"""

import sqlalchemy as sa
from alembic import op

revision = "0063_pi_nori_board"
down_revision = "0062_pi_nori_bridge_log"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
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


def upgrade() -> None:
    op.create_table(
        "pi_nori_numbers",
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("workspace", sa.String(length=120), nullable=False),
        sa.Column("person", sa.String(length=120), server_default="", nullable=False),
        sa.Column("department", sa.String(length=80), server_default="", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("source", sa.String(length=10), server_default="manual", nullable=False),
        *_scope_columns(),
        sa.CheckConstraint("source IN ('manual', 'nori')", name=op.f("ck_pi_nori_numbers_source")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_nori_numbers_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_nori_numbers_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_nori_numbers")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_nori_numbers_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "phone", name="uq_pi_nori_numbers_phone"
        ),
    )

    op.create_table(
        "pi_nori_items",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("ref", sa.String(length=80), nullable=False),
        sa.Column("item_kind", sa.String(length=12), server_default="note", nullable=False),
        sa.Column("nori_workspace", sa.String(length=120), server_default="", nullable=False),
        sa.Column("person", sa.String(length=120), server_default="", nullable=False),
        sa.Column("department", sa.String(length=80), server_default="", nullable=False),
        sa.Column("phone_mask", sa.String(length=24), server_default="", nullable=False),
        sa.Column("source", sa.String(length=10), server_default="manual", nullable=False),
        sa.Column("url", sa.String(length=300), nullable=True),
        *_scope_columns(),
        sa.CheckConstraint(
            "item_kind IN ('feature', 'problem', 'feedback', 'module', 'question', 'change', 'note')",
            name=op.f("ck_pi_nori_items_item_kind"),
        ),
        sa.CheckConstraint(
            "source IN ('nori', 'whatsapp', 'manual')", name=op.f("ck_pi_nori_items_source")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "task_id"],
            ["pi_tasks.tenant_id", "pi_tasks.environment_id", "pi_tasks.id"],
            name="fk_pi_nori_items_task_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_nori_items_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_nori_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_nori_items")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_nori_items_scope_id"),
        sa.UniqueConstraint("tenant_id", "environment_id", "ref", name="uq_pi_nori_items_ref"),
    )
    op.create_index(
        "ix_pi_nori_items_task", "pi_nori_items", ["tenant_id", "environment_id", "task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_pi_nori_items_task", table_name="pi_nori_items")
    op.drop_table("pi_nori_items")
    op.drop_table("pi_nori_numbers")
