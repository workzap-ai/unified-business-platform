"""Read-only evaluation of pi's idea generators against a scenario file.

Runs `free` (solution_free.free_ideas) or `expert` (app/modules/pi/expert_advisor.py) for each
scenario in pi_eval_scenarios.json and writes JSON and markdown that the `grader` subagent scores
with pi_eval_rubric.md. Nothing is written to any database.

Run from apps/api (keys come from the dashboard key store, read in a read-only session):

  railway run --service pi-worker "<repo>/.venv/Scripts/python.exe" scripts/pi_expert_eval.py \
      --generator free --scenarios 30 --out <dir>/free.json

  --dry-run builds every input and makes no network call (use it first).
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import importlib
import inspect
import json
import random
import re
import socket
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

SCENARIO_FILE = Path(__file__).with_name("pi_eval_scenarios.json")
DEFAULT_MAX_CALLS = 150
CONCURRENCY = 2
RETRY_DELAYS = (5.0, 15.0, 45.0, 90.0)  # seconds; the primary provider is on a free tier
RATE_LIMIT = re.compile(
    r"429|rate.?limit|quota|resource.?exhausted|overloaded|too many requests|try again", re.I
)
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{10,}|Bearer\s+\S+|key=\S+)", re.I)
EXPERT_ENTRY_POINTS = ("advise", "expert_ideas", "expert_advice", "generate", "run", "ideas")


class BudgetExceeded(Exception):  # noqa: N818 - a stop signal, not an error class
    """The hard cap on model calls was reached."""


class CallBudget:
    """A hard cap on model calls (every attempt, including retries, counts)."""

    def __init__(self, limit: int) -> None:
        self.limit = max(0, int(limit))
        self.used = 0

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)

    def take(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceeded(f"max calls reached ({self.limit})")
        self.used += 1


def redact(text: str) -> str:
    return SECRET.sub("[redacted]", text)[:400]


def is_rate_limit(exc: BaseException) -> bool:
    return bool(RATE_LIMIT.search(f"{type(exc).__name__} {exc}"))


@dataclass
class CallRecord:
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    attempts: int = 0
    rate_limited: int = 0
    provider: str = ""
    model: str = ""
    raw_text: str = ""
    error: str = ""


@dataclass
class Metrics:
    calls: list[CallRecord] = field(default_factory=list)


CURRENT: contextvars.ContextVar[Metrics | None] = contextvars.ContextVar(
    "pi_eval_metrics", default=None
)


class MeteredManager:
    """Wraps LLMManager.complete: counts calls against the cap, retries rate limits with backoff,
    and records latency, tokens and the raw text for the scenario being run."""

    def __init__(
        self,
        inner: Any,
        budget: CallBudget,
        sleep: Any = asyncio.sleep,
        delays: tuple[float, ...] = RETRY_DELAYS,
    ) -> None:
        self.inner, self.budget, self.sleep, self.delays = inner, budget, sleep, delays

    async def complete(self, scope: Any, **kwargs: Any) -> Any:
        record = CallRecord()
        metrics = CURRENT.get()
        if metrics is not None:
            metrics.calls.append(record)
        last: BaseException | None = None
        for attempt in range(len(self.delays) + 1):
            self.budget.take()
            record.attempts += 1
            started = time.perf_counter()
            try:
                response = await self.inner.complete(scope, **kwargs)
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                record.latency_s += time.perf_counter() - started
                last = exc
                record.error = redact(f"{type(exc).__name__}: {exc}")
                if is_rate_limit(exc) and attempt < len(self.delays):
                    record.rate_limited += 1
                    await self.sleep(self.delays[attempt] * (0.8 + 0.4 * random.random()))
                    continue
                raise
            record.latency_s += time.perf_counter() - started
            usage = getattr(response, "usage", None)
            record.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            record.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            record.provider = str(getattr(response, "provider", "") or "")
            record.model = str(getattr(response, "model", "") or "")
            record.raw_text = str(getattr(response, "text", "") or "")
            record.error = ""
            return response
        assert last is not None
        raise last


def load_scenarios(path: Path = SCENARIO_FILE) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("the scenario file must hold a list")
    return data


def build_input(scenario: dict[str, Any]) -> dict[str, Any]:
    """The same input the idea generators take in service_conversation.brain_free_ideas."""
    from app.modules.pi import idea_filter, solutions

    key = str(scenario["industry"])
    pack = solutions.load(key) or {}
    messages = [str(m) for m in scenario["owner_messages"]]
    titles = [str(t) for t in scenario.get("noted_problem_titles") or []]
    said = messages[-1]
    idea_ctx = None
    if titles:
        noted = [{"title": t} for t in titles]
        idea_ctx = idea_filter.context_from(
            noted, " ".join([messages[0], said]), [], pack.get("problems") or []
        )
    return {
        "said": said,
        "earlier": messages,
        "industry": pack.get("name") or key.replace("_", " "),
        "industry_key": key,
        "never_say": solutions.never_say([key]),
        "already_said": [],
        "problems": titles,
        "idea_ctx": idea_ctx,
        "language": scenario.get("language", ""),
        "owner_messages": messages,
        "owner_said": messages,
        "subtype": idea_ctx.subtype if idea_ctx else "",
        "country": str(scenario.get("country") or ""),
        "entry_ideas": list(idea_ctx.entry_ideas) if idea_ctx else [],
        "time_limit": 600.0,  # backoff on a free tier must not trip the advisor's own timeout
    }


def resolve_expert(function_name: str | None) -> Any:
    """The expert advisor's entry point, or None when the module is not there yet."""
    try:
        module = importlib.import_module("app.modules.pi.expert_advisor")
    except Exception:  # noqa: BLE001 - the module is being written; report instead of crashing
        return None
    names = (function_name,) if function_name else EXPERT_ENTRY_POINTS
    for name in names:
        fn = getattr(module, str(name), None)
        if callable(fn):
            return fn
    return None


def normalise(result: Any) -> list[str]:
    if result is None:
        return []
    if isinstance(result, str):
        return [result]
    if isinstance(result, dict):
        result = result.get("ideas") or result.get("text") or result
        if isinstance(result, str):
            return [result]
    inner = getattr(result, "ideas", None)
    if inner is not None:
        result = inner
    if isinstance(result, (list, tuple)):
        return [str(x) for x in result]
    return [str(result)]


async def run_generator(
    name: str, manager: Any, scope: Any, alias: str, data: dict[str, Any], expert: Any
) -> tuple[list[str], dict[str, Any]]:
    report: dict[str, Any] = {}
    if name == "free":
        from app.modules.pi import solution_free

        ideas = await solution_free.free_ideas(
            manager,
            scope,
            alias=alias,
            conversation_id=None,
            said=data["said"],
            earlier=data["earlier"],
            industry=data["industry"],
            never_say=data["never_say"],
            already_said=data["already_said"],
            problems=data["problems"],
            idea_ctx=data["idea_ctx"],
            report=report,
        )
        return ideas, report
    offered = {
        **data,
        "manager": manager,
        "scope": scope,
        "alias": alias,
        "conversation_id": None,
        "report": report,
    }
    params = inspect.signature(expert).parameters
    takes_all = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    kwargs = offered if takes_all else {k: v for k, v in offered.items() if k in params}
    result = expert(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    for attr in ("question", "causes", "problem", "judged", "dropped", "drops"):
        if hasattr(result, attr):
            report[attr] = getattr(result, attr)
    return normalise(result), report


async def run_one(
    scenario: dict[str, Any], generator: str, manager: Any, scope: Any, alias: str, expert: Any
) -> dict[str, Any]:
    metrics = Metrics()
    CURRENT.set(metrics)
    started = time.perf_counter()
    out: dict[str, Any] = {
        "id": scenario["id"],
        "industry": scenario["industry"],
        "language": scenario.get("language"),
        "owner_messages": scenario["owner_messages"],
        "problem_in_owner_words": scenario.get("problem_in_owner_words"),
        "facts_said": scenario.get("facts_said"),
        "facts_not_said": scenario.get("facts_not_said"),
        "expectations": scenario.get("expectations"),
        "notes": scenario.get("notes"),
        "generator": generator,
    }
    try:
        ideas, report = await run_generator(
            generator, manager, scope, alias, build_input(scenario), expert
        )
        out.update(ideas=ideas, filter_report=report, status="ok" if ideas else "no_ideas")
    except BudgetExceeded as exc:
        out.update(ideas=[], status="skipped_budget", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        out.update(ideas=[], status="error", error=redact(f"{type(exc).__name__}: {exc}"))
    out["wall_s"] = round(time.perf_counter() - started, 2)
    out["calls"] = [
        {
            "latency_s": round(c.latency_s, 2),
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "attempts": c.attempts,
            "rate_limited": c.rate_limited,
            "provider": c.provider,
            "model": c.model,
            "error": c.error,
        }
        for c in metrics.calls
    ]
    out["raw_model_text"] = [c.raw_text for c in metrics.calls if c.raw_text]
    return out


def summarise(results: list[dict[str, Any]], budget: CallBudget) -> dict[str, Any]:
    calls = [c for r in results for c in r.get("calls", [])]
    lat = sorted(c["latency_s"] for c in calls) or [0.0]
    statuses: dict[str, int] = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    return {
        "scenarios_run": len(results),
        "statuses": statuses,
        "model_calls_used": budget.used,
        "max_calls": budget.limit,
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "latency_median_s": lat[len(lat) // 2],
        "latency_max_s": lat[-1],
        "rate_limit_retries": sum(c["rate_limited"] for c in calls),
    }


def to_markdown(generator: str, summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines = [
        f"# pi idea evaluation: {generator}",
        "",
        "```json",
        json.dumps(summary, indent=1),
        "```",
        "",
    ]
    for r in results:
        lines += [f"## {r['id']} ({r['industry']}, {r.get('language')})", ""]
        lines += [f"Owner: {m}" for m in r["owner_messages"]]
        lines += ["", f"Problem: {r.get('problem_in_owner_words')}", f"Status: {r['status']}"]
        if r.get("error"):
            lines.append(f"Error: {r['error']}")
        exp = r.get("expectations") or {}
        lines += [
            f"Must not assume: {', '.join(exp.get('must_not_assume', []))}",
            f"Not said by the owner: {'; '.join(r.get('facts_not_said') or [])}",
            "",
            "Ideas:",
        ]
        lines += [f"{i}. {idea}" for i, idea in enumerate(r.get("ideas", []), 1)] or ["(none)"]
        calls = r.get("calls", [])
        tok = sum(c["input_tokens"] + c["output_tokens"] for c in calls)
        lines += ["", f"Calls {len(calls)}, tokens {tok}, wall {r['wall_s']}s", ""]
    return "\n".join(lines)


def select(
    scenarios: list[dict[str, Any]], count: int | None, ids: list[str] | None
) -> list[dict[str, Any]]:
    picked = [s for s in scenarios if not ids or s["id"] in ids]
    return picked[:count] if count else picked


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--generator", choices=["free", "expert"], required=True)
    p.add_argument("--file", type=Path, default=SCENARIO_FILE, help="scenario file")
    p.add_argument("--scenarios", type=int, default=None, help="run only the first N scenarios")
    p.add_argument("--ids", default="", help="comma-separated scenario ids")
    p.add_argument(
        "--out", type=Path, default=None, help="results .json path (a .md is written beside it)"
    )
    p.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    p.add_argument("--alias", default="pi_brain", help="model alias (the brain-mode reply alias)")
    p.add_argument("--module-function", default=None, help="entry point in expert_advisor")
    p.add_argument(
        "--provider",
        default="",
        help="put this provider first (e.g. anthropic) so a rate-limited free tier does not decide the run",
    )
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument(
        "--dry-run", action="store_true", help="build inputs only, no database, no model"
    )
    return p.parse_args(argv)


def default_out(generator: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.gettempdir()) / f"pi_eval_{generator}_{stamp}.json"


async def main_async(args: argparse.Namespace) -> int:
    scenarios = select(
        load_scenarios(args.file), args.scenarios, [i for i in args.ids.split(",") if i]
    )
    expert = None
    if args.generator == "expert":
        expert = resolve_expert(args.module_function)
        if expert is None:
            print("expert_advisor not available yet")
            return 2
    budget = CallBudget(args.max_calls)
    if args.dry_run:
        for s in scenarios:
            data = build_input(s)
            print(
                s["id"],
                data["industry_key"],
                "ctx" if data["idea_ctx"] else "no-ctx",
                len(data["never_say"]),
            )
        print(f"dry run ok: {len(scenarios)} scenarios, no model call made")
        return 0

    _orig = socket.getaddrinfo  # the host has no IPv6 route to the database
    socket.getaddrinfo = lambda h, p, family=0, *a, **k: _orig(h, p, socket.AF_INET, *a, **k)
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
    if args.provider:
        settings.primary_llm_provider = args.provider
    if not settings.anthropic_base_url.rstrip("/").endswith("/v1"):
        settings.anthropic_base_url = settings.anthropic_base_url.rstrip("/") + "/v1"

    sem = asyncio.Semaphore(max(1, args.concurrency))
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=120) as http:
        manager = MeteredManager(LLMManager(settings, http), budget)

        async def guarded(s: dict[str, Any]) -> dict[str, Any]:
            async with sem:
                if budget.left <= 0:
                    return {
                        "id": s["id"],
                        "industry": s["industry"],
                        "generator": args.generator,
                        "owner_messages": s["owner_messages"],
                        "ideas": [],
                        "status": "skipped_budget",
                        "wall_s": 0.0,
                        "calls": [],
                        "raw_model_text": [],
                    }
                res = await run_one(s, args.generator, manager, None, args.alias, expert)
                print(
                    f"{res['id']}: {res['status']} {len(res['ideas'])} ideas {res['wall_s']}s",
                    flush=True,
                )
                return res

        results = list(await asyncio.gather(*(guarded(s) for s in scenarios)))
    summary = summarise(results, budget)
    out = args.out or default_out(args.generator)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generator": args.generator,
        "alias": args.alias,
        "summary": summary,
        "results": results,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".md").write_text(
        to_markdown(args.generator, summary, results), encoding="utf-8"
    )
    print(json.dumps(summary))
    print(f"written {out} and {out.with_suffix('.md')}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async(parse_args())))


if __name__ == "__main__":
    main()
