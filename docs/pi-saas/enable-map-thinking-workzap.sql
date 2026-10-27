-- Turn on the problem map share and the thinking step (dials, moves) for Workzap's own pi.
-- box_offer stays OFF: the offer keeps following the accepted summary until the map flow has
-- been seen in real chats. Paste into the Neon SQL editor yourself. Claude Code does not write
-- to the real database.
--
-- Needs migrations 0047, 0048 and 0049 (all applied to the real database on 2026-10-27).
-- Targets the tenant "Workzap" (Production) by its settings id, never by name.

-- Step 1 (read-only): what is set now.
SELECT e.name AS env, e.kind, e.status,
       s.response_rules->>'pi_mode' AS pi_mode,
       s.response_rules->'brain' AS brain
FROM pi_settings s
JOIN tenants t ON t.id = s.tenant_id
JOIN environments e ON e.id = s.environment_id
WHERE t.name ILIKE '%workzap%'
ORDER BY e.kind;

-- Step 2: merge in the two flags (never overwrites the other brain settings).
UPDATE pi_settings s
SET response_rules = s.response_rules
  || jsonb_build_object(
       'brain',
       COALESCE(s.response_rules->'brain', '{}'::jsonb)
         || '{"map_share": true, "thinking": true}'::jsonb
     )
FROM tenants t, environments e
WHERE s.tenant_id = t.id
  AND s.environment_id = e.id
  AND s.id = 'ddb494a7-5e55-4e8b-944e-f111d0d034a0'  -- tenant "Workzap", Production, by id
RETURNING s.id, t.name, e.name, e.kind, s.response_rules->'brain' AS brain;

-- Step 2 is by id on purpose: the name pattern '%workzap%' also matches the DIFFERENT tenant
-- "Workzap.ai" (b29e78ba-2e6b-4772-8784-08842710858b). It must return exactly ONE row.

-- To undo, run Step 2 again with {"map_share": false, "thinking": false}.
