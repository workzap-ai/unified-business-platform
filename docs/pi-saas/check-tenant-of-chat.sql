-- Read-only (paste into the Neon SQL editor): which tenant and settings row answered the
-- "Dalal&Co." chat of 2026-10-28, and whether the opening warm-up is on for it.
-- Prints no phone number. Change '%dalal%' to look up another chat.

SELECT t.name AS tenant,
       e.kind AS environment,
       s.id AS settings_id,
       s.response_rules->>'pi_mode' AS pi_mode,
       s.response_rules->'brain'->>'warmup' AS warmup,
       s.response_rules->'brain'->>'solution_mode' AS solution_mode,
       pc.last_message_at
FROM customers c
JOIN pi_conversations pc
  ON pc.customer_id = c.id AND pc.tenant_id = c.tenant_id AND pc.environment_id = c.environment_id
JOIN tenants t ON t.id = c.tenant_id
JOIN environments e ON e.id = c.environment_id
LEFT JOIN pi_settings s ON s.tenant_id = c.tenant_id AND s.environment_id = c.environment_id
WHERE to_jsonb(c)::text ILIKE '%dalal%'
ORDER BY pc.last_message_at DESC
LIMIT 5;

-- How to read it:
--   tenant "Workzap" (ddb494a7-5e55-4e8b-944e-f111d0d034a0), warmup = true  -> the opening was
--     skipped by code: see the fix of 2026-10-29 (a "my friend shared your number" message).
--   tenant "Workzap.ai", or warmup is NULL/false  -> the opening is simply not switched on for
--     that tenant, and the old line came from the prompt (fixed the same day).
