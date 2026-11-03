BEGIN;

-- Running upgrade 0042_pi_learning_more -> 0043_pi_solution_learning

CREATE TABLE pi_build_fit (
    industry_key VARCHAR(80) NOT NULL, 
    problem_key VARCHAR(60) NOT NULL, 
    catalogue_key VARCHAR(40) NOT NULL, 
    confirmed_by UUID, 
    project_id UUID, 
    outcome VARCHAR(16) NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_build_fit PRIMARY KEY (id), 
    CONSTRAINT fk_pi_build_fit_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_build_fit_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_build_fit_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_build_fit_problem ON pi_build_fit (industry_key, problem_key);

CREATE TABLE pi_catalogue_proposals (
    need_text TEXT NOT NULL, 
    industries JSONB NOT NULL, 
    count INTEGER NOT NULL, 
    evidence_ids JSONB NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    reviewer UUID, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_catalogue_proposals PRIMARY KEY (id), 
    CONSTRAINT fk_pi_catalogue_proposals_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_catalogue_proposals_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_catalogue_proposals_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_catprop_status ON pi_catalogue_proposals (status);

CREATE TABLE pi_idea_arms (
    arm_key VARCHAR(140) NOT NULL, 
    industry_key VARCHAR(80) NOT NULL, 
    problem_id VARCHAR(60) NOT NULL, 
    language VARCHAR(12) NOT NULL, 
    text VARCHAR(500) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    alpha FLOAT NOT NULL, 
    beta FLOAT NOT NULL, 
    uses INTEGER NOT NULL, 
    stats JSONB NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    traffic_cap FLOAT NOT NULL, 
    source VARCHAR(12) NOT NULL, 
    retired_reason VARCHAR(200) NOT NULL, 
    generic BOOLEAN NOT NULL, 
    version VARCHAR(12) NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_idea_arms PRIMARY KEY (id), 
    CONSTRAINT fk_pi_idea_arms_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_arms_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_idea_arms_key UNIQUE (tenant_id, environment_id, arm_key), 
    CONSTRAINT uq_pi_idea_arms_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_idea_arms_problem ON pi_idea_arms (industry_key, problem_id, language);

CREATE TABLE pi_solution_versions (
    industry_key VARCHAR(80) NOT NULL, 
    version VARCHAR(12) NOT NULL, 
    diff JSONB NOT NULL, 
    evidence JSONB NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    rolled_back_at TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_solution_versions PRIMARY KEY (id), 
    CONSTRAINT fk_pi_solution_versions_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_solution_versions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_solution_versions_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_solution_versions UNIQUE (tenant_id, environment_id, industry_key, version)
);

CREATE INDEX ix_pi_solution_versions_industry ON pi_solution_versions (industry_key, status);

CREATE TABLE pi_idea_feedback (
    idea_arm_id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    industry_key VARCHAR(80) NOT NULL, 
    language VARCHAR(12) NOT NULL, 
    signal VARCHAR(32) NOT NULL, 
    score INTEGER NOT NULL, 
    message_id UUID, 
    applied BOOLEAN NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_idea_feedback PRIMARY KEY (id), 
    CONSTRAINT fk_pi_idea_feedback_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_feedback_idea_arm_id FOREIGN KEY(tenant_id, environment_id, idea_arm_id) REFERENCES pi_idea_arms (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_feedback_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_feedback_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_idea_feedback_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_idea_feedback_arm ON pi_idea_feedback (idea_arm_id, applied);

CREATE TABLE pi_idea_sources (
    idea_arm_id UUID NOT NULL, 
    source VARCHAR(12) NOT NULL, 
    evidence_ids JSONB NOT NULL, 
    redaction_confidence NUMERIC(4, 3) NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_idea_sources PRIMARY KEY (id), 
    CONSTRAINT fk_pi_idea_sources_idea_arm_id FOREIGN KEY(tenant_id, environment_id, idea_arm_id) REFERENCES pi_idea_arms (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_sources_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_idea_sources_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_idea_sources_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_idea_sources_arm UNIQUE (tenant_id, environment_id, idea_arm_id)
);

CREATE TABLE pi_solution_memory (
    customer_id UUID NOT NULL, 
    conversation_id UUID, 
    industry_key VARCHAR(80) NOT NULL, 
    problem_id VARCHAR(60) NOT NULL, 
    idea_arm_id UUID NOT NULL, 
    given_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reaction VARCHAR(12) NOT NULL, 
    said_will_try BOOLEAN NOT NULL, 
    reported_result VARCHAR(12) NOT NULL, 
    builds_mentioned JSONB NOT NULL, 
    offer_status VARCHAR(12) NOT NULL, 
    document_id UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_solution_memory PRIMARY KEY (id), 
    CONSTRAINT fk_pi_solution_memory_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_solution_memory_idea_arm_id FOREIGN KEY(tenant_id, environment_id, idea_arm_id) REFERENCES pi_idea_arms (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_solution_memory_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_solution_memory_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_solution_memory UNIQUE (tenant_id, environment_id, customer_id, idea_arm_id), 
    CONSTRAINT uq_pi_solution_memory_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_solution_memory_customer ON pi_solution_memory (customer_id, given_at);

UPDATE alembic_version SET version_num='0043_pi_solution_learning' WHERE alembic_version.version_num = '0042_pi_learning_more';

COMMIT;

