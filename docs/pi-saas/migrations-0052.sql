BEGIN;

-- Running upgrade 0051_pi_box_transitions -> 0052_pi_open_items

CREATE TABLE pi_open_items (
    conversation_id UUID NOT NULL, 
    customer_id UUID, 
    kind VARCHAR(20) NOT NULL, 
    key VARCHAR(40) DEFAULT '' NOT NULL, 
    text TEXT DEFAULT '' NOT NULL, 
    source_message_id UUID, 
    ref_id UUID, 
    language VARCHAR(12) DEFAULT 'en' NOT NULL, 
    status VARCHAR(10) DEFAULT 'open' NOT NULL, 
    due_at TIMESTAMP WITH TIME ZONE, 
    closed_at TIMESTAMP WITH TIME ZONE, 
    closed_reason VARCHAR(40), 
    surfaced_at TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_open_items PRIMARY KEY (id), 
    CONSTRAINT ck_pi_open_items_kind CHECK (kind IN ('owner_question', 'owner_request', 'pending_handoff', 'promised_followup')), 
    CONSTRAINT ck_pi_open_items_status CHECK (status IN ('open', 'answered', 'dropped')), 
    CONSTRAINT fk_pi_open_items_conversation_id FOREIGN KEY(tenant_id, environment_id, conversation_id) REFERENCES pi_conversations (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_open_items_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_open_items_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_open_items_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_open_items_open ON pi_open_items (tenant_id, environment_id, status, created_at);

CREATE INDEX ix_pi_open_items_conversation ON pi_open_items (tenant_id, environment_id, conversation_id);

UPDATE alembic_version SET version_num='0052_pi_open_items' WHERE alembic_version.version_num = '0051_pi_box_transitions';

COMMIT;

