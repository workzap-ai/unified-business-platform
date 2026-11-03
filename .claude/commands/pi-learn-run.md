Run the nightly learning now for one workspace and print the digest. $ARGUMENTS (tenant)

Respect the freeze: a frozen workspace only gets a run row saying so. Use the staff API
`POST /api/v1/pi/brain-learning/run` (signed in as staff) on a test workspace, or
`learning_nightly.run_workspace` on the disposable database. Never run it against the real
database yourself; the user decides when production learns. Print the digest (`runs`) and the change
log (`changes`). HIGH-risk items are never applied here: they wait for a person (lessons in
`review`, drafted packs in `draft`).
