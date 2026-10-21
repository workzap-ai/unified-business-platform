"""conversation flow state

Revision ID: 0034_conversation_flow_state
Revises: 0033_customer_industry

The state of a conversation in pi's brain flow (S0_NEW ... S13_IN_BUILD, X_*), and when
it last changed. Null for conversations that follow the standard flow: only workspaces
with response_rules.pi_mode = "brain" get a state.
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_conversation_flow_state"
down_revision = "0033_customer_industry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pi_conversations", sa.Column("flow_state", sa.String(32), nullable=True))
    op.add_column(
        "pi_conversations",
        sa.Column("flow_state_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pi_conversations", "flow_state_since")
    op.drop_column("pi_conversations", "flow_state")
