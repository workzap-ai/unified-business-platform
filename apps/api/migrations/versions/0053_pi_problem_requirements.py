"""pi problem requirements: constraints, what was tried, the cause and the expected outcome

Revision ID: 0053_pi_problem_requirements
Revises: 0052_pi_open_items

FT-B2a (decision D2, schema in docs/pi-saas/pi-p1-schema-review.md). Four nullable columns on
`pi_problems`; NULL means "not said", so rows written before this migration read as empty and
nothing is backfilled. Adding a nullable column with no default is a catalogue change only (no
table rewrite, a brief lock). No index, no constraint, no data change.

Order of deployment: apply 0053 BEFORE deploying code that touches the new columns. The four
columns are deferred on the PiProblem mapper, so an ordinary read or write never selects them and
code deployed before 0053 keeps working; only a brain-mode note that carries one of these fields
(ProblemBook.update/create/confirm_cause) reads or writes them, and that needs the columns.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0053_pi_problem_requirements"
down_revision = "0052_pi_open_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pi_problems",
        sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "pi_problems", sa.Column("tried", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "pi_problems", sa.Column("cause", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("pi_problems", sa.Column("expected_outcome", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_problems", "expected_outcome")
    op.drop_column("pi_problems", "cause")
    op.drop_column("pi_problems", "tried")
    op.drop_column("pi_problems", "constraints")
