"""pi thinking step: move log and hypothesis ledger

Revision ID: 0049_pi_move_log
Revises: 0048_pi_map_parked_positions

Book 5 of the pi platform spec (3.5, 11.2), data only: `pi_move_log` (one row per pi message: the
move, the reason, whether it asked a question) and `pi_hypotheses` (the ledger of a conversation).
Written only when response_rules.brain.thinking is on.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049_pi_move_log"
down_revision = "0048_pi_map_parked_positions"
branch_labels = None
depends_on = None


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
        "pi_move_log",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("move", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("had_question", sa.Boolean(), server_default="false", nullable=False),
        *_base_columns(),
        _scoped_fk("pi_move_log", "conversation_id", "pi_conversations"),
        _scoped_fk("pi_move_log", "message_id", "pi_messages"),
        *_workspace_constraints("pi_move_log"),
    )
    op.create_index(
        "ix_pi_move_log_conversation",
        "pi_move_log",
        ["tenant_id", "environment_id", "conversation_id"],
    )
    op.create_table(
        "pi_hypotheses",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("evidence_for", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_against", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.String(length=8), server_default="low", nullable=False),
        sa.Column("cheapest_test", sa.String(length=300), server_default="", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("ignored", sa.Boolean(), server_default="false", nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')", name=op.f("ck_pi_hypotheses_confidence")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'confirmed', 'dropped')", name=op.f("ck_pi_hypotheses_status")
        ),
        _scoped_fk("pi_hypotheses", "conversation_id", "pi_conversations"),
        *_workspace_constraints("pi_hypotheses"),
    )
    op.create_index(
        "ix_pi_hypotheses_conversation",
        "pi_hypotheses",
        ["tenant_id", "environment_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_hypotheses_conversation", table_name="pi_hypotheses")
    op.drop_table("pi_hypotheses")
    op.drop_index("ix_pi_move_log_conversation", table_name="pi_move_log")
    op.drop_table("pi_move_log")
