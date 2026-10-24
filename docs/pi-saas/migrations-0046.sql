-- Migration 0046: pi business team model (spec 4.9, R-MEM-06).
-- Generated from `alembic upgrade 0045_pi_request_reasons:0046_pi_business --sql`, applied and
-- verified (round-tripped up/down, autogenerate confirms no further diff, no owner_customer_id
-- back-reference so customers/pi_businesses never form a foreign-key cycle) on the disposable
-- database. Paste into the Neon SQL editor when you are ready to run it on the real database.

BEGIN;

-- Running upgrade 0045_pi_request_reasons -> 0046_pi_business

CREATE TABLE pi_businesses (
    name VARCHAR(160) NOT NULL,
    name_key VARCHAR(160) NOT NULL,
    tenant_id UUID NOT NULL,
    environment_id UUID NOT NULL,
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_pi_businesses PRIMARY KEY (id),
    CONSTRAINT ck_pi_businesses_name_nonempty CHECK (length(btrim(name)) > 0),
    CONSTRAINT fk_pi_businesses_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_pi_businesses_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
    CONSTRAINT uq_pi_businesses_scope_id UNIQUE (tenant_id, environment_id, id),
    CONSTRAINT uq_pi_businesses_name UNIQUE (tenant_id, environment_id, name_key)
);

ALTER TABLE customers ADD COLUMN business_id UUID;

ALTER TABLE customers ADD COLUMN business_role VARCHAR(8);

ALTER TABLE customers ADD COLUMN pending_business_name VARCHAR(160);

ALTER TABLE customers ADD COLUMN shares_with_business BOOLEAN DEFAULT 'true' NOT NULL;

ALTER TABLE customers ADD COLUMN business_joined_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE customers ADD COLUMN business_disclosed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE customers ADD CONSTRAINT fk_customers_business_id FOREIGN KEY(tenant_id, environment_id, business_id) REFERENCES pi_businesses (tenant_id, environment_id, id) ON DELETE RESTRICT;

ALTER TABLE customers ADD CONSTRAINT ck_customers_business_role CHECK (business_role IS NULL OR business_role IN ('owner', 'admin', 'member'));

UPDATE alembic_version SET version_num='0046_pi_business' WHERE alembic_version.version_num = '0045_pi_request_reasons';

COMMIT;
