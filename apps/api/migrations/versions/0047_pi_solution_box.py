"""pi solution box and engagement-engine fields

Revision ID: 0047_pi_solution_box
Revises: 0046_pi_business

Book 5 of the pi platform spec (data only): shared map versions, the Solution Box and its lifecycle,
and the log of offer decisions. pi_problems gains goal_verb and raised_voluntarily; pi_problem_links
gains evidence (owner_said | pi_inferred | confirmed), filled from the existing status
(suggested -> pi_inferred, confirmed -> confirmed, rejected -> pi_inferred) so nothing is lost, and
the link types widen with worsens, competes, same_root and symptom_of (the old types stay).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0047_pi_solution_box"
down_revision = "0046_pi_business"
branch_labels = None
depends_on = None

OLD_LINK_TYPES = (
    "'same_root_suspected', 'causes', 'same_area', 'duplicate_across_contacts', 'blocks'"
)
NEW_LINK_TYPES = OLD_LINK_TYPES + ", 'worsens', 'competes', 'same_root', 'symptom_of'"
STATES = (
    "'collecting', 'ready', 'offered', 'drafting', 'in_review', 'sent', 'accepted', "
    "'declined', 'changes_asked', 'revised'"
)


def _base_columns() -> list[sa.Column]:
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


def _workspace_constraints(table: str) -> list[sa.schema.SchemaItem]:
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


def _scoped_fk(table: str, column: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "environment_id", column],
        [f"{target}.tenant_id", f"{target}.environment_id", f"{target}.id"],
        name=f"fk_{table}_{column}",
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "pi_map_versions",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared_message_id", sa.Uuid(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint("version >= 1", name=op.f("ck_pi_map_versions_version_positive")),
        _scoped_fk("pi_map_versions", "customer_id", "customers"),
        *_workspace_constraints("pi_map_versions"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "version", name="uq_pi_map_versions"
        ),
    )
    op.create_table(
        "pi_solution_boxes",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="collecting", nullable=False),
        sa.Column("map_version_id", sa.Uuid(), nullable=True),
        sa.Column("owner_ranking", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("parent_box_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer", sa.String(length=120), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(f"state IN ({STATES})", name=op.f("ck_pi_solution_boxes_state")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_pi_solution_boxes_version_positive")),
        _scoped_fk("pi_solution_boxes", "customer_id", "customers"),
        *_workspace_constraints("pi_solution_boxes"),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "customer_id", "version", name="uq_pi_solution_boxes"
        ),
    )
    # the two references into tables of the same scope need the scope_id unique keys to exist
    op.create_foreign_key(
        "fk_pi_solution_boxes_map_version_id",
        "pi_solution_boxes",
        "pi_map_versions",
        ["tenant_id", "environment_id", "map_version_id"],
        ["tenant_id", "environment_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_pi_solution_boxes_parent_box_id",
        "pi_solution_boxes",
        "pi_solution_boxes",
        ["tenant_id", "environment_id", "parent_box_id"],
        ["tenant_id", "environment_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_pi_solution_boxes_customer",
        "pi_solution_boxes",
        ["tenant_id", "environment_id", "customer_id"],
    )
    op.create_table(
        "pi_offer_log",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("rule", sa.String(length=2), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint("rule IN ('R1', 'R2', 'R3', 'B')", name=op.f("ck_pi_offer_log_rule")),
        _scoped_fk("pi_offer_log", "conversation_id", "pi_conversations"),
        *_workspace_constraints("pi_offer_log"),
    )
    op.create_index(
        "ix_pi_offer_log_conversation",
        "pi_offer_log",
        ["tenant_id", "environment_id", "conversation_id"],
    )

    op.add_column("pi_problems", sa.Column("goal_verb", sa.String(length=24), nullable=True))
    op.add_column(
        "pi_problems",
        sa.Column("raised_voluntarily", sa.Boolean(), server_default="false", nullable=False),
    )

    op.add_column(
        "pi_problem_links",
        sa.Column("evidence", sa.String(length=12), server_default="pi_inferred", nullable=False),
    )
    op.execute("UPDATE pi_problem_links SET evidence = 'confirmed' WHERE status = 'confirmed'")
    op.create_check_constraint(
        op.f("ck_pi_problem_links_evidence"),
        "pi_problem_links",
        "evidence IN ('owner_said', 'pi_inferred', 'confirmed')",
    )
    op.drop_constraint(op.f("ck_pi_problem_links_type"), "pi_problem_links", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_problem_links_type"), "pi_problem_links", f"type IN ({NEW_LINK_TYPES})"
    )


def downgrade() -> None:
    # links of the new types cannot exist under the old constraint: they are removed
    op.execute(
        "DELETE FROM pi_problem_links WHERE type IN "
        "('worsens', 'competes', 'same_root', 'symptom_of')"
    )
    op.drop_constraint(op.f("ck_pi_problem_links_type"), "pi_problem_links", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_problem_links_type"), "pi_problem_links", f"type IN ({OLD_LINK_TYPES})"
    )
    op.drop_constraint(op.f("ck_pi_problem_links_evidence"), "pi_problem_links", type_="check")
    op.drop_column("pi_problem_links", "evidence")
    op.drop_column("pi_problems", "raised_voluntarily")
    op.drop_column("pi_problems", "goal_verb")
    op.drop_index("ix_pi_offer_log_conversation", table_name="pi_offer_log")
    op.drop_table("pi_offer_log")
    op.drop_index("ix_pi_solution_boxes_customer", table_name="pi_solution_boxes")
    op.drop_table("pi_solution_boxes")
    op.drop_table("pi_map_versions")
