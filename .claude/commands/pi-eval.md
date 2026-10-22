Run the full pi evaluation on the disposable database and report. $ARGUMENTS

1. From `apps/api` in Git Bash, run `. ../../scripts/pi-test-env.sh`. If it refuses or the cluster is
   down, start the cluster (command in the script's header) and try again. Never run the tests with a
   different database; `apps/api/.env` is the real one.
2. `PYTHONPATH=. ../../.venv/Scripts/python.exe -m alembic -c alembic.ini upgrade head`, then `check`
   (it must say "No new upgrade operations detected").
3. `../../.venv/Scripts/python.exe -m pytest tests/unit -q -p no:cacheprovider`.
4. `../../.venv/Scripts/python.exe -m pytest tests/integration/test_pi_brain_flow.py
   tests/integration/test_pi_brain_problems.py tests/integration/test_pi_brain_decisions.py
   tests/integration/test_pi_brain_documents.py tests/integration/test_pi_industry_context.py
   tests/integration/test_pi_service_conversations.py tests/integration/test_pi_reply_language.py -q`.
5. `ruff check app tests` and `mypy app/modules/pi`.
6. Print one table: suite, passed, failed. Name every failing test and the rule ID it protects
   (see `docs/pi-saas/pi-rule-coverage.md`). A failing rule-break test is a defect, not a flake: do
   not weaken the test or the rule, fix the code. Ignore unrelated failures only if they also fail on
   a clean checkout, and say so.
