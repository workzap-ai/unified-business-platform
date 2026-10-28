BEGIN;

-- Running upgrade 0050_pi_business_profile -> 0051_pi_box_transitions

ALTER TABLE pi_solution_boxes ADD COLUMN offered_at TIMESTAMP WITH TIME ZONE;

CREATE TABLE pi_box_transitions (
    box_id UUID NOT NULL, 
    from_state VARCHAR(16) NOT NULL, 
    to_state VARCHAR(16) NOT NULL, 
    actor VARCHAR(8) NOT NULL, 
    actor_ref VARCHAR(120), 
    reason TEXT DEFAULT '' NOT NULL, 
    tenant_id UUID NOT NULL, 
    environment_id UUID NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_pi_box_transitions PRIMARY KEY (id), 
    CONSTRAINT ck_pi_box_transitions_actor CHECK (actor IN ('pi', 'owner', 'staff')), 
    CONSTRAINT fk_pi_box_transitions_box_id FOREIGN KEY(tenant_id, environment_id, box_id) REFERENCES pi_solution_boxes (tenant_id, environment_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_box_transitions_environment FOREIGN KEY(tenant_id, environment_id) REFERENCES environments (tenant_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_pi_box_transitions_tenant_id_tenants FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_pi_box_transitions_scope_id UNIQUE (tenant_id, environment_id, id)
);

CREATE INDEX ix_pi_box_transitions_box ON pi_box_transitions (tenant_id, environment_id, box_id);

UPDATE alembic_version SET version_num='0051_pi_box_transitions' WHERE alembic_version.version_num = '0050_pi_business_profile';

COMMIT;

