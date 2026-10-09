"""pi request desk

Revision ID: 0030_pi_request_desk
Revises: 0029_customer_files

Ask Owner becomes a request desk: pi raises requests of a kind (question, price, review a
document, approve, meeting) with links to the lead, quote and file; the team answers
with a note for pi, and pi replies to the customer itself.
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_pi_request_desk"
down_revision = "0029_customer_files"
branch_labels = None
depends_on = None

TABLE = "pi_staff_requests"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("kind", sa.String(length=24), server_default="question", nullable=False)
    )
    op.add_column(
        TABLE, sa.Column("priority", sa.String(length=8), server_default="normal", nullable=False)
    )
    op.add_column(TABLE, sa.Column("lead_id", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("quote_id", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("file_id", sa.Uuid(), nullable=True))
    op.add_column(TABLE, sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f("ck_pi_staff_requests_status"), TABLE, type_="check")
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_status"),
        TABLE,
        "status IN ('open', 'answered', 'published', 'resolved', 'dismissed')",
    )
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_kind"),
        TABLE,
        "kind IN ('question', 'price', 'review_document', 'approve', 'meeting', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_priority"), TABLE, "priority IN ('normal', 'high')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_pi_staff_requests_priority"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_pi_staff_requests_kind"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_pi_staff_requests_status"), TABLE, type_="check")
    op.execute(f"UPDATE {TABLE} SET status = 'answered' WHERE status = 'resolved'")
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_status"),
        TABLE,
        "status IN ('open', 'answered', 'published', 'dismissed')",
    )
    for column in ("resolved_at", "file_id", "quote_id", "lead_id", "priority", "kind"):
        op.drop_column(TABLE, column)
