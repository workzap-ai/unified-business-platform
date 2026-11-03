"""Draft, critique, revise (spec 8.4.4): a failed check asks for one rewrite; errors never block."""

import asyncio
from types import SimpleNamespace as Ns

from app.modules.pi import critique as c


class Manager:
    def __init__(self, verdict=None, boom=False):
        self.verdict, self.boom = verdict, boom

    async def complete_structured(self, scope, output, **kwargs):
        assert kwargs["purpose"] == "pi_critique" and kwargs["alias"] == "fast"
        if self.boom:
            raise RuntimeError("model down")
        return Ns(value=self.verdict)


def run(manager):
    return asyncio.run(c.critique(manager, None, {"latest_customer_message": "stock"}, "Noted."))


def test_a_failed_check_returns_the_reasons():
    reason = run(Manager(c.Verdict(ok=False, issues=["repeats the person's words"])))
    assert reason == "the quality check failed: repeats the person's words"


def test_a_pass_or_an_error_never_blocks_a_reply():
    assert run(Manager(c.Verdict(ok=True))) is None
    assert run(Manager(c.Verdict(ok=False, issues=[]))) is None
    assert run(Manager(boom=True)) is None


def test_it_is_a_switch_that_is_off_by_default():
    assert not c.switched_on(None) and not c.switched_on({"brain": {}})
    assert c.switched_on({"brain": {"critique": True}})
