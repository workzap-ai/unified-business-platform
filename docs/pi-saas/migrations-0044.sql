BEGIN;

-- Running upgrade 0043_pi_solution_learning -> 0044_pi_learning_gaps

ALTER TABLE pi_learning_examples ALTER COLUMN message_id DROP NOT NULL;

ALTER TABLE pi_learning_examples ADD COLUMN source VARCHAR(16) DEFAULT 'live' NOT NULL;

ALTER TABLE pi_question_arms ADD COLUMN industry VARCHAR(80) DEFAULT '' NOT NULL;

ALTER TABLE pi_learning_lessons ADD COLUMN canary_since TIMESTAMP WITH TIME ZONE;

ALTER TABLE pi_experiences ADD COLUMN lesson_ids JSONB DEFAULT '[]' NOT NULL;

CREATE TABLE pi_reply_audits (
    message_id UUID NOT NULL, 
    conversation_id UUID, 
    run_id UUID, 
    prompt_version VARCHAR(32) NOT NULL, 
    pack_versions JSONB NOT NULL, 
    lesson_ids JSONB NOT NULL, 
    example_ids JSONB NOT NULL, 
    arm_ids JSONB NOT NULL, 
    linter JSONB NOT NULL, 
    frozen BOOLEAN NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_reply_audits PRIMARY KEY (id), 
    CONSTRAINT fk_pi_reply_audits_message_id FOREIGN KEY(tenant_id, environment_id, message_id) REFERENCES pi_messages (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_reply_audits_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_reply_audits_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_reply_audits_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_reply_audits_msg UNIQUE (tenant_id, environment_id, message_id)
);

CREATE INDEX ix_pi_reply_audits_created ON pi_reply_audits (created_at);

UPDATE alembic_version SET version_num='0044_pi_learning_gaps' WHERE alembic_version.version_num = '0043_pi_solution_learning';

COMMIT;

