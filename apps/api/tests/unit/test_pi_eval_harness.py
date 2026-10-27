"""The pi idea evaluation harness: scenario file validity, import without network, call cap."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

API = Path(__file__).resolve().parents[2]
SCRIPT = API / "scripts" / "pi_expert_eval.py"
SCENARIOS = API / "scripts" / "pi_eval_scenarios.json"
PACKS = API / "app" / "modules" / "pi" / "packs" / "industry"
REQUIRED = {
    "id", "industry", "language", "owner_messages", "problem_in_owner_words",
    "noted_problem_titles", "facts_said", "facts_not_said", "expectations",
}  # fmt: skip
EXPECT = {"must_not_assume", "likely_causes", "good_idea_traits", "bad_idea_examples"}
MUST_HAVE = {
    "car_showroom_footfall", "dalal_field_sales_tracking", "kiryana_credit_ledger",
    "restaurant_dinein_drop", "overstock_6_crore", "hospital_opd_wait", "school_fee_recovery",
    "clinic_no_shows", "poultry_mortality", "sugar_mill_cane_delivery",
    "freight_forwarder_delays", "jewellery_making_charges",
}  # fmt: skip


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("pi_expert_eval_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scenarios() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return data


def test_sixty_scenarios_with_unique_ids(scenarios: list[dict[str, Any]]) -> None:
    assert len(scenarios) == 60
    assert len({s["id"] for s in scenarios}) == 60
    assert MUST_HAVE <= {s["id"] for s in scenarios}


def test_industries_exist_and_are_varied(scenarios: list[dict[str, Any]]) -> None:
    keys = {s["industry"] for s in scenarios}
    assert len(keys) >= 45
    assert all((PACKS / f"{k}.json").exists() for k in keys)
    sectors = {
        json.loads((PACKS / f"{k}.json").read_text(encoding="utf-8"))["sector"]["code"]
        for k in keys
    }
    assert len(sectors) >= 8


def test_required_fields(scenarios: list[dict[str, Any]]) -> None:
    for s in scenarios:
        assert REQUIRED <= set(s), s["id"]
        assert s["owner_messages"] and all(isinstance(m, str) and m for m in s["owner_messages"])
        assert s["facts_said"] and s["facts_not_said"], s["id"]
        assert EXPECT <= set(s["expectations"]), s["id"]
        for k in EXPECT:
            assert s["expectations"][k], (s["id"], k)
    langs = {s["language"] for s in scenarios}
    assert {"roman_urdu", "english", "arabic", "urdu_script"} <= langs


def test_showroom_never_names_a_channel(scenarios: list[dict[str, Any]]) -> None:
    showroom = next(s for s in scenarios if s["id"] == "car_showroom_footfall")
    said = " ".join(showroom["owner_messages"]).lower()
    for word in ("video", "page", "ads", "website", "app"):
        assert word not in said.split(), word
    assert {"videos", "page", "ads", "website", "app"} <= set(
        showroom["expectations"]["must_not_assume"]
    )


def test_script_imports_without_network_and_dry_run(scenarios: list[dict[str, Any]]) -> None:
    module = load_module()
    args = module.parse_args(["--generator", "free", "--scenarios", "3", "--dry-run"])
    assert args.max_calls == 150 and args.concurrency == 2
    data = module.build_input(scenarios[0])
    assert data["said"] == scenarios[0]["owner_messages"][-1]
    assert data["industry_key"] == scenarios[0]["industry"]
    assert asyncio.run(module.main_async(args)) == 0


def test_call_budget_cap() -> None:
    module = load_module()
    budget = module.CallBudget(2)
    budget.take()
    budget.take()
    assert budget.left == 0
    with pytest.raises(module.BudgetExceeded):
        budget.take()


def test_metered_manager_counts_retries_against_cap() -> None:
    module = load_module()

    class Usage:
        input_tokens, output_tokens = 10, 5

    class Reply:
        text, provider, model, usage = "x", "p", "m", Usage()

    class Inner:
        calls = 0

        async def complete(self, scope: Any, **kw: Any) -> Any:
            Inner.calls += 1
            if Inner.calls == 1:
                raise RuntimeError("429 rate limit")
            return Reply()

    async def no_sleep(_: float) -> None:
        return None

    async def go(limit: int) -> Any:
        Inner.calls = 0
        manager = module.MeteredManager(Inner(), module.CallBudget(limit), no_sleep)
        metrics = module.Metrics()
        module.CURRENT.set(metrics)
        try:
            return await manager.complete(None, alias="a"), metrics
        except module.BudgetExceeded:
            return None, metrics

    reply, metrics = asyncio.run(go(5))
    assert reply is not None
    rec = metrics.calls[0]
    assert (rec.attempts, rec.rate_limited, rec.input_tokens, rec.output_tokens) == (2, 1, 10, 5)
    reply, _ = asyncio.run(go(1))  # the retry would be a second call: capped
    assert reply is None


def test_expert_missing_is_reported() -> None:
    module = load_module()
    if module.resolve_expert("no_such_function_here") is not None:
        pytest.skip("expert_advisor exists with that function")
    assert module.resolve_expert("no_such_function_here") is None


def test_secrets_are_redacted() -> None:
    module = load_module()
    assert "sk-abcdefghijklmnop" not in module.redact("bad key sk-abcdefghijklmnop here")
