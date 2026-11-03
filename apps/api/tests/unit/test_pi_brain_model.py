from types import SimpleNamespace

from app.ai.registry import ModelRegistry
from app.modules.pi.service_conversation import reply_alias


def _policy(rules: dict, ai: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(response_rules=rules, ai_config=ai or {"reply_alias": "balanced"})


def test_brain_mode_uses_the_pi_brain_model() -> None:
    assert reply_alias(_policy({"pi_mode": "brain"})) == "pi_brain"


def test_other_workspaces_and_explicit_choices_are_unchanged() -> None:
    assert reply_alias(_policy({})) == "balanced"
    assert reply_alias(_policy({"pi_mode": "brain"}, {"reply_alias": "reasoning"})) == "reasoning"


def test_pi_brain_resolves_and_can_be_pinned() -> None:
    assert ModelRegistry({}, use_defaults=True).resolve("openai", "pi_brain") == "gpt-5.4-mini"
    pinned = ModelRegistry({"openai": {"pi_brain": "gpt-5.4"}}, use_defaults=True)
    assert pinned.resolve("openai", "pi_brain") == "gpt-5.4"
