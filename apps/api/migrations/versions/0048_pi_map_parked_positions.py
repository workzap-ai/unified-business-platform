"""pi problem map: a real parked status and stored node positions

Revision ID: 0048_pi_map_parked_positions
Revises: 0047_pi_solution_box

Book 5 of the pi platform spec (4.5, 4.4). A problem the owner told pi to leave ("ye masla chhor do")
was a `parked` tag; it is now the status `parked`, so it is kept out of the live summaries and counts
but stays on the map. Existing problems with the tag are moved in this migration (the tag is removed
from them, their other tags stay). pi_map_versions gains `positions` (node id -> [row, column]), the
places the owner saw the nodes at, so a new version keeps them where they were.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048_pi_map_parked_positions"
down_revision = "0047_pi_solution_box"
branch_labels = None
depends_on = None

OLD_STATUSES = (
    "'draft', 'confirmed', 'corrected', 'merged', 'split', 'in_document', 'quoted', 'in_build', "
    "'resolved', 'withdrawn'"
)
NEW_STATUSES = OLD_STATUSES + ", 'parked'"
# The statuses a parked tag could sit on (problems in play): only these become parked.
IN_PLAY = "'draft', 'confirmed', 'corrected', 'in_document', 'quoted', 'in_build'"
# A problem that carries the tag becomes parked; the tag goes, its other tags stay.
CONVERT_PARKED_TAGS = (
    "UPDATE pi_problems SET status = 'parked', tags = tags - 'parked' "
    f"WHERE status IN ({IN_PLAY}) AND tags @> '[\"parked\"]'::jsonb"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_pi_problems_status"), "pi_problems", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_problems_status"), "pi_problems", f"status IN ({NEW_STATUSES})"
    )
    op.execute(CONVERT_PARKED_TAGS)
    op.add_column(
        "pi_map_versions",
        sa.Column(
            "positions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("pi_map_versions", "positions")
    op.execute(
        "UPDATE pi_problems SET status = 'confirmed', tags = tags || '[\"parked\"]'::jsonb "
        "WHERE status = 'parked'"
    )
    op.drop_constraint(op.f("ck_pi_problems_status"), "pi_problems", type_="check")
    op.create_check_constraint(
        op.f("ck_pi_problems_status"), "pi_problems", f"status IN ({OLD_STATUSES})"
    )
