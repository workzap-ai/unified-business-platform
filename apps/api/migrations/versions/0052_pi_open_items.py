"""pi open items: what the owner asked that is not finished

Revision ID: 0052_pi_open_items
Revises: 0051_pi_box_transitions

Platform spec v1.4, 17.7 and the 17.9 sketch (`open_item`): `pi_open_items`, kept until answered or
dropped by the owner, shown to staff by age. Additive only; nothing is read from it unless the
workspace is in pi_mode "brain".
"""

import sqlalchemy as sa
from alembic import op

revision = "0052_pi_open_items"
down_revision = "0051_pi_box_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pi_open_items",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=40), server_default="", nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=True),
        sa.Column("ref_id", sa.Uuid(), nullable=True),
        sa.Column("language", sa.String(length=12), server_default="en", nullable=False),
        sa.Column("status", sa.String(length=10), server_default="open", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(length=40), nullable=True),
        sa.Column("surfaced_at", sa.DateTime(timezone=True), nullable=True),
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
            "kind IN ('owner_question', 'owner_request', 'pending_handoff', 'promised_followup')",
            name=op.f("ck_pi_open_items_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'answered', 'dropped')", name=op.f("ck_pi_open_items_status")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "conversation_id"],
            [
                "pi_conversations.tenant_id",
                "pi_conversations.environment_id",
                "pi_conversations.id",
            ],
            name="fk_pi_open_items_conversation_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_pi_open_items_environment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pi_open_items_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pi_open_items")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name="uq_pi_open_items_scope_id"),
    )
    op.create_index(
        "ix_pi_open_items_open",
        "pi_open_items",
        ["tenant_id", "environment_id", "status", "created_at"],
    )
    op.create_index(
        "ix_pi_open_items_conversation",
        "pi_open_items",
        ["tenant_id", "environment_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_open_items_conversation", table_name="pi_open_items")
    op.drop_index("ix_pi_open_items_open", table_name="pi_open_items")
    op.drop_table("pi_open_items")
