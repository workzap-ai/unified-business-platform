"""pi request reasons and the urgent priority

Revision ID: 0045_pi_request_reasons
Revises: 0044_pi_learning_gaps

Brain-mode escalations (spec 6.6) get a request kind of their own (the reason) and an "urgent"
priority for emergencies and a claimed bank-detail change, so each reason alerts the team and none
merges into an older open request.
"""

from alembic import op

revision = "0045_pi_request_reasons"
down_revision = "0044_pi_learning_gaps"
branch_labels = None
depends_on = None

TABLE = "pi_staff_requests"
OLD_KINDS = ("question", "price", "review_document", "approve", "meeting", "other")
NEW_KINDS = (
    "human_requested",
    "emergency",
    "payment_detail_change",
    "refund",
    "complaint_about_pi",
    "complaint_about_workzap",
    "cant_help",
    "legal_threat",
    "abuse",
    "press",
    "partnership",
    "enterprise_lead",
    "existing_project",
    "technical_failure",
    "demo_request",
    "jobs",
    "vendor",
    "deletion_request",
    "price_request",
    "payment_method",
    "company_info",
    "cancel_after_payment",
    "quote_expired",
)


def _list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_pi_staff_requests_kind"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_pi_staff_requests_priority"), TABLE, type_="check")
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_kind"), TABLE, f"kind IN ({_list((*OLD_KINDS, *NEW_KINDS))})"
    )
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_priority"), TABLE, "priority IN ('normal', 'high', 'urgent')"
    )


def downgrade() -> None:
    op.execute(f"UPDATE {TABLE} SET priority = 'high' WHERE priority = 'urgent'")
    op.execute(f"UPDATE {TABLE} SET kind = 'other' WHERE kind NOT IN ({_list(OLD_KINDS)})")
    op.drop_constraint(op.f("ck_pi_staff_requests_priority"), TABLE, type_="check")
    op.drop_constraint(op.f("ck_pi_staff_requests_kind"), TABLE, type_="check")
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_kind"), TABLE, f"kind IN ({_list(OLD_KINDS)})"
    )
    op.create_check_constraint(
        op.f("ck_pi_staff_requests_priority"), TABLE, "priority IN ('normal', 'high')"
    )
