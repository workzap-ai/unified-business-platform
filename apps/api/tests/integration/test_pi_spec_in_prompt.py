"""In brain mode the model is given the specification's own words, for the moment (Appendix A)."""

import json

import pytest
from test_pi_brain_problems import adaptive, say, workspace
from test_pi_service_conversations import turn

pytestmark = pytest.mark.integration


def asks(context, n):
    return turn(reply="Noted. Which items run out first?", language="en")


async def test_the_brain_prompt_carries_the_spec_and_the_emergency_numbers(
    api, business_db, monkeypatch
):
    prompts = adaptive(monkeypatch, asks)
    pi = await workspace(api, business_db)
    await say(pi, "stock runs out in two shops", "sp-1")
    contexts = [json.loads(p) for p in prompts if p.startswith("{")]
    first = contexts[0]
    guide = first["spec_guidance"]
    assert "pi-brain specification" in guide
    for rule in ("R-DISC-01", "R-SELL-01", "R-PAY-01", "R-VOICE-01"):
        assert rule in guide
    assert "3.3 The listening loop" in guide  # the stage guidance for listening
    assert "G1" in guide  # a worked example close to the situation
    assert "Pakistan" in str(first["emergency_numbers"]) or isinstance(
        first["emergency_numbers"], dict
    )
    await pi.close()
