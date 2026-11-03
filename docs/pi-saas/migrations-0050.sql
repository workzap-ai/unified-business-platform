BEGIN;

-- Running upgrade 0049_pi_move_log -> 0050_pi_business_profile

CREATE TABLE pi_business_profiles (
    customer_id UUID NOT NULL, 
    business_id UUID, 
    display_name VARCHAR(160) DEFAULT '' NOT NULL, 
    owner_address_name VARCHAR(80) DEFAULT '' NOT NULL, 
    industry_pack_id VARCHAR(80), 
    industry_confidence FLOAT, 
    industry_source VARCHAR(16), 
    what_they_do TEXT DEFAULT '' NOT NULL, 
    city_area VARCHAR(160) DEFAULT '' NOT NULL, 
    since_year INTEGER, 
    size_band VARCHAR(40) DEFAULT '' NOT NULL, 
    channels JSONB NOT NULL, 
    website_url VARCHAR(500) DEFAULT '' NOT NULL, 
    social_urls JSONB NOT NULL, 
    digital_flags JSONB NOT NULL, 
    language VARCHAR(16) DEFAULT '' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_business_profiles PRIMARY KEY (id), 
    CONSTRAINT ck_pi_business_profiles_industry_source CHECK (industry_source IS NULL OR industry_source IN ('owner', 'page', 'confirmed')), 
    CONSTRAINT fk_pi_business_profiles_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_business_profiles_business_id FOREIGN KEY(tenant_id, environment_id, business_id) REFERENCES pi_businesses (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_business_profiles_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_business_profiles_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_business_profiles_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_business_profiles_customer ON pi_business_profiles (tenant_id, environment_id, customer_id) WHERE business_id IS NULL;

CREATE UNIQUE INDEX uq_pi_business_profiles_business ON pi_business_profiles (tenant_id, environment_id, customer_id, business_id) WHERE business_id IS NOT NULL;

CREATE TABLE pi_profile_facts (
    profile_id UUID NOT NULL, 
    key VARCHAR(32) NOT NULL, 
    value TEXT NOT NULL, 
    source VARCHAR(8) NOT NULL, 
    confirmed BOOLEAN DEFAULT 'false' NOT NULL, 
    confirmed_at TIMESTAMP WITH TIME ZONE, 
    evidence_snippet VARCHAR(200) DEFAULT '' NOT NULL, 
    source_url VARCHAR(500) DEFAULT '' NOT NULL, 
    fetched_at TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_profile_facts PRIMARY KEY (id), 
    CONSTRAINT ck_pi_profile_facts_source CHECK (source IN ('owner', 'page', 'photo')), 
    CONSTRAINT ck_pi_profile_facts_key_nonempty CHECK (length(btrim(key)) > 0), 
    CONSTRAINT fk_pi_profile_facts_profile_id FOREIGN KEY(tenant_id, environment_id, profile_id) REFERENCES pi_business_profiles (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_profile_facts_key UNIQUE (tenant_id, environment_id, profile_id, key), 
    CONSTRAINT fk_pi_profile_facts_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_profile_facts_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_profile_facts_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE TABLE pi_page_snapshots (
    profile_id UUID NOT NULL, 
    url VARCHAR(500) NOT NULL, 
    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    content_hash VARCHAR(64) DEFAULT '' NOT NULL, 
    extracted JSONB NOT NULL, 
    status VARCHAR(24) DEFAULT 'ok' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_page_snapshots PRIMARY KEY (id), 
    CONSTRAINT fk_pi_page_snapshots_profile_id FOREIGN KEY(tenant_id, environment_id, profile_id) REFERENCES pi_business_profiles (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_page_snapshots_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_page_snapshots_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_page_snapshots_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_page_snapshots_profile ON pi_page_snapshots (tenant_id, environment_id, profile_id);

UPDATE alembic_version SET version_num='0050_pi_business_profile' WHERE alembic_version.version_num = '0049_pi_move_log';

COMMIT;

