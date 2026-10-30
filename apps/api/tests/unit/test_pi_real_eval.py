"""D6 stage 1 runner: dry by default, Development only, 30 calls and USD 0.50 at most, the key never
leaves the environment, and every stop (cap, model, HTTP error) ends the run. No test touches the
network: the provider is a mock transport."""

import importlib.util
import json
import tempfile
from pathlib import Path

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


def test_the_default_is_a_dry_run_with_no_call_and_no_key() -> None:
    code, text, seen = go(RATES)
    assert code == 0 and seen == []
    assert "dry run: no network call was made" in text and "plan: 30 calls" in text


def test_only_the_development_split_can_be_chosen() -> None:
    for split in ("held_out", "regression"):
        with pytest.raises(SystemExit):
            go(["--split", split, *RATES])
    chosen = mod.pick_cases(json.loads(CASES.read_text(encoding="utf-8")), "development", 30)
    assert chosen and all(splits.split_of(c) == splits.DEVELOPMENT for c in chosen)


@pytest.mark.parametrize(
    "extra",
    [["--max-calls", "31"], ["--max-calls", "0"], ["--max-usd", "0.51"], ["--max-usd", "0"]],
)
def test_the_stage_one_limits_cannot_be_raised(extra) -> None:
    code, text, seen = go([*RATES, *extra])
    assert code == 2 and "refused" in text and seen == []


def test_the_token_prices_are_required() -> None:
    with pytest.raises(SystemExit):
        go([])
    code, text, _ = go(["--in-per-m", "0", "--out-per-m", "0.6"])
    assert code == 2 and "positive" in text


def test_a_real_run_needs_the_key_the_confirmation_and_an_output_file(tmp_path) -> None:
    _, dry, _ = go([*RATES, "--max-calls", "3"])
    exact = confirm(dry)
    out = str(tmp_path / "run.jsonl")
    code, text, seen = go(
        [*RATES, "--max-calls", "3", "--execute", "--confirm-cap", exact, "--out", out]
    )
    assert code == 2 and "OPENAI_API_KEY" in text and seen == []
    env = {"OPENAI_API_KEY": KEY}
    code, text, seen = go(
        [*RATES, "--max-calls", "3", "--execute", "--confirm-cap", "yes", "--out", out], env
    )
    assert code == 2 and "--confirm-cap" in text and seen == []
    code, text, seen = go([*RATES, "--max-calls", "3", "--execute", "--confirm-cap", exact], env)
    assert code == 2 and "--out" in text and seen == []


def test_a_run_stays_inside_the_call_cap_and_never_leaks_the_key(tmp_path) -> None:
    _, dry, _ = go([*RATES, "--max-calls", "3"])
    out = tmp_path / "run.jsonl"
    argv = [
        *RATES,
        "--max-calls",
        "3",
        "--execute",
        "--confirm-cap",
        confirm(dry),
        "--out",
        str(out),
    ]
    code, text, seen = go(argv, {"OPENAI_API_KEY": KEY})
    assert code == 0 and len(seen) == 3
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3
    assert KEY not in text and KEY not in out.read_text(encoding="utf-8")
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


def execute(tmp_path, handler, calls="3"):
    _, dry, _ = go([*RATES, "--max-calls", calls])
    out = str(tmp_path / "run.jsonl")
    argv = [*RATES, "--max-calls", calls, "--execute", "--confirm-cap", confirm(dry), "--out", out]
    return go(argv, {"OPENAI_API_KEY": KEY}, handler)


def test_the_spend_guard_stops_the_run_before_the_cap_is_passed(tmp_path) -> None:
    huge = {
        **OK,
        "usage": {"prompt_tokens": 1400, "completion_tokens": 900_000},
    }  # USD 0.54: above the cap
    code, text, seen = execute(tmp_path, answer(huge))
    assert code == 1 and len(seen) == 1 and "could pass the cap" in text


def test_a_call_without_usage_counts_as_the_worst_case(tmp_path) -> None:
    code, text, seen = execute(tmp_path, answer({**OK, "usage": {}}))
    assert code == 0 and len(seen) == 3
    assert float(text.split("spent_usd: ")[1].split()[0]) > 0.001


def test_a_different_model_answering_stops_the_run(tmp_path) -> None:
    code, text, seen = execute(tmp_path, answer({**OK, "model": "gpt-5.4-mini"}))
    assert code == 1 and len(seen) == 1 and "different model" in text


@pytest.mark.parametrize("status", [401, 429, 500])
def test_any_http_error_stops_at_once(tmp_path, status) -> None:
    code, text, seen = execute(tmp_path, answer({"error": "x"}, status))
    assert code == 1 and len(seen) == 1 and f"HTTP {status}" in text


def test_invalid_model_output_counts_as_a_call_with_no_notes(tmp_path) -> None:
    bad = {**OK, "choices": [{"message": {"content": "not json"}}]}
    code, text, seen = execute(tmp_path, answer(bad))
    assert code == 0 and len(seen) == 3


def test_a_stop_cannot_be_swallowed_by_the_extractor() -> None:
    assert issubclass(mod.Stop, BaseException) and not issubclass(mod.Stop, Exception)


def test_the_selection_is_the_same_every_time_and_mixes_languages() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    one = [c["id"] for c in mod.pick_cases(cases, "development", 12)]
    assert one == [c["id"] for c in mod.pick_cases(cases, "development", 12)]
    languages = {c["language"] for c in mod.pick_cases(cases, "development", 12)}
    assert len(languages) >= 2


def test_the_script_reads_no_settings_file_and_no_database() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("get_settings", "load_dotenv", "env_file", "DATABASE_URL", "sqlalchemy"):
        assert forbidden not in source
