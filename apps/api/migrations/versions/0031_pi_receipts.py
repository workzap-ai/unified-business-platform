"""pi receipts

Revision ID: 0031_pi_receipts
Revises: 0030_pi_request_desk

A PDF receipt for every payment, kept on the customer's files and sent to them (a
"receipt" document with its own page). What a receipt shows is set per business.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_pi_receipts"
down_revision = "0030_pi_request_desk"
branch_labels = None
depends_on = None

FLAGS = (
    "auto_receipt",
    "receipt_whatsapp",
    "receipt_email",
    "receipt_customer_details",
    "receipt_project_details",
    "receipt_line_items",
)


def upgrade() -> None:
    for flag in FLAGS:
        op.add_column(
            "pi_deal_settings",
            sa.Column(flag, sa.Boolean(), server_default="true", nullable=False),
        )
    op.add_column(
        "pi_deal_settings",
        sa.Column("receipt_footer", sa.String(length=500), server_default="", nullable=False),
    )
    op.add_column("pi_documents", sa.Column("file_id", sa.Uuid(), nullable=True))
    op.drop_constraint(op.f("ck_pi_documents_kind"), "pi_documents", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_documents_kind"), "pi_documents", "kind IN ('proposal', 'invoice', 'receipt')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM pi_documents WHERE kind = 'receipt'")
    op.drop_constraint(op.f("ck_pi_documents_kind"), "pi_documents", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_documents_kind"), "pi_documents", "kind IN ('proposal', 'invoice')"
    )
    op.drop_column("pi_documents", "file_id")
    op.drop_column("pi_deal_settings", "receipt_footer")
    for flag in reversed(FLAGS):
        op.drop_column("pi_deal_settings", flag)
