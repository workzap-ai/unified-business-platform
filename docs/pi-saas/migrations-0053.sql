-- Migration 0053 (FT-B2a): four nullable columns on pi_problems. Additive, reversible, no rewrite.
-- Apply this BEFORE deploying code that touches the new columns (a brain-mode note that carries
-- constraints, tried, a cause or an expected outcome). The columns are deferred in the ORM, so code
-- deployed earlier keeps working; it only fails when such a note is saved. Not applied anywhere yet.
-- Rollback (reviewed, not generated here): ALTER TABLE pi_problems DROP COLUMN expected_outcome,
-- DROP COLUMN cause, DROP COLUMN tried, DROP COLUMN constraints; then set alembic_version back to
-- '0052_pi_open_items'.

BEGIN;

-- Running upgrade 0052_pi_open_items -> 0053_pi_problem_requirements

ALTER TABLE pi_problems ADD COLUMN constraints JSONB;

ALTER TABLE pi_problems ADD COLUMN tried JSONB;

ALTER TABLE pi_problems ADD COLUMN cause JSONB;

ALTER TABLE pi_problems ADD COLUMN expected_outcome TEXT;

UPDATE alembic_version SET version_num='0053_pi_problem_requirements' WHERE alembic_version.version_num = '0052_pi_open_items';

COMMIT;

