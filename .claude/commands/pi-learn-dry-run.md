Dry-run the nightly learning for the last $ARGUMENTS days (default 1). Disposable database only.

1. `. ../../scripts/pi-test-env.sh` from `apps/api`; refuse anything but `127.0.0.1:55432/owner_industry_test`.
2. In a transaction that you roll back at the end, call `learning_nightly.run_workspace` for the
   workspace under test (see `tests/integration/test_pi_learning_loop.py` for the fixtures).
3. Report from the returned digest: examples curated, activated, canaried, promoted, rolled back or
   retired; question wordings added and retired; vocabulary lessons added; packs drafted; lessons
   with their risk labels (`learning.risk`); health numbers. Flag anything `learning.never_learn`
   would refuse. Nothing may be committed.
