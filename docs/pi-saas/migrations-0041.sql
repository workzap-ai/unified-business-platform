BEGIN;

-- Running upgrade 0040_pi_experiences -> 0041_pi_learning

CREATE TABLE pi_learning_changes (
    kind VARCHAR(32) NOT NULL, 
    speed VARCHAR(8) NOT NULL, 
    risk VARCHAR(8) NOT NULL, 
    target_id UUID, 
    before JSONB NOT NULL, 
    after JSONB NOT NULL, 
    evidence JSONB NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    reason VARCHAR(300) NOT NULL, 
    decided_by UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_learning_changes PRIMARY KEY (id), 
    CONSTRAINT fk_pi_learning_changes_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learning_changes_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_learning_changes_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_learning_changes_created ON pi_learning_changes (created_at);

CREATE TABLE pi_learning_runs (
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    frozen BOOLEAN NOT NULL, 
    digest JSONB NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_learning_runs PRIMARY KEY (id), 
    CONSTRAINT fk_pi_learning_runs_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learning_runs_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_learning_runs_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_learning_runs_started ON pi_learning_runs (started_at);

CREATE TABLE pi_question_arms (
    slot VARCHAR(24) NOT NULL, 
    language VARCHAR(12) NOT NULL, 
    text VARCHAR(300) NOT NULL, 
    alpha FLOAT NOT NULL, 
    beta FLOAT NOT NULL, 
    uses INTEGER NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    traffic_cap FLOAT NOT NULL, 
    created_by VARCHAR(12) NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_question_arms PRIMARY KEY (id), 
    CONSTRAINT fk_pi_question_arms_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_question_arms_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_question_arms_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_question_arms_slot ON pi_question_arms (slot, language);

CREATE TABLE pi_learning_examples (
    message_id UUID NOT NULL, 
    situation JSONB NOT NULL, 
    language VARCHAR(12) NOT NULL, 
    person_text TEXT NOT NULL, 
    reply_text TEXT NOT NULL, 
    reward INTEGER NOT NULL, 
    uses INTEGER NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    source_contacts JSONB NOT NULL, 
    redaction_confidence NUMERIC(4, 3) NOT NULL, 
    embedding JSONB, 
    retired_reason VARCHAR(200) NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_learning_examples PRIMARY KEY (id), 
    CONSTRAINT fk_pi_learning_examples_message_id FOREIGN KEY(tenant_id, environment_id, message_id) REFERENCES pi_messages (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learning_examples_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learning_examples_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_learning_examples_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_learning_examples_status ON pi_learning_examples (status, language);

ALTER TABLE pi_experiences ADD COLUMN arm_id UUID;

ALTER TABLE pi_experiences ADD COLUMN example_ids JSONB DEFAULT '[]'::jsonb NOT NULL;

UPDATE alembic_version SET version_num='0041_pi_learning' WHERE alembic_version.version_num = '0040_pi_experiences';

COMMIT;

