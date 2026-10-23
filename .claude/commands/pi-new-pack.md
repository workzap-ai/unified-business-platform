Draft a new industry pack for: $ARGUMENTS

Use the `pack-writer` subagent. Follow the template of the existing packs in
`apps/api/app/modules/pi/packs/industry/*.json` (key, name, kind, signals, shape_facts, scope_rule,
vocabulary, problems mapped to `taxonomy` categories, questions by area, seasons, care, build_ideas,
exchange). Write it as a draft under `apps/api/app/modules/pi/packs/drafts/<key>.json`, never into
`packs/industry/`. The care sections and the scope rule are marked for human review and are never
final. Check every problem category with `taxonomy.KEYS` and every question with
`learning_packs.one_question`, and report what you invented versus took from the user.
