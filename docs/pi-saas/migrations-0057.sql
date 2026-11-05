-- 0057_pi_meeting_brain. Additive: four new empty tables (pi_meetings, pi_meeting_participants,
-- pi_meeting_segments, pi_meeting_insights). Apply after 0056_pi_memory_ledgers. Code and migration may
-- deploy in either order: until it is applied, a customer erase reports the meeting steps as skipped
-- (INCOMPLETE warning, no failure) and nothing else reads the tables. Brief SHARE ROW EXCLUSIVE lock on
-- customers and environments (foreign keys). Generated with: alembic upgrade 0056_pi_memory_ledgers:0057_pi_meeting_brain --sql

BEGIN;

-- Running upgrade 0056_pi_memory_ledgers -> 0057_pi_meeting_brain

CREATE TABLE pi_meetings (
    customer_id UUID, 
    title VARCHAR(200) DEFAULT '' NOT NULL, 
    source VARCHAR(10) DEFAULT 'upload' NOT NULL, 
    status VARCHAR(12) DEFAULT 'created' NOT NULL, 
    language VARCHAR(12) DEFAULT '' NOT NULL, 
    external_ref VARCHAR(200), 
    consent_at TIMESTAMP WITH TIME ZONE, 
    consent_by UUID, 
    consent_note VARCHAR(300) DEFAULT '' NOT NULL, 
    recording_key VARCHAR(300), 
    recording_mime VARCHAR(60) DEFAULT '' NOT NULL, 
    recording_bytes BIGINT DEFAULT '0' NOT NULL, 
    duration_ms INTEGER DEFAULT '0' NOT NULL, 
    held_at TIMESTAMP WITH TIME ZONE, 
    retention_until TIMESTAMP WITH TIME ZONE, 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    failure_reason VARCHAR(300) DEFAULT '' NOT NULL, 
    created_by UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_meetings PRIMARY KEY (id), 
    CONSTRAINT ck_pi_meetings_source CHECK (source IN ('upload', 'browser', 'native', 'zoom', 'meet')), 
    CONSTRAINT ck_pi_meetings_status CHECK (status IN ('created', 'uploaded', 'transcribing', 'analysing', 'review', 'approved', 'failed')), 
    CONSTRAINT ck_pi_meetings_attempts CHECK (attempts >= 0), 
    CONSTRAINT fk_pi_meetings_customer_id FOREIGN KEY(tenant_id, environment_id, customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meetings_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meetings_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_meetings_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_meetings_external ON pi_meetings (tenant_id, environment_id, source, external_ref) WHERE external_ref IS NOT NULL;

CREATE INDEX ix_pi_meetings_status ON pi_meetings (tenant_id, environment_id, status);

CREATE INDEX ix_pi_meetings_customer ON pi_meetings (tenant_id, environment_id, customer_id, created_at);

CREATE TABLE pi_meeting_participants (
    meeting_id UUID NOT NULL, 
    label VARCHAR(60) NOT NULL, 
    role VARCHAR(10) DEFAULT 'unknown' NOT NULL, 
    mapped_customer_id UUID, 
    mapped_user_id UUID, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_meeting_participants PRIMARY KEY (id), 
    CONSTRAINT ck_pi_meeting_participants_role CHECK (role IN ('customer', 'staff', 'other', 'unknown')), 
    CONSTRAINT fk_pi_meeting_participants_meeting_id FOREIGN KEY(tenant_id, environment_id, meeting_id) REFERENCES pi_meetings (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_participants_mapped_customer_id FOREIGN KEY(tenant_id, environment_id, mapped_customer_id) REFERENCES customers (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_participants_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_participants_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_meeting_participants_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_meeting_participants_label ON pi_meeting_participants (tenant_id, environment_id, meeting_id, label);

CREATE TABLE pi_meeting_segments (
    meeting_id UUID NOT NULL, 
    ordinal INTEGER NOT NULL, 
    start_ms INTEGER NOT NULL, 
    end_ms INTEGER NOT NULL, 
    participant_id UUID, 
    text TEXT DEFAULT '' NOT NULL, 
    text_hash VARCHAR(64) DEFAULT '' NOT NULL, 
    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_meeting_segments PRIMARY KEY (id), 
    CONSTRAINT ck_pi_meeting_segments_ordinal CHECK (ordinal >= 0), 
    CONSTRAINT ck_pi_meeting_segments_span CHECK (start_ms >= 0 AND end_ms >= start_ms), 
    CONSTRAINT fk_pi_meeting_segments_meeting_id FOREIGN KEY(tenant_id, environment_id, meeting_id) REFERENCES pi_meetings (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_segments_participant_id FOREIGN KEY(tenant_id, environment_id, participant_id) REFERENCES pi_meeting_participants (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_segments_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_segments_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_meeting_segments_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE UNIQUE INDEX uq_pi_meeting_segments_ordinal ON pi_meeting_segments (tenant_id, environment_id, meeting_id, ordinal);

CREATE INDEX ix_pi_meeting_segments_search ON pi_meeting_segments USING gin (tsv);

CREATE TABLE pi_meeting_insights (
    meeting_id UUID NOT NULL, 
    kind VARCHAR(24) NOT NULL, 
    basis VARCHAR(14) NOT NULL, 
    text TEXT DEFAULT '' NOT NULL, 
    edited_text TEXT DEFAULT '' NOT NULL, 
    confidence SMALLINT DEFAULT '0' NOT NULL, 
    segment_refs INTEGER[] DEFAULT '{}' NOT NULL, 
    participant_id UUID, 
    owner_label VARCHAR(60) DEFAULT '' NOT NULL, 
    due_text VARCHAR(80) DEFAULT '' NOT NULL, 
    review_status VARCHAR(10) DEFAULT 'pending' NOT NULL, 
    reviewed_by UUID, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    brain_ref VARCHAR(60) DEFAULT '' NOT NULL, 
    written_at TIMESTAMP WITH TIME ZONE, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_meeting_insights PRIMARY KEY (id), 
    CONSTRAINT ck_pi_meeting_insights_kind CHECK (kind IN ('summary', 'problem', 'requirement_explicit', 'requirement_implicit', 'root_cause', 'impact', 'decision', 'commitment', 'action', 'question', 'risk', 'next_step')), 
    CONSTRAINT ck_pi_meeting_insights_basis CHECK (basis IN ('stated', 'inferred', 'estimate', 'recommendation')), 
    CONSTRAINT ck_pi_meeting_insights_review_status CHECK (review_status IN ('pending', 'approved', 'rejected', 'edited')), 
    CONSTRAINT ck_pi_meeting_insights_confidence CHECK (confidence BETWEEN 0 AND 100), 
    CONSTRAINT ck_pi_meeting_insights_stated_only CHECK ((basis = 'stated') OR (owner_label = '' AND due_text = '')), 
    CONSTRAINT fk_pi_meeting_insights_meeting_id FOREIGN KEY(tenant_id, environment_id, meeting_id) REFERENCES pi_meetings (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_insights_participant_id FOREIGN KEY(tenant_id, environment_id, participant_id) REFERENCES pi_meeting_participants (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_insights_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_meeting_insights_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_meeting_insights_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_meeting_insights_meeting ON pi_meeting_insights (tenant_id, environment_id, meeting_id, review_status);

UPDATE alembic_version SET version_num='0057_pi_meeting_brain' WHERE alembic_version.version_num = '0056_pi_memory_ledgers';

COMMIT;

