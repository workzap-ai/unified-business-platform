"""A number the owner corrects ("not 10, 100") through the real database, webhook and worker path:
the saved problem shows the new figure, the old one stays in the revision history, and the reply
uses the new figure. Only the model and WhatsApp are scripted. (B7.1 and B7.3 of the plan.)"""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import OPENING, create, problems_of, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import figure_correction as fc
from app.modules.pi.problem_models import PiProblemRevision
from app.modules.pi.problems import ProblemNote, ProblemOp

pytestmark = pytest.mark.integration

FIRST = "We lost about 10 clients last year because reports came late."
FIX = "Sorry, not 10, it was 100 clients."


def first_turn():
    op = create(
        "Clients lost because reports came late",
        FIRST,
        "customers_retention",
        summary="We lost about 10 clients last year because reports came late.",
    )
    return turn(
        reply=f"{OPENING} Noted: clients lost to late reports. Anything else?",
        language="en",
        problem_ops=[op],
    )


def script(monkeypatch, second, rewrite=None):
    """The model: turn one notes the problem; turn two is `second`; a rewrite gets `rewrite`.
    Returns the prompts so a test can read what pi asked."""
    prompts: list[str] = []
    contexts: list[str] = []

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        prompts.append(text)
        if text.startswith("{"):
            contexts.append(text)
            value = first_turn() if len(contexts) == 1 else second(json.loads(text))
        else:
            if len(contexts) == 1:  # a rewrite of turn one
                value = first_turn()
            else:
                value = rewrite if rewrite is not None else second(json.loads(contexts[-1]))
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return prompts


def current_text(problem) -> str:
    """Everything the saved record says now."""
    impact = problem.impact or {}
    parts = [problem.title, problem.summary, impact.get("money_text", ""), *problem.user_words]
    return " ".join(str(p) for p in parts if p)


async def revisions_of(db, problem):
    return list(
        await db.scalars(
            select(PiProblemRevision)
            .where(PiProblemRevision.problem_id == problem.id)
            .order_by(PiProblemRevision.revision)
        )
    )


async def say(pi, text, key):
    await pi.process(text, key)
    await pi.deliver_all()


async def test_a_model_update_that_corrects_the_figure_replaces_the_old_wording(
    api, business_db, monkeypatch
):
    def second(context):
        ref = context["noted_problems"][0]["ref"]
        note = ProblemNote(
            summary="We lost about 100 clients last year because reports came late.",
            user_words=["it was 100 clients"],
        )
        return turn(
            reply="You're right, 100 clients, not 10. When did the late reports start?",
            language="en",
            problem_ops=[ProblemOp(op="update", ref=ref, reason="correction", note=note)],
        )

    script(monkeypatch, second)
    pi = await workspace(api, business_db)
    await say(pi, FIRST, "fc-1a")
    await say(pi, FIX, "fc-1b")
    _, [problem] = await problems_of(business_db, pi)
    text = current_text(problem)
    assert fc.has_figure(text, "100") and not fc.has_figure(text, "10"), text
    assert problem.status == "corrected"
    history = (await revisions_of(business_db, problem))[-1]
    assert history.reason == "correction" and history.by == "person"
    assert any("10 clients" in w for w in history.diff["user_words"][0])  # the old words are kept
    await pi.close()


async def test_a_correction_the_model_does_not_apply_is_applied_by_the_code(
    api, business_db, monkeypatch
):
    script(monkeypatch, lambda c: turn(reply="Noted, thank you. When did it start?", language="en"))
    pi = await workspace(api, business_db)
    await say(pi, FIRST, "fc-2a")
    await say(pi, FIX, "fc-2b")
    _, [problem] = await problems_of(business_db, pi)
    text = current_text(problem)
    assert fc.has_figure(text, "100") and not fc.has_figure(text, "10"), text
    history = (await revisions_of(business_db, problem))[-1]
    assert history.reason == "correction" and history.by == "person"
    assert fc.has_figure(json.dumps(history.diff), "10")  # old figure kept in the history
    await pi.close()


async def test_a_reply_that_keeps_the_old_figure_is_sent_back_and_the_new_one_is_sent(
    api, business_db, monkeypatch
):
    bad = turn(reply="Noted: 10 clients lost to late reports. When did it start?", language="en")
    good = turn(reply="You're right, 100 clients, not 10. When did it start?", language="en")
    prompts = script(monkeypatch, lambda c: bad, rewrite=good)
    pi = await workspace(api, business_db)
    await say(pi, FIRST, "fc-3a")
    await say(pi, FIX, "fc-3b")
    asked = [p for p in prompts if not p.startswith("{")]
    assert asked and "100" in asked[-1] and "corrected" in asked[-1]
    sent = [m.body for m in await pi.outbound() if m.body][-1]
    assert fc.reply_problem(sent, "10", "100") is None, sent
    await pi.close()
