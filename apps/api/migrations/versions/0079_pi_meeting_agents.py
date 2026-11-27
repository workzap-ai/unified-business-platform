"""pi meeting agents and Ask AI chats

Revision ID: 0079_pi_meeting_agents
Revises: 0078_pi_meeting_room_notes

Additive: three new tables (`pi_meeting_agents`, `pi_meeting_chats`, `pi_meeting_chat_messages`)
and one nullable column on `pi_meetings` (`agent_key`, no default, no rewrite). An agent is a name,
a look and a few lines of focus and tone a workspace wrote; a chat is one "Ask AI" conversation
with a meeting and its messages (redacted text, the cited lines). Nothing existing is renamed,
dropped or backfilled. Code reads the new column on `pi_meetings`, so apply 0079 BEFORE deploying.
Locks: CREATE TABLE takes none on existing tables; the composite foreign keys take a brief SHARE
ROW EXCLUSIVE lock on `pi_meetings` and `environments`.
Rollback: downgrade drops the tables and the column (chats and custom agents are lost).
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0079_pi_meeting_agents"
down_revision = "0078_pi_meeting_room_notes"
branch_labels = None
depends_on = None


def _base(table: str) -> list[Any]:
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


def _tail(table: str) -> list[Any]:
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


def upgrade() -> None:
    op.add_column("pi_meetings", sa.Column("agent_key", sa.String(40), nullable=True))

    agents = "pi_meeting_agents"
    op.create_table(
        agents,
        *_base(agents),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("tagline", sa.String(80), server_default="", nullable=False),
        sa.Column("icon", sa.String(20), server_default="sparkles", nullable=False),
        sa.Column("color", sa.String(12), server_default="green", nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_tail(agents),
    )
    op.create_index(
        "uq_pi_meeting_agents_name",
        agents,
        ["tenant_id", "environment_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    chats = "pi_meeting_chats"
    op.create_table(
        chats,
        *_base(chats),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("agent_key", sa.String(40), server_default="pi", nullable=False),
        sa.Column("title", sa.String(80), server_default="", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "meeting_id"],
            ["pi_meetings.tenant_id", "pi_meetings.environment_id", "pi_meetings.id"],
            name=f"fk_{chats}_meeting_id",
            ondelete="RESTRICT",
        ),
        *_tail(chats),
    )
    op.create_index(
        "ix_pi_meeting_chats_meeting",
        chats,
        ["tenant_id", "environment_id", "meeting_id", "updated_at"],
    )

    messages = "pi_meeting_chat_messages"
    op.create_table(
        messages,
        *_base(messages),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(9), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("found", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("partial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f(f"ck_{messages}_role")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id", "chat_id"],
            [f"{chats}.tenant_id", f"{chats}.environment_id", f"{chats}.id"],
            name=f"fk_{messages}_chat_id",
            ondelete="RESTRICT",
        ),
        *_tail(messages),
    )
    op.create_index(
        "ix_pi_meeting_chat_messages_chat",
        messages,
        ["tenant_id", "environment_id", "chat_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_pi_meeting_chat_messages_chat", table_name="pi_meeting_chat_messages")
    op.drop_table("pi_meeting_chat_messages")
    op.drop_index("ix_pi_meeting_chats_meeting", table_name="pi_meeting_chats")
    op.drop_table("pi_meeting_chats")
    op.drop_index("uq_pi_meeting_agents_name", table_name="pi_meeting_agents")
    op.drop_table("pi_meeting_agents")
    op.drop_column("pi_meetings", "agent_key")
