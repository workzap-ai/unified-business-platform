"""pi deal documents

Revision ID: 0026_pi_deal_documents
Revises: 0024_pi_customer_share_prefs

The deal flow: customer-facing proposal and invoice links (accept, ask for changes,
pay) and each business's automation switches for what happens after "accepted".
"""

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0026_pi_deal_documents"
down_revision = "0024_pi_customer_share_prefs"
branch_labels = None
depends_on = None


def _workspace(table: str) -> list[Any]:
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f(f"fk_{table}_tenant_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name=f"fk_{table}_environment",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("tenant_id", "environment_id", "id", name=f"uq_{table}_scope_id"),
    ]


def upgrade() -> None:
    op.create_table(
        "pi_documents",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("message_text", sa.Text(), server_default="", nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.String(length=16), nullable=True),
        sa.Column("response_note", sa.Text(), server_default="", nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *_workspace("pi_documents"),
        sa.UniqueConstraint("token_hash", name="uq_pi_documents_token_hash"),
        sa.CheckConstraint("kind IN ('proposal', 'invoice')", name=op.f("ck_pi_documents_kind")),
        sa.CheckConstraint(
            "delivery IN ('pending', 'sent', 'waiting', 'manual', 'failed')",
            name=op.f("ck_pi_documents_delivery"),
        ),
        sa.CheckConstraint(
            "response IS NULL OR response IN ('accepted', 'changes', 'rejected')",
            name=op.f("ck_pi_documents_response"),
        ),
    )
    op.create_index(
        "ix_pi_documents_quote", "pi_documents", ["tenant_id", "environment_id", "quote_id"]
    )
    op.create_index(
        "ix_pi_documents_waiting", "pi_documents", ["tenant_id", "customer_id", "delivery"]
    )
    op.create_table(
        "pi_deal_settings",
        sa.Column("auto_order", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_invoice", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auto_payment_request", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("thank_you_on_paid", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("payment_method", sa.String(length=16), server_default="auto", nullable=False),
        sa.Column("template_name", sa.String(length=512), server_default="", nullable=False),
        sa.Column("template_language", sa.String(length=16), server_default="", nullable=False),
        *_workspace("pi_deal_settings"),
        sa.UniqueConstraint("tenant_id", "environment_id", name="uq_pi_deal_settings_scope"),
        sa.CheckConstraint(
            "payment_method IN ('auto', 'stripe', 'bank_transfer', 'mobile_wallet', 'cash')",
            name=op.f("ck_pi_deal_settings_payment_method"),
        ),
    )


def downgrade() -> None:
    op.drop_table("pi_deal_settings")
    op.drop_index("ix_pi_documents_waiting", table_name="pi_documents")
    op.drop_index("ix_pi_documents_quote", table_name="pi_documents")
    op.drop_table("pi_documents")
