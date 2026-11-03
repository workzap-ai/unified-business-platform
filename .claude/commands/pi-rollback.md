Roll back a learning change. $ARGUMENTS (a `pi_learning_changes` id, "last" or "today")

Find the change(s) in `pi_learning_changes`. For an example, set it back to `retired` (or to
`candidate` if it was activated by mistake) and note the reason; for a question wording or lesson,
retire it with the staff routes (`POST /pi/brain-learning/examples/{id}/retire`,
`/arms/{id}/retire`, `/lessons/{id}/retire`, `/packs/{id}/retire`). Mark the change `rolled_back`
with a reason. On the real database only give the user the SQL; do not run it. Then run `/pi-eval`
and report.
