"""The release gate for pi's automatic changes (pi Brain spec 8.5 job 9, steps 1 and 2; 10.3).

    python scripts/pi_release_gate.py [--sample 200] [--skip-tests] [--allow-empty]

Run it from apps/api on the disposable database (`. ../../scripts/pi-test-env.sh` first). It
refuses any other database: apps/api/.env is the real one.

1. Rule tests: the golden conversations and the red-team suite (and the Part 10 index) must pass
   100%.
2. Replay: a sample of the most recent stored conversations (default 200, from pi_experiences and
   pi_messages) is replayed through the reply linter and `learning_grader.release_gate`: any
   rule-break item, a mean below 1.7, or any language below 1.65 fails the gate.

Exit code 0 only when both steps pass; 1 otherwise (2 when it refuses to run). An empty database
fails step 2 ("nothing was graded") unless --allow-empty is given.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API))

TESTS = (
    "tests/unit/test_pi_redteam.py",
    "tests/unit/test_pi_redteam_more.py",
    "tests/unit/test_pi_part10_coverage.py",
    "tests/integration/test_pi_golden.py",
)
DISPOSABLE = "@127.0.0.1:55432/owner_industry_test"


def refuse(message: str) -> int:
    print(f"pi_release_gate: refusing: {message}", file=sys.stderr)
    return 2


def run_tests() -> bool:
    """Step 1: the golden and red-team selection."""
    command = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TESTS]
    print("step 1: golden and red-team tests")
    return subprocess.run(command, cwd=API, check=False).returncode == 0


async def replay(sample: int) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.modules.pi import learning_gate

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with AsyncSession(engine) as session:
            result = await learning_gate.replay(session, None, sample)
    finally:
        await engine.dispose()
    return result.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "")
    if not url.endswith(DISPOSABLE):
        return refuse("DATABASE_URL is not the disposable test database (see pi-test-env.sh)")
    tests_ok = True if args.skip_tests else run_tests()
    print("step 2: replay of", args.sample, "stored conversations")
    result = asyncio.run(replay(args.sample))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    replay_ok = bool(result["ok"]) or (args.allow_empty and result["conversations"] == 0)
    ok = tests_ok and replay_ok
    print("GATE PASSED" if ok else "GATE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
