"""D6 stage 1: run the real extractor on Development cases, under a hard cost cap.

Owner approval of 2026-10-30 is for STAGE 1 ONLY: Development cases, at most 30 calls and at most
USD 0.50. Stage 2 (Held-out) and stage 3 (conversations) are NOT approved, so this script refuses
any split but `development` and has no flag to open another one.

Safe by default: with no `--execute` it is a DRY RUN. It builds the exact prompts the extractor
would send, prices the worst case, prints the plan and makes NO network call and needs NO key. A
real run needs all of: `--execute`, `OPENAI_API_KEY` in the environment of the shell that runs it
(never an argument, never a file), `--confirm-cap` repeating the plan's numbers, and `--out`, a
new file under `.cache` or the temp directory.

Guards: one process, one call at a time; a call is refused before it is sent when the spend so far
plus its worst case (a conservative input estimate plus the full `max_tokens`) would pass the cap;
the spend is updated from the provider's own `usage` after each call (missing or invalid `usage`
counts as the worst case, and so does any call that failed after it was sent); any HTTP error, a
different model than expected, an answer that is not JSON or the call cap stops the whole run at
once (the stop is a BaseException, so the extractor's own `except Exception` cannot swallow it).
Prices must be finite and at least the verified rates, so a typo cannot make the dollar cap
meaningless. The HTTP client ignores proxy and certificate environment variables and follows no
redirects. Results are written one line per case as they arrive. Nothing here reads `.env`,
imports the app settings or opens a database connection.

Usage (from apps/api):
    python scripts/pi_real_eval.py --in-per-m 0.15 --out-per-m 0.60                 # dry run
    OPENAI_API_KEY=... python scripts/pi_real_eval.py --in-per-m R --out-per-m R \\
        --execute --confirm-cap "<calls> calls USD <cap>" --out .cache/run.jsonl
"""

import argparse
import asyncio
import json
import math
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.modules.pi import problem_extract as pe  # noqa: E402
from app.modules.pi.evalkit import replay, scorers, splits  # noqa: E402
from app.modules.pi.evalkit.report import CASES  # noqa: E402

MAX_CALLS = 30  # stage 1 hard limit (owner approval, 2026-10-30)
MAX_USD = 0.50
ALLOWED_SPLITS = (splits.DEVELOPMENT,)
API_URL = "https://api.openai.com/v1/chat/completions"
EXPECTED_MODEL = "gpt-4o-mini"  # what the registry's "fast" alias maps to; the answer must match
VERIFIED_IN_PER_M = 0.15  # USD per 1M input tokens, from the provider's model page (2026-10-30)
VERIFIED_OUT_PER_M = 0.60  # USD per 1M output tokens: the lowest rates the guard accepts
JSON_SUFFIX = "\nReply with a JSON object."  # the API's JSON mode needs the word JSON in the prompt
INPUT_OVERHEAD_TOKENS = 60  # message framing the provider adds
CHARS_PER_TOKEN_FLOOR = 2.0  # assume one token per 2 characters: far more than English or Urdu need
TIMEOUT_SECONDS = 60.0
REPO_ROOT = Path(__file__).resolve().parents[3]


class Stop(BaseException):
    """Ends the whole run. A BaseException so `extract()`'s `except Exception` cannot swallow it."""


def default_client() -> httpx.AsyncClient:
    """No proxy or certificate environment variables, no redirects: the key goes to one URL."""
    return httpx.AsyncClient(trust_env=False, follow_redirects=False)


def input_tokens_upper(messages: list[Any]) -> int:
    chars = sum(len(m.text()) for m in messages) + len(JSON_SUFFIX)
    return math.ceil(chars / CHARS_PER_TOKEN_FLOOR) + INPUT_OVERHEAD_TOKENS


def worst_case_usd(messages: list[Any], max_tokens: int, in_rate: float, out_rate: float) -> float:
    """The most one call can cost: the input upper bound plus the whole output allowance."""
    return (input_tokens_upper(messages) * in_rate + max_tokens * out_rate) / 1_000_000


class DryManager:
    """Records the exact messages `extract()` builds for a case and returns nothing: no network."""

    def __init__(self) -> None:
        self.sent: list[Any] = []
        self.max_tokens = 1500

    async def complete_structured(self, scope: Any, model: Any, **kwargs: Any) -> Any:
        self.sent = list(kwargs["messages"])
        self.max_tokens = int(kwargs.get("max_tokens") or 1500)
        return SimpleNamespace(value=pe.Extracted(found=[]))


async def dry_price(case: dict[str, Any], in_rate: float, out_rate: float) -> float:
    manager = DryManager()
    await pe.extract(manager, None, replay.context_for(case))
    return worst_case_usd(manager.sent, manager.max_tokens, in_rate, out_rate)


def pick_cases(cases: list[dict[str, Any]], split: str, count: int) -> list[dict[str, Any]]:
    """The first `count` cases of the split, round robin over languages, ids in order: the same
    selection every time."""
    pool = sorted((c for c in cases if splits.split_of(c) == split), key=lambda c: str(c["id"]))
    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in pool:
        by_language[str(case.get("language", "en"))].append(case)
    chosen: list[dict[str, Any]] = []
    queues = [by_language[k] for k in sorted(by_language)]
    while len(chosen) < count and any(queues):
        for queue in queues:
            if queue and len(chosen) < count:
                chosen.append(queue.pop(0))
    return chosen


async def plan(
    cases: list[dict[str, Any]],
    split: str,
    max_calls: int,
    max_usd: float,
    rates: tuple[float, float],
) -> tuple[list[dict[str, Any]], list[float]]:
    """The cases to run and the worst case of each. If the worst case of the whole run passes
    the cap, calls are dropped (never the cap raised) until it fits."""
    chosen = pick_cases(cases, split, max_calls)
    worst = [await dry_price(c, *rates) for c in chosen]
    while chosen and sum(worst) > max_usd:
        chosen.pop()
        worst.pop()
    return chosen, worst


def whole_tokens(value: Any) -> int | None:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


class RealManager:
    """Sends the extractor's request to the provider under the caps. One call at a time."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        key: str,
        max_calls: int,
        max_usd: float,
        rates: tuple[float, float],
    ) -> None:
        self.client = client
        self._key = key
        self.max_calls = max_calls
        self.max_usd = max_usd
        self.rates = rates
        self.calls = 0
        self.spent = 0.0
        self.invalid = 0  # answers that were not usable notes
        self.log: list[dict[str, Any]] = []
        self.raw: list[dict[str, Any]] = []

    def _fail(self, worst: float, why: str) -> Stop:
        self.spent += worst  # a call that failed after it was sent may still have been billed
        return Stop(why)

    async def complete_structured(self, scope: Any, model: Any, **kwargs: Any) -> Any:
        messages = list(kwargs["messages"])
        max_tokens = int(kwargs.get("max_tokens") or 1500)
        worst = worst_case_usd(messages, max_tokens, *self.rates)
        if self.calls >= self.max_calls:
            raise Stop(f"call cap reached ({self.max_calls})")
        if self.spent + worst > self.max_usd:
            raise Stop(f"the next call could pass the cap (spent {self.spent:.5f} + {worst:.5f})")
        body = {
            "model": EXPECTED_MODEL,
            "messages": [
                {
                    "role": m.role,
                    "content": m.text() + (JSON_SUFFIX if m.role == "system" else ""),
                }
                for m in messages
            ],
            "temperature": kwargs.get("temperature", 0.1),
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        self.calls += 1  # counted before the send: a failed call counts too
        try:
            response = await self.client.post(
                API_URL,
                json=body,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as error:
            raise self._fail(worst, f"network error: {type(error).__name__}") from None
        if response.status_code != 200:
            raise self._fail(worst, f"the provider answered HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise self._fail(worst, "the provider's answer was not JSON") from None
        if not isinstance(data, dict):
            raise self._fail(worst, "the provider's answer was not a JSON object")
        served = str(data.get("model", ""))
        if not served.startswith(EXPECTED_MODEL):
            raise self._fail(
                worst, f"a different model answered: {served!r}, expected {EXPECTED_MODEL}"
            )
        raw_usage = data.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        used_in = whole_tokens(usage.get("prompt_tokens"))
        used_out = whole_tokens(usage.get("completion_tokens"))
        if used_in is not None and used_out is not None:
            cost = (used_in * self.rates[0] + used_out * self.rates[1]) / 1_000_000
        else:
            cost = worst  # no usable usage: assume the worst
        self.spent += cost
        self.log.append({"call": self.calls, "usd": round(cost, 6), "model": served})
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = str(message.get("content", "")) if isinstance(message, dict) else ""
        self.raw.append({"content": content})
        try:
            value = pe.Extracted.model_validate(json.loads(content))
        except Exception:  # noqa: BLE001 - unusable output is a finding, counted as no notes
            self.invalid += 1
            value = pe.Extracted(found=[])
        return SimpleNamespace(value=value)


def records_of(ops: list[Any]) -> list[dict[str, Any]]:
    out = []
    for op in ops:
        note = op.note
        if note is not None:
            out.append(
                {
                    "title": note.title,
                    "user_words": list(note.user_words),
                    "summary": note.summary,
                    "money_text": note.money_text,
                }
            )
    return out


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def report(scored: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines = ["# D6 stage 1 (Development, extractor only)", ""]
    for key in ("model", "calls", "spent_usd", "invalid_outputs", "stopped_because"):
        lines.append(f"- {key}: {meta.get(key)}")
    for title, field in (("language", "language"), ("kind", "kind"), ("all", None)):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in scored:
            groups[str(item.get(field, "")) if field else "all"].append(item)
        lines += [
            "",
            f"## by {title}",
            "",
            "| group | n | recall | precision | figures | corrections |",
        ]
        lines.append("|---|---|---|---|---|---|")
        for name in sorted(groups):
            agg = scorers.aggregate(groups[name])
            if not agg["measured"]:
                lines.append(f"| {name} | {agg['cases']} | not yet measured | | | |")
                continue
            lines.append(
                f"| {name} | {agg['cases']} | {pct(agg['recall'])} | {pct(agg['precision'])} | "
                f"{pct(agg['figure_fidelity'])} | {pct(agg['correction_fidelity'])} |"
            )
    return "\n".join(lines)


def start_file(path: str) -> None:
    Path(path).write_text("", encoding="utf-8")


def append_line(path: str, row: str) -> None:
    with open(path, "a", encoding="utf-8") as sink:
        sink.write(row + "\n")


def out_problem(path: str) -> str:
    """Why this output path is refused, or an empty string. It must be a new file under the
    repository's `.cache` folder or the temp directory, so a result is never committed or lost."""
    if not path:
        return "--out is required to execute"
    target = Path(path).resolve()
    roots = [(REPO_ROOT / ".cache").resolve(), Path(tempfile.gettempdir()).resolve()]
    if not any(root == target.parent or root in target.parents for root in roots):
        return "--out must be under .cache or the temp directory"
    if not target.parent.is_dir():
        return "the folder of --out does not exist"
    if target.exists():
        return "--out already exists: it is never overwritten"
    return ""


def number_problem(args: argparse.Namespace) -> str:
    if not 1 <= args.max_calls <= MAX_CALLS:
        return f"--max-calls must be 1 to {MAX_CALLS} (stage 1)"
    if not (math.isfinite(args.max_usd) and 0 < args.max_usd <= MAX_USD):
        return f"--max-usd must be above 0 and at most {MAX_USD} (stage 1)"
    low = (
        not math.isfinite(args.in_per_m)
        or not math.isfinite(args.out_per_m)
        or args.in_per_m < VERIFIED_IN_PER_M
        or args.out_per_m < VERIFIED_OUT_PER_M
    )
    if low:
        return (
            "the token prices must be finite and at least the verified rates "
            f"({VERIFIED_IN_PER_M} in, {VERIFIED_OUT_PER_M} out, USD per 1M tokens)"
        )
    return ""


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="D6 stage 1 real-extractor run (dry run by default)")
    ap.add_argument("--split", choices=list(ALLOWED_SPLITS), default=splits.DEVELOPMENT)
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS)
    ap.add_argument("--max-usd", type=float, default=MAX_USD)
    ap.add_argument("--in-per-m", type=float, required=True, help="USD per 1M input tokens")
    ap.add_argument("--out-per-m", type=float, required=True, help="USD per 1M output tokens")
    ap.add_argument("--execute", action="store_true", help="really call the provider")
    ap.add_argument("--confirm-cap", default="", help='repeat the plan: "<calls> calls USD <cap>"')
    ap.add_argument("--out", default="", help="new JSONL file under .cache or the temp directory")
    return ap


async def run_async(
    args: argparse.Namespace,
    env: Mapping[str, str],
    out: Callable[[str], None],
    client_factory: Callable[[], httpx.AsyncClient],
) -> int:
    if problem := number_problem(args):
        out(f"refused: {problem}")
        return 2
    rates = (args.in_per_m, args.out_per_m)
    cases = replay.load_cases(str(CASES))
    chosen, worst = await plan(cases, args.split, args.max_calls, args.max_usd, rates)
    if not chosen:
        out("refused: not even one call fits under the cap")
        return 2
    languages: dict[str, int] = defaultdict(int)
    for case in chosen:
        languages[str(case.get("language", "en"))] += 1
    out(f"plan: {len(chosen)} calls, split {args.split}, model {EXPECTED_MODEL}")
    out(f"languages: {dict(sorted(languages.items()))}")
    out(f"worst case per call: USD {max(worst):.6f}; worst case for the run: USD {sum(worst):.6f}")
    out(
        f"cap: USD {args.max_usd:.2f} and {args.max_calls} calls; "
        "input estimated at 2 characters per token"
    )
    confirm = f"{len(chosen)} calls USD {args.max_usd:.2f}"
    if not args.execute:
        out(
            "dry run: no network call was made, no key was read. "
            f'To run: --execute --confirm-cap "{confirm}"'
        )
        return 0
    key = env.get("OPENAI_API_KEY", "")
    if not key:
        out("refused: OPENAI_API_KEY is not set in the environment (it is never an argument)")
        return 2
    if args.confirm_cap != confirm:
        out(f'refused: --confirm-cap must be exactly "{confirm}"')
        return 2
    if problem := out_problem(args.out):
        out(f"refused: {problem}")
        return 2
    start_file(args.out)  # exists from the start, then one line per case
    scored: list[dict[str, Any]] = []
    stopped = ""
    async with client_factory() as client:
        manager = RealManager(client, key, len(chosen), args.max_usd, rates)
        try:
            for case in chosen:
                before = len(manager.raw)
                ops = await pe.extract(manager, None, replay.context_for(case))
                records = records_of(ops)
                item = scorers.score_case(case, records) | {
                    "language": case.get("language", "en"),
                    "kind": case.get("kind", "single"),
                }
                scored.append(item)
                append_line(
                    args.out,
                    json.dumps(
                        {"case": case["id"], "raw": manager.raw[before:], "records": records},
                        ensure_ascii=False,
                    ),
                )
                out(
                    f"{case['id']}: found {item['found']}/{item['expected']}  "
                    f"spent {manager.spent:.5f}"
                )
        except Stop as stop:
            stopped = str(stop)
        except Exception as error:  # noqa: BLE001 - whatever happens, the report and file are kept
            stopped = f"unexpected error: {type(error).__name__}"
    meta = {
        "model": EXPECTED_MODEL,
        "calls": manager.calls,
        "spent_usd": round(manager.spent, 6),
        "invalid_outputs": manager.invalid,
        "stopped_because": stopped or "finished the plan",
    }
    out(report(scored, meta))
    return 1 if stopped else 0


def run(
    argv: list[str],
    env: Mapping[str, str] | None = None,
    out: Callable[[str], None] = print,
    client_factory: Callable[[], httpx.AsyncClient] = default_client,
) -> int:
    args = parser().parse_args(argv)
    return asyncio.run(run_async(args, os.environ if env is None else env, out, client_factory))


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
