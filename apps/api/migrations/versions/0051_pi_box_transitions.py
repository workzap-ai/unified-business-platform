"""pi Solution Box: the log of every lifecycle move

Revision ID: 0051_pi_box_transitions
Revises: 0050_pi_business_profile

Book 5 of the pi platform spec (5.3, 5.7 boxState), data only: `pi_box_transitions` (one row per
legal move of a Solution Box: from, to, who, why; the time is created_at) and the box's offer
time. Written only when response_rules.brain.box_offer is on. If a 0050 lands first, rebase
`down_revision` onto it (`alembic heads` must show one head).
"""

import sqlalchemy as sa
from alembic import op

revision = "0051_pi_box_transitions"
down_revision = "0050_pi_business_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_solution_boxes", sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "pi_box_transitions",
        sa.Column("box_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.String(length=16), nullable=False),
        sa.Column("to_state", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=8), nullable=False),
        sa.Column("actor_ref", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
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
        sa.CheckConstraint(
            "actor IN ('pi', 'owner', 'staff')", name=op.f("ck_pi_box_transitions_actor")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "box_id"],
            [
                "pi_solution_boxes.tenant_id",
                "pi_solution_boxes.environment_id",
                "pi_solution_boxes.id",
            ],
            name="fk_pi_box_transitions_box_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_box_transitions_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_box_transitions_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_box_transitions")),
        sa.UniqueConstraint(
            "tenant_id", "environment_id", "id", name="uq_pi_box_transitions_scope_id"
        ),
    )
    op.create_index(
        "ix_pi_box_transitions_box",
        "pi_box_transitions",
        ["tenant_id", "environment_id", "box_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_box_transitions_box", table_name="pi_box_transitions")
    op.drop_table("pi_box_transitions")
    op.drop_column("pi_solution_boxes", "offered_at")
