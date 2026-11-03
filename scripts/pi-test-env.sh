# Point this shell at the disposable pi test database and refuse anything else.
# Source it from apps/api in Git Bash:  . ../../scripts/pi-test-env.sh
#
# apps/api/.env holds the REAL database. Alembic and pytest read it when DATABASE_URL is empty, so
# this script never leaves the variables empty: it either sets them to the test database on
# 127.0.0.1:55432 or fails loudly. Needs .cache/pi-saas/industry_connection.json (made by
# .cache/pi-saas/setup_db.py owner_industry_test industry_connection.json) and the cluster running:
#   .cache/postgres-portable/pgsql/bin/pg_ctl.exe -D .cache/pg-stage2/data -o "-p 55432" start

_root="$(cygpath -m "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")"
_python="$_root/.venv/Scripts/python.exe"
_conn="$_root/.cache/pi-saas/industry_connection.json"

unset DATABASE_URL MIGRATION_DATABASE_URL TEST_DATABASE_URL

if [ ! -f "$_conn" ]; then
  echo "pi-test-env: $_conn is missing; create the test database first (see this file)." >&2
  return 1 2>/dev/null || exit 1
fi

TEST_DATABASE_URL="$("$_python" -c "
import json
from urllib.parse import quote
d = json.load(open(r'$_conn'))
print(f\"postgresql+asyncpg://{d['user']}:{quote(d['password'], safe='')}@{d['host']}:{d['port']}/{d['database']}\")
")"

case "$TEST_DATABASE_URL" in
  *@127.0.0.1:55432/owner_industry_test) ;;
  *)
    unset TEST_DATABASE_URL
    echo "pi-test-env: refusing, the connection is not 127.0.0.1:55432/owner_industry_test." >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

export TEST_DATABASE_URL
export DATABASE_URL="$TEST_DATABASE_URL"
export MIGRATION_DATABASE_URL="$TEST_DATABASE_URL"
export REDIS_URL="redis://127.0.0.1:6379/0"
export APP_ENV=test
echo "pi-test-env: ${TEST_DATABASE_URL##*@}"
