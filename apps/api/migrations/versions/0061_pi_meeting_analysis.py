"""pi meetings: where a long analysis has got to

Revision ID: 0061_pi_meeting_analysis
Revises: 0060_pi_meeting_guests

One nullable JSONB column on `pi_meetings` (`analysis_progress`): which parts of the transcript the
whole-meeting analysis has already read, so a long meeting on a rate-limited AI provider is finished
over several calls instead of failing as a whole. Additive only: nothing is rewritten or backfilled
(NULL means "no analysis in progress"). Apply 0061 BEFORE deploying the code that uses it.
Locks: ADD COLUMN of a nullable column without a default takes a brief ACCESS EXCLUSIVE lock and
rewrites nothing.
Rollback: downgrade drops the column (progress of analyses in flight is lost; the insights already
saved stay); or revert the code and leave it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0061_pi_meeting_analysis"
down_revision = "0060_pi_meeting_guests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pi_meetings", sa.Column("analysis_progress", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("pi_meetings", "analysis_progress")
