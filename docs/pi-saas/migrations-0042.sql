BEGIN;

-- Running upgrade 0041_pi_learning -> 0042_pi_learning_more

CREATE TABLE pi_learned_packs (
    key VARCHAR(60) NOT NULL, 
    title VARCHAR(120) NOT NULL, 
    content JSONB NOT NULL, 
    evidence JSONB NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    care_approved BOOLEAN NOT NULL, 
    decided_by UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_learned_packs PRIMARY KEY (id), 
    CONSTRAINT fk_pi_learned_packs_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learned_packs_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_learned_packs_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_learned_packs_status ON pi_learned_packs (status);

CREATE TABLE pi_learning_lessons (
    text TEXT NOT NULL, 
    scope JSONB NOT NULL, 
    risk VARCHAR(8) NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    created_by VARCHAR(12) NOT NULL, 
    author_id UUID, 
    decided_by UUID, 
    reason VARCHAR(300) NOT NULL, 
    uses INTEGER NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_learning_lessons PRIMARY KEY (id), 
    CONSTRAINT fk_pi_learning_lessons_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_learning_lessons_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_learning_lessons_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_learning_lessons_status ON pi_learning_lessons (status);

ALTER TABLE pi_learning_examples ADD COLUMN canary_since TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0042_pi_learning_more' WHERE alembic_version.version_num = '0041_pi_learning';

COMMIT;

