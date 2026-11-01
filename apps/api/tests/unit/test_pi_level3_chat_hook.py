"""Level 3 chat approval hook: the gate turns a confirmed approval into a fixed reply, and does
nothing at all when the hook set no confirmation (flag off, no shown scope, not an explicit yes)."""

import asyncio
from types import SimpleNamespace

from app.modules.pi import execution_hooks as hooks
from app.modules.pi import service_conversation as sc


def _ctx(**extra):
    base = {
        "pi_mode": "brain",
        "latest_customer_message": "haan, ye kar do",
        "reply_language": "en",
        "history": [{"role": "ai", "text": "hello"}],
        "flow": {"state": "S1_LISTENING"},
    }
    base.update(extra)
    return base


def test_gate_replies_with_the_confirmation_when_the_hook_set_one():
    line = "Thank you. That exact scope is approved."
    turn = sc._brain_gate(_ctx(l3_confirmation=line), "haan, ye kar do")
    assert turn is not None and line in turn.reply
    assert turn._decision.why == "L3-APPROVAL"


def test_gate_does_not_fire_without_a_confirmation():
    turn = sc._brain_gate(_ctx(), "haan, ye kar do")
    assert turn is None or turn._decision.why != "L3-APPROVAL"


def test_gate_ignores_the_confirmation_for_an_earlier_message_of_a_burst():
    turn = sc._brain_gate(_ctx(l3_confirmation="x"), "haan", earlier_message=True)
    assert turn is None or turn._decision.why != "L3-APPROVAL"


def test_hook_is_inert_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(hooks, "get_settings", lambda: SimpleNamespace(app_env="test"))
    conv = SimpleNamespace(customer_id="c1")
    out = asyncio.run(
        hooks.owner_reply(None, None, conv, {"pi_mode": "brain"}, "yes please do it", "Ali")
    )
    assert out is None
