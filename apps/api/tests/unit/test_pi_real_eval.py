"""D6 stage 1 runner: dry by default, Development only, 30 calls and USD 0.50 at most, the key never
leaves the environment, and every stop (cap, model, HTTP error, bad answer) ends the run with the
results so far on disk. No test touches the network: the provider is a mock transport."""

import asyncio
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.modules.pi.evalkit import splits
from app.modules.pi.evalkit.report import CASES

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pi_real_eval.py"
spec = importlib.util.spec_from_file_location("pi_real_eval", SCRIPT)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def tmp_path():
    """The platform temp directory directly (pytest's own base directory is not writable here)."""
    with tempfile.TemporaryDirectory() as folder:
        yield Path(folder)


KEY = "sk-test-SECRET123"
RATES = ["--in-per-m", "0.15", "--out-per-m", "0.60"]
OK = {
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [{"message": {"content": json.dumps({"found": []})}}],
    "usage": {"prompt_tokens": 1400, "completion_tokens": 50},
}


def answer(body=None, status=200):
    return lambda request: httpx.Response(status, json=body if body is not None else OK)


def go(argv, env=None, handler=None):
    lines: list[str] = []
    seen: list[httpx.Request] = []
    reply = handler or answer()

    def factory():
        def record(request):
            seen.append(request)
            return reply(request)

        return httpx.AsyncClient(transport=httpx.MockTransport(record))

    code = mod.run(argv, env if env is not None else {}, lines.append, factory)
    return code, "\n".join(lines), seen


def confirm(text: str) -> str:
    line = next(ln for ln in text.splitlines() if ln.startswith("dry run"))
    return line.split('--confirm-cap "')[1].rstrip('"')


def execute(tmp_path, handler, calls="3", env=None):
    _, dry, _ = go([*RATES, "--max-calls", calls])
    out = tmp_path / "run.jsonl"
    argv = [*RATES, "--max-calls", calls, "--execute", "--confirm-cap", confirm(dry)]
    code, text, seen = go([*argv, "--out", str(out)], env or {"OPENAI_API_KEY": KEY}, handler)
    return code, text, seen, out


def spent(text: str) -> float:
    return float(text.split("spent_usd: ")[1].split()[0])


def test_the_default_is_a_dry_run_with_no_call_and_no_key() -> None:
    code, text, seen = go(RATES)
    assert code == 0 and seen == []
    assert "dry run: no network call was made" in text and "plan: 30 calls" in text


def test_only_the_development_split_can_be_chosen() -> None:
    for split in ("held_out", "regression"):
        with pytest.raises(SystemExit):
            go(["--split", split, *RATES])
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    chosen, _ = asyncio.run(mod.plan(cases, "development", 30, 0.5, (0.15, 0.6)))
    assert chosen and all(splits.split_of(c) == splits.DEVELOPMENT for c in chosen)


@pytest.mark.parametrize(
    "extra",
    [
        ["--max-calls", "31"],
        ["--max-calls", "0"],
        ["--max-usd", "0.51"],
        ["--max-usd", "0"],
        ["--max-usd", "nan"],
        ["--max-usd", "inf"],
    ],
)
def test_the_stage_one_limits_cannot_be_raised(extra) -> None:
    code, text, seen = go([*RATES, *extra])
    assert code == 2 and "refused" in text and seen == []


def test_the_token_prices_are_required() -> None:
    with pytest.raises(SystemExit):
        go([])


@pytest.mark.parametrize(
    ("price_in", "price_out"),
    [
        ("0", "0.6"),
        ("nan", "0.6"),
        ("0.15", "nan"),
        ("inf", "0.6"),
        ("0.10", "0.6"),
        ("0.15", "0.3"),
    ],
)
def test_a_price_not_finite_or_below_the_verified_rate_is_refused(price_in, price_out) -> None:
    code, text, seen = go(["--in-per-m", price_in, "--out-per-m", price_out])
    assert code == 2 and "verified rates" in text and seen == []


def test_a_real_run_needs_the_key_the_confirmation_and_an_output_file(tmp_path) -> None:
    _, dry, _ = go([*RATES, "--max-calls", "3"])
    exact = confirm(dry)
    base = [*RATES, "--max-calls", "3", "--execute"]
    out = str(tmp_path / "run.jsonl")
    code, text, seen = go([*base, "--confirm-cap", exact, "--out", out])
    assert code == 2 and "OPENAI_API_KEY" in text and seen == []
    env = {"OPENAI_API_KEY": KEY}
    code, text, seen = go([*base, "--confirm-cap", "yes", "--out", out], env)
    assert code == 2 and "--confirm-cap" in text and seen == []
    code, text, seen = go([*base, "--confirm-cap", exact], env)
    assert code == 2 and "--out is required" in text and seen == []


def test_the_output_path_is_checked_before_any_call(tmp_path) -> None:
    _, dry, _ = go([*RATES, "--max-calls", "3"])
    base = [*RATES, "--max-calls", "3", "--execute", "--confirm-cap", confirm(dry), "--out"]
    env = {"OPENAI_API_KEY": KEY}
    elsewhere = SCRIPT.parent / "must_not_exist.jsonl"
    code, text, seen = go([*base, str(elsewhere)], env)
    assert code == 2 and "under .cache or the temp directory" in text and seen == []
    assert not elsewhere.exists()
    code, text, seen = go([*base, str(tmp_path / "missing" / "run.jsonl")], env)
    assert code == 2 and "does not exist" in text and seen == []
    old = tmp_path / "old.jsonl"
    old.write_text("keep me", encoding="utf-8")
    code, text, seen = go([*base, str(old)], env)
    assert code == 2 and "never overwritten" in text and seen == []
    assert old.read_text(encoding="utf-8") == "keep me"


def test_a_run_stays_inside_the_call_cap_and_never_leaks_the_key(tmp_path) -> None:
    code, text, seen, out = execute(tmp_path, answer())
    assert code == 0 and len(seen) == 3
    written = out.read_text(encoding="utf-8")
    assert len(written.splitlines()) == 3 and KEY not in text and KEY not in written
    body = json.loads(seen[0].content)
    assert body["model"] == "gpt-4o-mini" and body["max_tokens"] == 1500
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.1
    system = next(m for m in body["messages"] if m["role"] == "system")
    assert system["content"].endswith("Reply with a JSON object.")
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert str(seen[0].url) == mod.API_URL


def test_calls_are_dropped_not_the_cap_raised_when_the_worst_case_does_not_fit() -> None:
    code, text, _ = go([*RATES, "--max-usd", "0.004"])
    line = next(ln for ln in text.splitlines() if ln.startswith("worst case"))
    total = float(line.split("run: USD ")[1])
    count = int(text.split("plan: ")[1].split(" calls")[0])
    assert code == 0 and 1 <= count < 30 and total <= 0.004
    code, text, seen = go([*RATES, "--max-usd", "0.0004"])
    assert code == 2 and "not even one call fits" in text and seen == []


def test_the_spend_guard_stops_the_run_before_the_cap_is_passed(tmp_path) -> None:
    huge = {**OK, "usage": {"prompt_tokens": 1400, "completion_tokens": 900_000}}  # USD 0.54
    code, text, seen, _ = execute(tmp_path, answer(huge))
    assert code == 1 and len(seen) == 1 and "could pass the cap" in text


@pytest.mark.parametrize(
    "usage",
    [{}, {"prompt_tokens": "x", "completion_tokens": None}, "not a dict", {"prompt_tokens": 5}],
)
def test_a_call_without_usable_usage_counts_as_the_worst_case(tmp_path, usage) -> None:
    code, text, seen, _ = execute(tmp_path, answer({**OK, "usage": usage}))
    assert code == 0 and len(seen) == 3 and spent(text) > 0.003


def test_a_negative_usage_cannot_lower_the_spend(tmp_path) -> None:
    negative = {**OK, "usage": {"prompt_tokens": -9_000_000, "completion_tokens": -5}}
    code, text, _, _ = execute(tmp_path, answer(negative))
    assert code == 0 and spent(text) >= 0


def test_a_different_model_answering_stops_the_run(tmp_path) -> None:
    code, text, seen, _ = execute(tmp_path, answer({**OK, "model": "gpt-5.4-mini"}))
    assert code == 1 and len(seen) == 1 and "different model" in text and spent(text) > 0.001


@pytest.mark.parametrize("status", [401, 429, 500])
def test_any_http_error_stops_at_once_and_is_charged_the_worst_case(tmp_path, status) -> None:
    code, text, seen, out = execute(tmp_path, answer({"error": "x"}, status))
    assert code == 1 and len(seen) == 1 and f"HTTP {status}" in text
    assert spent(text) > 0.001 and out.exists() and KEY not in text


def test_a_network_error_stops_the_run(tmp_path) -> None:
    def boom(request):
        raise httpx.ConnectError("no route")

    code, text, seen, out = execute(tmp_path, boom)
    assert code == 1 and "network error: ConnectError" in text and out.exists()
    assert KEY not in text


@pytest.mark.parametrize(
    ("handler", "words"),
    [
        (lambda r: httpx.Response(200, text="not json"), "not JSON"),
        (lambda r: httpx.Response(200, json=[1, 2]), "not a JSON object"),
    ],
)
def test_a_malformed_answer_ends_the_run_and_the_report_and_file_are_kept(
    tmp_path, handler, words
) -> None:
    code, text, seen, out = execute(tmp_path, handler)
    assert code == 1 and len(seen) == 1 and words in text and "stopped_because" in text
    assert out.exists() and spent(text) > 0.001 and KEY not in text


def test_invalid_model_output_counts_as_a_call_and_is_counted_in_the_report(tmp_path) -> None:
    bad = {**OK, "choices": [{"message": {"content": "not json"}}]}
    code, text, seen, _ = execute(tmp_path, answer(bad))
    assert code == 0 and len(seen) == 3 and "invalid_outputs: 3" in text


def test_results_are_written_as_each_case_arrives(tmp_path) -> None:
    calls = []

    def first_ok_then_error(request):
        calls.append(1)
        return httpx.Response(200 if len(calls) == 1 else 500, json=OK)

    code, text, seen, out = execute(tmp_path, first_ok_then_error)
    assert code == 1 and len(seen) == 2
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1


def test_an_unexpected_error_still_keeps_the_report_and_the_file(tmp_path, monkeypatch) -> None:
    def broken(case, records):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod.scorers, "score_case", broken)
    code, text, seen, out = execute(tmp_path, answer())
    assert code == 1 and "unexpected error: RuntimeError" in text and out.exists()


def test_the_call_cap_stops_a_manager_asked_for_one_call_too_many() -> None:
    message = SimpleNamespace(role="user", text=lambda: "x")

    async def two_calls():
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer())) as client:
            manager = mod.RealManager(client, KEY, 1, 0.5, (0.15, 0.6))
            await manager.complete_structured(None, None, messages=[message], max_tokens=10)
            await manager.complete_structured(None, None, messages=[message], max_tokens=10)

    with pytest.raises(mod.Stop, match="call cap"):
        asyncio.run(two_calls())


def test_a_stop_cannot_be_swallowed_by_the_extractor() -> None:
    assert issubclass(mod.Stop, BaseException)
    assert not issubclass(mod.Stop, Exception)


def test_the_http_client_ignores_proxy_variables_and_follows_no_redirects() -> None:
    client = mod.default_client()
    try:
        assert client.trust_env is False
        assert client.follow_redirects is False
    finally:
        asyncio.run(client.aclose())


def test_the_selection_is_the_same_every_time_and_mixes_languages() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    one = [c["id"] for c in mod.pick_cases(cases, "development", 12)]
    assert one == [c["id"] for c in mod.pick_cases(cases, "development", 12)]
    assert len({c["language"] for c in mod.pick_cases(cases, "development", 12)}) >= 2


def test_the_script_reads_no_settings_file_and_opens_no_database_connection() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("get_settings", "load_dotenv", "env_file", "DATABASE_URL", "create_engine"):
        assert forbidden not in source
    probe = (
        "import importlib.util, sys; "
        f"s = importlib.util.spec_from_file_location('r', r'{SCRIPT}'); "
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "print('app.core.config' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=str(SCRIPT.parents[1])
    )
    assert result.stdout.strip().endswith("False"), result.stderr[-300:]
