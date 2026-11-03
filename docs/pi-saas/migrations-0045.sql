BEGIN;

-- Running upgrade 0044_pi_learning_gaps -> 0045_pi_request_reasons

ALTER TABLE pi_staff_requests DROP CONSTRAINT ck_pi_staff_requests_kind;

ALTER TABLE pi_staff_requests DROP CONSTRAINT ck_pi_staff_requests_priority;

ALTER TABLE pi_staff_requests ADD CONSTRAINT ck_pi_staff_requests_kind CHECK (kind IN ('question', 'price', 'review_document', 'approve', 'meeting', 'other', 'human_requested', 'emergency', 'payment_detail_change', 'refund', 'complaint_about_pi', 'complaint_about_workzap', 'cant_help', 'legal_threat', 'abuse', 'press', 'partnership', 'enterprise_lead', 'existing_project', 'technical_failure', 'demo_request', 'jobs', 'vendor', 'deletion_request', 'price_request', 'payment_method', 'company_info', 'cancel_after_payment', 'quote_expired'));

ALTER TABLE pi_staff_requests ADD CONSTRAINT ck_pi_staff_requests_priority CHECK (priority IN ('normal', 'high', 'urgent'));

UPDATE alembic_version SET version_num='0045_pi_request_reasons' WHERE alembic_version.version_num = '0044_pi_learning_gaps';

COMMIT;

