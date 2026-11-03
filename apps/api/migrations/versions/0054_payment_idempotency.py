"""payment idempotency: an optional client key on a payment (BL-05)

Revision ID: 0054_payment_idempotency
Revises: 0053_pi_problem_requirements

Two nullable columns on `payments` and a partial unique index on (tenant_id, environment_id,
idempotency_key) where the key is set. Rows written before this migration, and payments recorded
without a key, keep NULL and are untouched; nothing is backfilled. Adding nullable columns with no
default is a catalogue change only, and the index covers only keyed rows, so it is built over an
(almost) empty set.

Order of deployment: apply 0054 BEFORE deploying code that writes payments with a key; ordinary
payments keep working before it (the two columns are deferred on the Payment mapper and left out
of an ordinary INSERT, so only a keyed payment names them).
Locks: ADD COLUMN takes a brief ACCESS EXCLUSIVE lock on payments (catalogue change only);
CREATE UNIQUE INDEX takes a short SHARE lock on payments (brief on an ordinary table).
Rollback: downgrade drops the index and the columns (any stored keys are lost, which only means a
replay is no longer recognised); or revert the code and leave the columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0054_payment_idempotency"
down_revision = "0053_pi_problem_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("payments", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_payments_idempotency",
        "payments",
        ["tenant_id", "environment_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_payments_idempotency", table_name="payments")
    op.drop_column("payments", "request_hash")
    op.drop_column("payments", "idempotency_key")
