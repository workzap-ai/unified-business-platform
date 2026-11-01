-- 0055_pi_memory_ledgers. Additive: three new tables (pi_decisions, pi_rejections,
-- pi_document_texts) and three nullable columns on pi_brain_documents (delivered_at, verified_at,
-- verified_by). Apply before or after the code: readers are guarded. Brief ACCESS EXCLUSIVE lock on
-- pi_brain_documents (ADD COLUMN, catalogue only). Generated with:
--   alembic upgrade 0054_payment_idempotency:0055_pi_memory_ledgers --sql

BEGIN;

-- Running upgrade 0054_payment_idempotency -> 0055_pi_memory_ledgers

CREATE TABLE pi_decisions (
    customer_id UUID NOT NULL, 
    problem_id UUID, 
    kind VARCHAR(20) NOT NULL, 
    subject_ref VARCHAR(60) DEFAULT '' NOT NULL, 
    actor VARCHAR(8) DEFAULT 'owner' NOT NULL, 
    owner_words TEXT DEFAULT '' NOT NULL, 
    source_message_id UUID, 
    status VARCHAR(12) DEFAULT 'active' NOT NULL, 
    supersedes_id UUID, 
    valid_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    valid_to TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_decisions PRIMARY KEY (id), 
    CONSTRAINT ck_pi_decisions_kind CHECK (kind IN ('offer', 'yes', 'decline', 'revision_request', 'approval', 'document_approval', 'other')), 
    CONSTRAINT ck_pi_decisions_status CHECK (status IN ('active', 'superseded', 'withdrawn')), 
    CONSTRAINT ck_pi_decisions_actor CHECK (actor IN ('owner', 'staff', 'pi')), 
    CONSTRAINT fk_pi_decisions_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_decisions_problem_id FOREIGN KEY(tenant_id, environment_id, problem_id) REFERENCES pi_problems (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_decisions_supersedes_id FOREIGN KEY(tenant_id, environment_id, supersedes_id) REFERENCES pi_decisions (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_decisions_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_decisions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_decisions_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_decisions_source ON pi_decisions (tenant_id, environment_id, customer_id, kind, subject_ref, source_message_id) WHERE source_message_id IS NOT NULL;

CREATE UNIQUE INDEX uq_pi_decisions_active ON pi_decisions (tenant_id, environment_id, customer_id, subject_ref) WHERE status = 'active';

CREATE INDEX ix_pi_decisions_customer ON pi_decisions (tenant_id, environment_id, customer_id, status);

CREATE TABLE pi_rejections (
    customer_id UUID NOT NULL, 
    problem_id UUID, 
    target_kind VARCHAR(12) NOT NULL, 
    target_key VARCHAR(140) DEFAULT '' NOT NULL, 
    idea_hash VARCHAR(64) DEFAULT '' NOT NULL, 
    idea_text VARCHAR(500) DEFAULT '' NOT NULL, 
    owner_words TEXT DEFAULT '' NOT NULL, 
    reason VARCHAR(300) DEFAULT '' NOT NULL, 
    source_message_id UUID, 
    status VARCHAR(10) DEFAULT 'active' NOT NULL, 
    valid_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    valid_to TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_rejections PRIMARY KEY (id), 
    CONSTRAINT ck_pi_rejections_target_kind CHECK (target_kind IN ('idea', 'offer', 'document', 'price', 'option')), 
    CONSTRAINT ck_pi_rejections_status CHECK (status IN ('active', 'reversed', 'expired')), 
    CONSTRAINT fk_pi_rejections_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_rejections_problem_id FOREIGN KEY(tenant_id, environment_id, problem_id) REFERENCES pi_problems (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_rejections_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_rejections_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_rejections_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_rejections_source ON pi_rejections (tenant_id, environment_id, customer_id, target_kind, target_key, source_message_id) WHERE source_message_id IS NOT NULL;

CREATE INDEX ix_pi_rejections_customer ON pi_rejections (tenant_id, environment_id, customer_id, status);

CREATE TABLE pi_document_texts (
    customer_id UUID NOT NULL, 
    customer_file_id UUID NOT NULL, 
    ordinal INTEGER NOT NULL, 
    ref VARCHAR(80) NOT NULL, 
    text TEXT DEFAULT '' NOT NULL, 
    content_hash VARCHAR(64) DEFAULT '' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_document_texts PRIMARY KEY (id), 
    CONSTRAINT ck_pi_document_texts_ordinal CHECK (ordinal >= 0), 
    CONSTRAINT fk_pi_document_texts_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_document_texts_customer_file_id FOREIGN KEY(tenant_id, environment_id, customer_file_id) REFERENCES customer_files (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_document_texts_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_document_texts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_document_texts_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_document_texts_ref ON pi_document_texts (tenant_id, environment_id, customer_file_id, ordinal);

CREATE INDEX ix_pi_document_texts_customer ON pi_document_texts (tenant_id, environment_id, customer_id);

ALTER TABLE pi_brain_documents ADD COLUMN delivered_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE pi_brain_documents ADD COLUMN verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE pi_brain_documents ADD COLUMN verified_by UUID;

UPDATE alembic_version SET version_num='0055_pi_memory_ledgers' WHERE alembic_version.version_num = '0054_payment_idempotency';

COMMIT;

