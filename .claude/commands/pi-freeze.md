Freeze or unfreeze pi's learning for one workspace. $ARGUMENTS ("true" or "false", then the tenant)

Learning is frozen unless `response_rules.brain.learning_frozen` is exactly `false`.

Do not write to the real database yourself. For "true" (freeze): give the user this SQL for their
Neon SQL editor, with the workspace's `pi_settings.id` filled in from a read-only lookup:
`UPDATE pi_settings SET response_rules = response_rules || jsonb_build_object('brain', COALESCE(response_rules->'brain','{}'::jsonb) || '{"learning_frozen":true}'::jsonb) WHERE id = '<id>';`
For "false": the same with `false`, but only if the user said so in this conversation. On a test
workspace you may use `PATCH /api/v1/pi/settings/response_rules` with
`{"value": {"brain": {"learning_frozen": <bool>}}}` against the disposable database.
Confirm afterwards (read-only) that the nightly run writes `{"frozen": true}` and changes nothing.
