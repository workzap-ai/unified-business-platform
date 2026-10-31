-- 0054_payment_idempotency (BL-05). Apply 0054 BEFORE deploying code that writes payments with a
-- key; ordinary payments keep working before it.
-- ADD COLUMN takes a brief ACCESS EXCLUSIVE lock on payments; CREATE UNIQUE INDEX takes a short
-- SHARE lock on payments (brief on an ordinary table). Generated with:
--   alembic upgrade 0053_pi_problem_requirements:0054_payment_idempotency --sql

BEGIN;

-- Running upgrade 0053_pi_problem_requirements -> 0054_payment_idempotency

ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(128);

ALTER TABLE payments ADD COLUMN request_hash VARCHAR(64);

CREATE UNIQUE INDEX uq_payments_idempotency ON payments (tenant_id, environment_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

UPDATE alembic_version SET version_num='0054_payment_idempotency' WHERE alembic_version.version_num = '0053_pi_problem_requirements';

COMMIT;

