Show pi's current health for one workspace. $ARGUMENTS (a tenant name; default Workzap)

Read only. Use the read-only helpers in `.cache/` (they force IPv4 and never print the connection
string) or the staff API `GET /api/v1/pi/brain-health?days=1` and `GET /api/v1/pi/brain-learning/*`
if you are signed in. Never write to the real database; the user applies SQL.

Report: the workspace's `pi_mode` and `learning_frozen`, conversations in the last 24 hours, average
reward, confusion, correction and opt-out rates, rule breaks (must be 0; a `rule_break` signal in
`pi_experiences` is a defect), learning changes promoted and rolled back (`pi_learning_changes`),
lessons waiting for review, drafted packs waiting, and anything needing a person. Say what you could
not check.
