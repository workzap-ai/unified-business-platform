"""A draft that fails validation is never answered with a statement alone: the owner gets the
acknowledgement and the next question (owner rule: no dead-end replies). Real database and webhook
flow; the AI and WhatsApp are mocked."""

import pytest
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.modules.pi import runtime
from app.modules.pi.guard import ReplyRejected

pytestmark = pytest.mark.integration

HELLO = "Hi, I'm pi, an AI from Workzap."
ACK = "Thanks, I've got that."


def script(context, n):
    said = context["latest_customer_message"]
    if "Best-sellers" in said:
        return turn(
            reply=f"{HELLO} That sounds costly. Which shop feels it most?",
            language="en",
            problem_ops=[
                create("Best-sellers run out", "Best-sellers run out.", "stock_inventory")
            ],
        )
    return turn(reply="Okay. What else gets in the way?", language="en")


def last_reply(pi):
    return next(m["text"]["body"] for m in reversed(pi.sent) if "text" in m)


async def test_a_rejected_draft_is_acknowledged_and_the_next_question_follows(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, script)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out", "de-1")
    first = last_reply(pi)
    assert first.endswith("?")
    real = runtime.validate_service_reply

    def reject_the_second_draft(reply, *args, **kwargs):
        if "What else" in reply:  # the model's draft for the next message
            raise ReplyRejected("SERVICE_PRICE_BLOCKED")
        return real(reply, *args, **kwargs)

    monkeypatch.setattr(runtime, "validate_service_reply", reject_the_second_draft)
    await say(pi, "the cashiers are late too", "de-2")
    reply = last_reply(pi)
    assert reply.startswith(ACK), reply
    assert (
        "What else" not in reply
    )  # the rejected draft is not sent  # the rejected draft is not sent
    assert reply.count("?") == 1 and reply.rstrip().endswith("?"), reply
    await pi.close()
