-- Turn on the opening warm-up (platform spec v1.4, Part 16) for Workzap's own pi.
-- With it on, a first-time owner who opens with a plain "Hi" gets: the AI line, ONE question about
-- the business (name and what it does), ONE ask for a public page, a safe quick look when a link is
-- given, "Page se ye samajh aaya: ..." and then the soft problem question. An owner who states a
-- problem in the first message skips all of it. Chats that already have noted problems are not
-- touched. Paste into the Neon SQL editor yourself. Claude Code does not write to the real database.
--
-- Needs the commit "Part 16 (second slice)" deployed on Railway first (an older deploy rejects the
-- unknown setting key `warmup` and keeps the old opening). No migration is needed: the profile and
-- the warm-up state live on the conversation brief.
-- Targets Workzap's production, active environment by name, like enable-map-thinking-workzap.sql.

-- Step 1 (read-only): what is set now.
SELECT e.name AS env, e.kind, e.status,
       s.response_rules->>'pi_mode' AS pi_mode,
       s.response_rules->'brain' AS brain
FROM pi_settings s
JOIN tenants t ON t.id = s.tenant_id
JOIN environments e ON e.id = s.environment_id
WHERE t.name ILIKE '%workzap%'
ORDER BY e.kind;

-- Step 2: merge in the flag (never overwrites the other brain settings).
UPDATE pi_settings s
SET response_rules = s.response_rules
  || jsonb_build_object(
       'brain',
       COALESCE(s.response_rules->'brain', '{}'::jsonb)
         || '{"warmup": true}'::jsonb
     )
FROM tenants t, environments e
WHERE s.tenant_id = t.id
  AND s.environment_id = e.id
  AND t.name ILIKE '%workzap%'
  AND e.kind = 'production'
  AND e.status = 'active'
RETURNING s.id, t.name, e.name, e.kind, s.response_rules->'brain' AS brain;

-- If Step 2 returns more than one row, stop and tell Claude.

-- To undo, run Step 2 again with {"warmup": false}. Chats already past the warm-up keep their state
-- (brief.warmup.step = done or skipped) and are not asked again.
--
-- Try it with a number that has never chatted with Workzap (or after workzap-fresh-start.sql):
--   1. "Hi"                               -> AI line + "naam kya hai, aur kis cheez ka hai?"
--   2. "mera clothing brand hai"          -> one ask for a website or Instagram link
--   3. "website nahi hai"  (or a link)    -> "Theek hai." / "Page se ye samajh aaya: ..." + the soft question
-- Instagram and Facebook links are not read (the owner is asked for a screenshot); that is intended.
