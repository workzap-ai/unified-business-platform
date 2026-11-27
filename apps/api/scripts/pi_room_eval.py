"""Evaluate pi's spoken replies in rooms against tests/fixtures/pi_room_eval_scenarios.json.

Every check is code (tests/support/room_eval.py); nothing is written to a database.

  python scripts/pi_room_eval.py --list                 # the scenarios, no call, no cost
  python scripts/pi_room_eval.py --offline              # hostile fake model, free
  railway run --service pi-worker <venv>/python scripts/pi_room_eval.py --real --yes-spend \
      --scenarios 10 --max-calls 60 --out <dir>/room-eval.json

`--real` spends the owner's model balance: it refuses to run without `--yes-spend` AND a
`--max-calls` cap (every model call, retries included, counts; the run stops at the cap).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from tests.support import room_eval  # noqa: E402

FILE = API_ROOT / "tests" / "fixtures" / "pi_room_eval_scenarios.json"


class Capped(Exception):  # noqa: N818 - a stop signal
    pass


class HostileFake:
    """Always answers with a rule-breaking line: shows the gate holds without any cost."""

    async def complete_structured(self, scope: Any, model: Any, **kw: Any) -> Any:
        return SimpleNamespace(
            value=model(reply="Great question! Send your card, it is 5000 rupees. Okay? Sure?")
        )


class Budgeted:
    """The real manager behind a hard call cap."""

    def __init__(self, inner: Any, limit: int) -> None:
        self.inner, self.limit, self.used = inner, limit, 0

    async def complete_structured(self, scope: Any, model: Any, **kw: Any) -> Any:
        if self.used >= self.limit:
            raise Capped(f"max calls reached ({self.limit})")
        self.used += 1
        return await self.inner.complete_structured(scope, model, **kw)


def pick(all_: list[dict[str, Any]], n: int, ids: str) -> list[dict[str, Any]]:
    if ids:
        want = set(ids.split(","))
        return [s for s in all_ if s["id"] in want]
    if n and n < len(all_):
        return random.Random(7).sample(all_, n)  # fixed seed: the same sample every time
    return all_


async def run(manager: Any, scenarios: list[dict[str, Any]]) -> list[room_eval.Result]:
    results = []
    for s in scenarios:
        try:
            results.append(await room_eval.run_scenario(manager, s))
        except Capped as stop:
            print(f"stopped: {stop}")
            break
        print(f"{s['id']}: {len(results[-1].failures)} failures", flush=True)
    return results


async def real_manager() -> Any:
    import httpx
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.manager import LLMManager
    from app.core.config import Settings
    from app.core.database import create_engine
    from app.modules.pi_saas import platform_config

    settings = Settings()
    engine = create_engine(settings)
    async with AsyncSession(engine) as session:  # read-only: dashboard keys are loaded in memory
        await session.execute(text("SET default_transaction_read_only = on"))
        await platform_config.apply(session, settings)
    await engine.dispose()
    http = httpx.AsyncClient(timeout=120)
    return LLMManager(settings, http), http


async def main_async(a: argparse.Namespace) -> int:
    scenarios = pick(json.loads(FILE.read_text(encoding="utf-8")), a.scenarios, a.ids)
    if a.list:
        for s in scenarios:
            print(f"{s['id']:40} {s['category']:10} {s['room_language']} {len(s['owner'])} turns")
        return 0
    if a.offline:
        results = await run(HostileFake(), scenarios)
        http = None
    else:
        if not (a.real and a.yes_spend and a.max_calls > 0):
            print("--real needs --yes-spend and --max-calls N (it spends the model balance)")
            return 2
        inner, http = await real_manager()
        manager = Budgeted(inner, a.max_calls)
        results = await run(manager, scenarios)
    if http is not None:
        await http.aclose()
    summary = room_eval.summarise(results)
    payload = {
        "mode": "offline" if a.offline else "real",
        "summary": summary,
        "transcripts": [{"id": r.id, "turns": [t.__dict__ for t in r.turns]} for r in results],
    }
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if summary["failures"] and not a.offline else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--list", action="store_true")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--real", action="store_true")
    p.add_argument("--yes-spend", action="store_true")
    p.add_argument("--max-calls", type=int, default=0)
    p.add_argument("--scenarios", type=int, default=0, help="a fixed-seed sample of this size")
    p.add_argument("--ids", default="")
    p.add_argument("--out", type=Path)
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
