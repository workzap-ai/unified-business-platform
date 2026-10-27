-- Remove ONLY the `warmup` flag that enable-warmup-workzap.sql added by mistake to the different
-- tenant "Workzap.ai" (settings id b29e78ba-2e6b-4772-8784-08842710858b, Production). The name
-- pattern '%workzap%' matched both tenants. Nothing else in its response_rules is touched.
-- Paste into the Neon SQL editor yourself. Claude Code does not write to the real database.

-- Step 1 (read-only): confirm the id and the current brain settings.
SELECT s.id, t.name AS tenant, e.kind, s.response_rules->'brain' AS brain
FROM pi_settings s
JOIN tenants t ON t.id = s.tenant_id
JOIN environments e ON e.id = s.environment_id
WHERE s.id = 'b29e78ba-2e6b-4772-8784-08842710858b';

-- Step 2: drop the one key (`#-` deletes a path from a jsonb value).
UPDATE pi_settings
SET response_rules = response_rules #- '{brain,warmup}'
WHERE id = 'b29e78ba-2e6b-4772-8784-08842710858b'
RETURNING id, response_rules->'brain' AS brain;
-- Expect exactly ONE row, and a brain object without "warmup".
