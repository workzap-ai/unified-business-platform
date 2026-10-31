"""RMEM05: the customer export carries the same PS-8 bundle pi answers "what do you keep?" from."""

import pytest
from test_pi_brain_problems import adaptive, create, problems_of, say, workspace
from test_pi_service_conversations import turn

pytestmark = pytest.mark.integration


def noting(context, n):
    if "Best-sellers" in context["latest_customer_message"]:
        return turn(
            reply="Hi, I'm pi, an AI from Workzap. Noted. Anything else getting in the way?",
            language="en",
            problem_ops=[create("Best-sellers run out", "Best-sellers run out.")],
        )
    return turn(reply="Noted. Anything else getting in the way?", language="en")


async def test_the_export_includes_the_bundle_and_the_chat_lists_the_same_problem(
    api, business_db, monkeypatch
):
    adaptive(monkeypatch, noting)
    pi = await workspace(api, business_db)
    await say(pi, "Best-sellers run out", "ex-1")
    conversation, rows = await problems_of(business_db, pi)
    assert len(rows) == 1

    exported = await api.get(f"/api/v1/pi/customers/{conversation.customer_id}/export")
    assert exported.status_code == 200, exported.text
    bundle = exported.json()["pi_memory"]
    assert [p["title"] for p in bundle["problems"]] == ["Best-sellers run out"]
    assert {"profile", "constraints", "decisions", "solutions"} <= set(bundle)

    await say(pi, "what do you remember about me?", "ex-2")
    answer = (await pi.reply_to("ex-2")).body
    assert "Best-sellers run out" in answer and "delete" in answer
    await pi.close()
