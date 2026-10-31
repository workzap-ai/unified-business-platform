BEGIN;

-- Running upgrade 0053_pi_problem_requirements -> 0054_payment_idempotency

ALTER TABLE payments ADD COLUMN idempotency_key VARCHAR(128);

ALTER TABLE payments ADD COLUMN request_hash VARCHAR(64);

CREATE UNIQUE INDEX uq_payments_idempotency ON payments (tenant_id, environment_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

UPDATE alembic_version SET version_num='0054_payment_idempotency' WHERE alembic_version.version_num = '0053_pi_problem_requirements';

COMMIT;

