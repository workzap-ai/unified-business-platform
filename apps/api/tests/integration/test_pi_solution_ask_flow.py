"""Free ideas on request and "how exactly?" in a real chat (Addendum 2, Parts 1.4, 1.6, 1.9).
The model is mocked; the webhook, the worker, the gates and the database are real."""

import json

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_service_conversations import turn
from test_pi_solution_learning import an_industry

from app.modules.customers.models import Customer
from app.modules.pi import solution_ask, solution_context, solution_ideas, solutions
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def the_offer_is_open(monkeypatch):
    """These journeys start at the offer. Since Book 5 Part 14 pi offers only through can_offer
    (R1 to R3 or B1 to B7), which the unit tests cover; here the gate is held open so the chat
    reaches the offer and the tests can exercise what follows it."""
    from app.modules.pi import box

    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: True)
    monkeypatch.setattr(box, "can_offer", lambda facts: (True, "R2", "held open for this journey"))


OPENING = "Hi, I'm pi, an AI from Workzap."


async def solution_chat(api, db, monkeypatch, make):
    """A chat whose workspace has solution mode on and whose first message noted a problem."""
    prompts = adaptive(monkeypatch, make)
    pi = await workspace(api, db)
    pi.prompts = prompts
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"solution_mode": True, "learning_frozen": False}}},
    )
    assert response.status_code == 200, response.text
    industry, problem = an_industry()
    await solution_ideas.ensure_arms(db, pi.scope(), industry)
    await say(pi, "my shop loses sales when stock runs out", "ask-1")
    conversation = await pi.conversation()
    customer = await db.get(Customer, conversation.customer_id)
    customer.industry_primary = industry
    await db.flush()
    return pi, conversation, industry, problem


def replies(db_rows):
    return [m.body for m in db_rows if m.direction == "outbound"]


async def reply_after(pi, db, text, key):
    """What pi sent in answer to this message (the test clock stands still, so by id)."""
    before = set(await db.scalars(select(PiMessage.id)))
    await say(pi, text, key)
    fresh = [
        m
        for m in await db.scalars(select(PiMessage))
        if m.id not in before and m.direction == "outbound"
    ]
    return [m.body for m in fresh]


def scripted(industry, problem):
    def make(context, n):
        if n == 1:
            return turn(
                reply=f"{OPENING} Thanks. I've noted it: {problem['words'][:40]}.",
                language="en",
                problem_ops=[
                    create(
                        " ".join(problem["words"].split()[:8]),
                        problem["words"],
                        category=problem["category"],
                        subtype=problem["subtype"],
                        confidence=0.9,
                    )
                ],
            )
        if "solution_ideas" in context:
            ideas = context["solution_ideas"]
            says = (context.get("solution_build") or {}).get("says", "")
            return turn(
                reply="Sure.\n"
                + "\n".join(f"• {i}" for i in ideas)
                + f"\nWorkzap would set it up: {says}",
                language="en",
            )
        if "solution_howto" in context:
            return turn(
                reply="That's in the solution document: " + context["solution_howto"]["covers"],
                language="en",
            )
        return turn(reply="Noted. Anything else getting in the way?", language="en")

    return make


async def test_a_push_for_a_fix_gets_two_ideas_then_the_applications_offer(
    api, business_db, monkeypatch
):
    industry, problem = an_industry()
    pi, conversation, industry, problem = await solution_chat(
        api, business_db, monkeypatch, scripted(industry, problem)
    )
    bodies = await reply_after(pi, business_db, "Can you tell me the solution", "ask-2")
    assert len(bodies) == 1, bodies
    [body] = bodies
    await business_db.refresh(conversation)
    bullets = [line for line in body.splitlines() if line.startswith(("First,", "Second,", "•"))]
    assert 1 <= len(bullets) <= 2  # R-VAL-01
    assert body.rstrip().endswith(solution_ask.offer_line("en"))
    assert conversation.flow_state == "S5_READINESS"
    assert conversation.service_brief["ideas_given"] == len(bullets)
    assert conversation.service_brief["offer_asked"] is True
    assert conversation.service_brief["builds_said"]
    await pi.close()


async def test_how_exactly_gets_what_the_document_covers_and_the_offer_and_no_idea(
    api, business_db, monkeypatch
):
    industry, problem = an_industry()
    pi, conversation, industry, problem = await solution_chat(
        api, business_db, monkeypatch, scripted(industry, problem)
    )
    [body] = await reply_after(pi, business_db, "how exactly would that work?", "ask-2")
    await business_db.refresh(conversation)
    assert "solution document" in body
    assert body.rstrip().endswith(solution_ask.offer_line("en"))
    assert not [line for line in body.splitlines() if line.startswith("•")]
    assert conversation.service_brief.get("howto_asked") == 1
    assert conversation.service_brief.get("ideas_given", 0) == 0
    assert conversation.flow_state == "S5_READINESS"
    await reply_after(pi, business_db, "ok, let me think about it", "ask-3")
    sent = json.loads([p for p in pi.prompts if p.startswith("{")][-1])
    # the free-rider counters are for the dashboard: the model never sees them
    assert not {"free_rider", "howto_asked", "declines"} & set(sent["brief"])
    await pi.close()


async def test_a_push_for_a_fix_without_solution_mode_gets_the_no_idea_line_and_one_question(
    api, business_db, monkeypatch
):
    industry, problem = an_industry()
    adaptive(monkeypatch, scripted(industry, problem))
    pi = await workspace(api, business_db)
    await say(pi, "my shop loses sales when stock runs out", "ask-1")
    body = " ".join(await reply_after(pi, business_db, "Aap jaldi solution do na mujhe", "ask-2"))
    # spec v1.6 19.7: a summary is never the reply to a push for a fix, and 19.6: never a dead end.
    # The honest no-idea line with its one question, last, is the reply; no offer, no summary.
    from app.modules.pi.service_conversation import NO_IDEA_LINES

    assert NO_IDEA_LINES["roman_ur"] in body
    assert body.rstrip().endswith("?") and body.count("?") == 1
    assert solution_ask.offer_line("en") not in body
    await pi.close()


async def test_the_giving_gate_opens_for_a_request_while_listening_only(
    api, business_db, monkeypatch
):
    industry, problem = an_industry()
    pi, conversation, industry, problem = await solution_chat(
        api, business_db, monkeypatch, scripted(industry, problem)
    )
    noted = [{"title": problem["words"], "group": problem["category"]}]
    scope = pi.scope()
    conversation.flow_state = "S1_LISTENING"
    conversation.service_brief = {}
    quiet = await solution_context.build(
        business_db, scope, conversation, "stock runs out", noted, {}
    )
    assert "solution_ideas" not in quiet
    used: dict = {}
    asked = await solution_context.build(
        business_db, scope, conversation, "Can you tell me the solution", noted, used
    )
    assert asked["solution_asked"] and 1 <= len(asked["solution_ideas"]) <= 2
    assert used["offer_appended"] is True and used["ideas"]
    # never in the payment, document or delivery states: not for a fix, not for "how exactly?"
    conversation.service_brief = {}
    conversation.flow_state = "S10_AWAITING_PAYMENT"
    for said in ("Can you tell me the solution", "how exactly would that work?"):
        assert await solution_context.build(business_db, scope, conversation, said, noted, {}) == {}
    assert asked["solution_build"]["says"] in {
        solutions.build_phrase(k) for k in solutions.CATALOGUE
    }
    await pi.close()
