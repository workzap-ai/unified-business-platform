BEGIN;

-- Running upgrade 0052_pi_open_items -> 0053_pi_problem_requirements

ALTER TABLE pi_problems ADD COLUMN constraints JSONB;

ALTER TABLE pi_problems ADD COLUMN tried JSONB;

ALTER TABLE pi_problems ADD COLUMN cause JSONB;

ALTER TABLE pi_problems ADD COLUMN expected_outcome TEXT;

UPDATE alembic_version SET version_num='0053_pi_problem_requirements' WHERE alembic_version.version_num = '0052_pi_open_items';

COMMIT;

