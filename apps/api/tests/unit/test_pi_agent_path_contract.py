"""Every step name pi's runtime writes into a run's `agent_path` must be one the web app's contract
allows: the inbox "Details" panel parses each run with a closed list, and one unknown name (like
"outage_queue" was) makes the whole panel fail with "Couldn't load this"."""

import re
from pathlib import Path

APPS = Path(__file__).resolve().parents[3]
RUNTIME = APPS / "api" / "app" / "modules" / "pi" / "runtime.py"
CONTRACT = APPS / "web" / "src" / "features" / "pi" / "contracts.generated.ts"
WRITES = re.compile(r"agent_path\s*(?:=|\+=)\s*\[([^\]]*)\]")
# a name written as a plain string: not the key of a lookup like state["path"]
NAME = re.compile(r'(?<![\[\w])"([a-z_]+)"(?!\])')


def test_every_step_the_runtime_writes_is_in_the_web_contract():
    written = {
        name
        for match in WRITES.finditer(RUNTIME.read_text(encoding="utf-8"))
        for name in NAME.findall(match.group(1))
    }
    assert {"router", "handoff", "outage_queue"} <= written  # the scan itself finds the steps
    allowed = set(re.findall(r'z\.literal\("([a-z_]+)"\)', CONTRACT.read_text(encoding="utf-8")))
    missing = sorted(written - allowed)
    assert not missing, (
        f"runtime.py writes agent_path steps {missing} that contracts.generated.ts does not allow: "
        "add them to RunStep in apps/web/src/features/pi/types.ts and run "
        "`node scripts/generate-pi-contracts.mjs` (then prettier) in apps/web"
    )
