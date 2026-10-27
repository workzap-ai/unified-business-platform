-- Turn on the expert advisor (independent, industry-expert solutions) for Workzap's own pi.
-- Paste into the Neon SQL editor yourself, only AFTER the code with `solution_source` is deployed
-- (otherwise the settings validator in the running code would refuse the unknown key).
-- Claude Code does not write to the real database.
--
-- Needs no migration. It merges two keys into response_rules.brain and never overwrites the rest:
--   solution_mode   = true      (the expert only runs when the solution ladder is on)
--   solution_source = "expert"  (default is "packs_first")
-- The judge call stays on (brain.expert_judge defaults to true). For lower cost and latency add
-- "expert_judge": false to the JSON below.
--
-- Targets Workzap's production, active environment by name, like enable-solution-mode-workzap.sql.

-- Step 1 (read-only): what is set now.
SELECT e.name AS env, e.kind, e.status,
       s.response_rules->>'pi_mode' AS pi_mode,
       s.response_rules->'brain' AS brain
FROM pi_settings s
JOIN tenants t ON t.id = s.tenant_id
JOIN environments e ON e.id = s.environment_id
WHERE t.name ILIKE '%workzap%'
ORDER BY e.kind;

-- Step 2: merge in the two keys.
UPDATE pi_settings s
SET response_rules = s.response_rules
  || jsonb_build_object(
       'brain',
       COALESCE(s.response_rules->'brain', '{}'::jsonb)
         || '{"solution_mode": true, "solution_source": "expert"}'::jsonb
     )
FROM tenants t, environments e
WHERE s.tenant_id = t.id
  AND s.environment_id = e.id
  AND t.name ILIKE '%workzap%'
  AND e.kind = 'production'
  AND e.status = 'active'
RETURNING s.id, t.name, e.name, e.kind, s.response_rules->'brain' AS brain;

-- If Step 2 returns more than one row, stop and tell Claude.

-- To undo: run Step 2 again with {"solution_source": "packs_first"}. Nothing else changes.
