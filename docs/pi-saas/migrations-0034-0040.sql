BEGIN;

-- Running upgrade 0033_customer_industry -> 0034_conversation_flow_state

ALTER TABLE pi_conversations ADD COLUMN flow_state VARCHAR(32);

ALTER TABLE pi_conversations ADD COLUMN flow_state_since TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0034_conversation_flow_state' WHERE alembic_version.version_num = '0033_customer_industry';

-- Running upgrade 0034_conversation_flow_state -> 0035_pi_problems

CREATE TABLE pi_problem_groups (
    customer_id UUID NOT NULL, 
    category VARCHAR(40) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    created_by VARCHAR(8) DEFAULT 'pi' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_problem_groups PRIMARY KEY (id), 
    CONSTRAINT ck_pi_problem_groups_created_by CHECK (created_by IN ('pi', 'person')), 
    CONSTRAINT fk_pi_problem_groups_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_groups_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_groups_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_problem_groups_cat UNIQUE (tenant_id, environment_id, customer_id, category), 
    CONSTRAINT uq_pi_problem_groups_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE TABLE pi_problems (
    customer_id UUID NOT NULL, 
    conversation_id UUID, 
    group_id UUID, 
    number INTEGER NOT NULL, 
    title VARCHAR(120) NOT NULL, 
    title_local VARCHAR(200) DEFAULT '' NOT NULL, 
    summary TEXT DEFAULT '' NOT NULL, 
    user_words JSONB NOT NULL, 
    category VARCHAR(40) NOT NULL, 
    subtype VARCHAR(60) DEFAULT '' NOT NULL, 
    tags JSONB NOT NULL, 
    scope JSONB NOT NULL, 
    frequency JSONB NOT NULL, 
    since JSONB NOT NULL, 
    trigger VARCHAR(200) DEFAULT '' NOT NULL, 
    impact JSONB NOT NULL, 
    severity_stated VARCHAR(10) DEFAULT 'unknown' NOT NULL, 
    severity_inferred VARCHAR(10) DEFAULT 'unknown' NOT NULL, 
    severity_score NUMERIC(4, 1), 
    current_workaround TEXT DEFAULT '' NOT NULL, 
    systems_mentioned JSONB NOT NULL, 
    who_notices VARCHAR(200) DEFAULT '' NOT NULL, 
    person_believes_cause VARCHAR(300) DEFAULT '' NOT NULL, 
    requested_solution VARCHAR(300) DEFAULT '' NOT NULL, 
    status VARCHAR(16) DEFAULT 'draft' NOT NULL, 
    confidence NUMERIC(3, 2) NOT NULL, 
    source_message_ids JSONB NOT NULL, 
    revision INTEGER DEFAULT '1' NOT NULL, 
    pii_redacted BOOLEAN DEFAULT 'false' NOT NULL, 
    language VARCHAR(16), 
    merged_into UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_problems PRIMARY KEY (id), 
    CONSTRAINT ck_pi_problems_severity_inferred CHECK (severity_inferred IN ('low', 'medium', 'high', 'critical', 'unknown')), 
    CONSTRAINT ck_pi_problems_severity_stated CHECK (severity_stated IN ('low', 'medium', 'high', 'critical', 'unknown')), 
    CONSTRAINT ck_pi_problems_status CHECK (status IN ('draft', 'confirmed', 'corrected', 'merged', 'split', 'in_document', 'quoted', 'in_build', 'resolved', 'withdrawn')), 
    CONSTRAINT ck_pi_problems_confidence_range CHECK (confidence >= 0 AND confidence <= 1), 
    CONSTRAINT ck_pi_problems_title_nonempty CHECK (length(btrim(title)) > 0), 
    CONSTRAINT fk_pi_problems_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problems_group_id FOREIGN KEY(tenant_id, environment_id, group_id) REFERENCES pi_problem_groups (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problems_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problems_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_problems_number UNIQUE (tenant_id, environment_id, customer_id, number), 
    CONSTRAINT uq_pi_problems_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_problems_customer ON pi_problems (tenant_id, environment_id, customer_id, status);

CREATE TABLE pi_problem_links (
    from_id UUID NOT NULL, 
    to_id UUID NOT NULL, 
    type VARCHAR(32) NOT NULL, 
    confidence NUMERIC(3, 2) NOT NULL, 
    created_by VARCHAR(8) DEFAULT 'pi' NOT NULL, 
    status VARCHAR(12) DEFAULT 'suggested' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_problem_links PRIMARY KEY (id), 
    CONSTRAINT ck_pi_problem_links_status CHECK (status IN ('suggested', 'confirmed', 'rejected')), 
    CONSTRAINT ck_pi_problem_links_type CHECK (type IN ('same_root_suspected', 'causes', 'same_area', 'duplicate_across_contacts', 'blocks')), 
    CONSTRAINT ck_pi_problem_links_confidence_range CHECK (confidence >= 0 AND confidence <= 1), 
    CONSTRAINT ck_pi_problem_links_distinct CHECK (from_id <> to_id), 
    CONSTRAINT fk_pi_problem_links_from_id FOREIGN KEY(tenant_id, environment_id, from_id) REFERENCES pi_problems (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_links_to_id FOREIGN KEY(tenant_id, environment_id, to_id) REFERENCES pi_problems (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_links_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_links_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_problem_links UNIQUE (tenant_id, environment_id, from_id, to_id, type), 
    CONSTRAINT uq_pi_problem_links_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE TABLE pi_problem_revisions (
    problem_id UUID NOT NULL, 
    revision INTEGER NOT NULL, 
    diff JSONB NOT NULL, 
    reason VARCHAR(24) NOT NULL, 
    by VARCHAR(8) DEFAULT 'pi' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_problem_revisions PRIMARY KEY (id), 
    CONSTRAINT ck_pi_problem_revisions_by CHECK (by IN ('pi', 'person', 'staff')), 
    CONSTRAINT fk_pi_problem_revisions_problem_id FOREIGN KEY(tenant_id, environment_id, problem_id) REFERENCES pi_problems (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_revisions_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_problem_revisions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_problem_revisions_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_problem_revisions UNIQUE (tenant_id, environment_id, problem_id, revision)
);

UPDATE alembic_version SET version_num='0035_pi_problems' WHERE alembic_version.version_num = '0034_conversation_flow_state';

-- Running upgrade 0035_pi_problems -> 0036_customer_can_approve

ALTER TABLE customers ADD COLUMN can_approve BOOLEAN DEFAULT true NOT NULL;

UPDATE alembic_version SET version_num='0036_customer_can_approve' WHERE alembic_version.version_num = '0035_pi_problems';

-- Running upgrade 0036_customer_can_approve -> 0037_pi_brain_documents

CREATE TABLE pi_brain_documents (
    customer_id UUID NOT NULL, 
    conversation_id UUID, 
    offer_id UUID NOT NULL, 
    kind VARCHAR(8) NOT NULL, 
    number INTEGER NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    solution_id UUID, 
    problem_ids JSONB NOT NULL, 
    language VARCHAR(16) DEFAULT 'en' NOT NULL, 
    content JSONB NOT NULL, 
    content_en JSONB NOT NULL, 
    total NUMERIC(14, 2), 
    currency VARCHAR(3) DEFAULT '' NOT NULL, 
    valid_until DATE, 
    status VARCHAR(12) DEFAULT 'draft' NOT NULL, 
    drafted_by VARCHAR(8) DEFAULT 'pi' NOT NULL, 
    approved_by UUID, 
    approved_at TIMESTAMP WITH TIME ZONE, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    review_notes TEXT DEFAULT '' NOT NULL, 
    file_id UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_brain_documents PRIMARY KEY (id), 
    CONSTRAINT ck_pi_brain_documents_drafted_by CHECK (drafted_by IN ('pi', 'staff')), 
    CONSTRAINT ck_pi_brain_documents_kind CHECK (kind IN ('solution', 'quote')), 
    CONSTRAINT ck_pi_brain_documents_status CHECK (status IN ('draft', 'in_review', 'approved', 'sent', 'superseded')), 
    CONSTRAINT fk_pi_brain_documents_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_brain_documents_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_brain_documents_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_brain_documents_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_brain_documents_version UNIQUE (tenant_id, environment_id, kind, number, version)
);

CREATE INDEX ix_pi_brain_documents_offer ON pi_brain_documents (tenant_id, environment_id, offer_id);

CREATE INDEX ix_pi_brain_documents_status ON pi_brain_documents (tenant_id, environment_id, status);

UPDATE alembic_version SET version_num='0037_pi_brain_documents' WHERE alembic_version.version_num = '0036_customer_can_approve';

-- Running upgrade 0037_pi_brain_documents -> 0038_pi_brain_payments

CREATE TABLE pi_brain_payments (
    customer_id UUID NOT NULL, 
    conversation_id UUID, 
    quote_id UUID NOT NULL, 
    status VARCHAR(12) DEFAULT 'pending' NOT NULL, 
    claimed_at TIMESTAMP WITH TIME ZONE, 
    confirmed_by UUID, 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    reference VARCHAR(120) DEFAULT '' NOT NULL, 
    note TEXT DEFAULT '' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_brain_payments PRIMARY KEY (id), 
    CONSTRAINT ck_pi_brain_payments_status CHECK (status IN ('pending', 'claimed', 'confirmed', 'failed')), 
    CONSTRAINT fk_pi_brain_payments_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_brain_payments_quote_id FOREIGN KEY(tenant_id, environment_id, quote_id) REFERENCES pi_brain_documents (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_brain_payments_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_brain_payments_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_brain_payments_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_brain_payments_quote UNIQUE (tenant_id, environment_id, quote_id)
);

CREATE INDEX ix_pi_brain_payments_status ON pi_brain_payments (tenant_id, environment_id, status);

UPDATE alembic_version SET version_num='0038_pi_brain_payments' WHERE alembic_version.version_num = '0037_pi_brain_documents';

-- Running upgrade 0038_pi_brain_payments -> 0039_pi_quarantine

CREATE TABLE pi_quarantine (
    message_id UUID NOT NULL, 
    kinds JSONB NOT NULL, 
    payload TEXT NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_quarantine PRIMARY KEY (id), 
    CONSTRAINT fk_pi_quarantine_message_id FOREIGN KEY(tenant_id, environment_id, message_id) REFERENCES pi_messages (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_quarantine_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_quarantine_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_quarantine_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_quarantine_expires ON pi_quarantine (expires_at);

UPDATE alembic_version SET version_num='0039_pi_quarantine' WHERE alembic_version.version_num = '0038_pi_brain_payments';

-- Running upgrade 0039_pi_quarantine -> 0040_pi_experiences

CREATE TABLE pi_experiences (
    message_id UUID NOT NULL, 
    conversation_id UUID NOT NULL, 
    situation JSONB NOT NULL, 
    signals JSONB NOT NULL, 
    reward INTEGER NOT NULL, 
    scored_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_experiences PRIMARY KEY (id), 
    CONSTRAINT fk_pi_experiences_conversation_id FOREIGN KEY(tenant_id, environment_id, conversation_id) REFERENCES pi_conversations (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_experiences_message_id FOREIGN KEY(tenant_id, environment_id, message_id) REFERENCES pi_messages (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_experiences_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_experiences_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_experiences_scope_id UNIQUE (tenant_id, environment_id, id), 
    CONSTRAINT uq_pi_experiences_msg UNIQUE (tenant_id, environment_id, message_id)
);

CREATE INDEX ix_pi_experiences_scored ON pi_experiences (scored_at);

UPDATE alembic_version SET version_num='0040_pi_experiences' WHERE alembic_version.version_num = '0039_pi_quarantine';

COMMIT;

