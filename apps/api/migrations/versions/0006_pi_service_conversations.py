"""Service briefs, durable followups and video messages.

Revision ID: 0006_pi_service_conversations
Revises: 0005_employee_onboarding
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_pi_service_conversations"
down_revision = "0005_employee_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_conversations",
        sa.Column("service_brief", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column("pi_conversations", sa.Column("followup_due_at", sa.DateTime(timezone=True)))
    op.create_index("ix_pi_conversations_followup_due", "pi_conversations", ["followup_due_at"])
    op.drop_constraint(op.f("ck_pi_messages_type"), "pi_messages", type_="check")
    op.create_check_constraint(
        "type",
        "pi_messages",
        "message_type IN ('text','audio','image','video','interactive','other')",
    )


def downgrade() -> None:
    op.execute("UPDATE pi_messages SET message_type = 'other' WHERE message_type = 'video'")
    op.drop_constraint(op.f("ck_pi_messages_type"), "pi_messages", type_="check")
    op.create_check_constraint(
        "type", "pi_messages", "message_type IN ('text','audio','image','interactive','other')"
    )
    op.drop_index("ix_pi_conversations_followup_due", table_name="pi_conversations")
    op.drop_column("pi_conversations", "followup_due_at")
    op.drop_column("pi_conversations", "service_brief")
