BEGIN;

-- Running upgrade 0057_pi_meeting_brain -> 0058_backfill_pi_meetings_perms

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.read' FROM roles r WHERE r.is_system AND r.key = 'owner' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.read');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.record' FROM roles r WHERE r.is_system AND r.key = 'owner' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.record');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.approve' FROM roles r WHERE r.is_system AND r.key = 'owner' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.approve');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.delete' FROM roles r WHERE r.is_system AND r.key = 'owner' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.delete');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.read' FROM roles r WHERE r.is_system AND r.key = 'admin' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.read');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.record' FROM roles r WHERE r.is_system AND r.key = 'admin' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.record');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.approve' FROM roles r WHERE r.is_system AND r.key = 'admin' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.approve');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.delete' FROM roles r WHERE r.is_system AND r.key = 'admin' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.delete');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.read' FROM roles r WHERE r.is_system AND r.key = 'manager' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.read');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.record' FROM roles r WHERE r.is_system AND r.key = 'manager' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.record');

INSERT INTO role_permissions (id, tenant_id, role_id, permission) SELECT gen_random_uuid(), r.tenant_id, r.id, 'pi.meetings.approve' FROM roles r WHERE r.is_system AND r.key = 'manager' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission = 'pi.meetings.approve');

UPDATE alembic_version SET version_num='0058_backfill_pi_meetings_perms' WHERE alembic_version.version_num = '0057_pi_meeting_brain';

COMMIT;

