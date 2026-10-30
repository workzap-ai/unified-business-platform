# ruff: noqa: E501
"""solution_source "expert" in a real chat: webhook, worker, gates and database are real; the model
is scripted (the reply model by context, the expert pipeline by purpose)."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import adaptive, create, say, workspace
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi import decisions, expert_advisor
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration

OPENING = "Hi, I'm pi, an AI from Workzap."
SHOWROOM = "I run a car showroom and fewer people walk in than before, footfall is low"
VIDEO_IDEA = (
    "Pin a short video of your best cars on your page, so people stop and look at the showroom."
)
GOOD_ONE = "Ask each recent buyer how they first heard of the showroom, so you see which way people really find you."
GOOD_TWO = "Stand outside the showroom as a passer-by would and note what you see first, so you spot what keeps people walking past."
ROMAN = "Mere car showroom mein pehle se kam log aa rahe hain, footfall bohat kam hai"
QUESTION = "Has footfall dropped everywhere, or only since a new showroom opened nearby?"
TRACKING = "Ask each salesperson to say aloud at the end of the day who they sold to, so the sheet and the sales match."


@pytest.fixture(autouse=True)
def the_offer_is_open(monkeypatch):
    from app.modules.pi import box

    monkeypatch.setattr(box, "box_offer_enabled", lambda rules: True)
    monkeypatch.setattr(box, "can_offer", lambda facts: (True, "R2", "held open for this journey"))


def expert_model(monkeypatch, diagnosis: dict, judge: dict | None = None):
    calls: list[str] = []

    async def complete(self, scope, **kwargs):
        calls.append(kwargs["purpose"])
        if kwargs["purpose"] == "pi_expert_diag":
            return SimpleNamespace(text=json.dumps(diagnosis))
        if kwargs["purpose"] == "pi_expert_judge":
            return SimpleNamespace(text=json.dumps(judge or {}))
        raise RuntimeError("no other model call is scripted")  # free ideas: falls back to nothing

    monkeypatch.setattr(LLMManager, "complete", complete)
    return calls


def diagnosis(ideas, problem="fewer people walk into the showroom", question=QUESTION):
    return {
        "problem": problem,
        "causes": [
            {
                "cause": "people do not know the showroom exists",
                "evidence_for": [],
                "evidence_against": [],
            },
            {"cause": "competitor nearby", "evidence_for": [], "evidence_against": []},
        ],
        "missing_fact": "whether footfall fell everywhere",
        "question": question,
        "ideas": [
            {"idea": i, "addresses": "awareness", "assumes": [], "current_practice": "ask buyers"}
            for i in ideas
        ],
    }


def judged(n):
    return {
        "scores": [{"i": i, **{q: 5 for q in expert_advisor.QUALITIES}} for i in range(n)],
        "best": [{"i": 0, "reason": "a"}, {"i": 1, "reason": "b"}][: min(n, 2)],
    }


def scripted(title, words, category="marketing_leads", subtype="brand_awareness"):
    def make(context, n):
        if n == 1:
            return turn(
                reply=f"{OPENING} Thanks. I've noted it: {title}.",
                language="en",
                problem_ops=[
                    create(title, words, category=category, subtype=subtype, confidence=0.9)
                ],
            )
        if context.get("solution_asked_no_ideas"):
            return turn(reply="Yes. Workzap can prepare a solution document for it.", language="en")
        return turn(reply="Noted. Who follows up the enquiries once they come in?", language="en")

    return make


async def expert_chat(api, db, monkeypatch, first, title, words, **kw):
    prompts = adaptive(monkeypatch, scripted(title, words, **kw))
    pi = await workspace(api, db)
    pi.prompts = prompts
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={
            "value": {
                "brain": {
                    "solution_mode": True,
                    "solution_source": "expert",
                    "learning_frozen": False,
                }
            }
        },
    )
    assert response.status_code == 200, response.text
    await say(pi, first, "x-1")
    return pi


async def reply_after(pi, db, text, key):
    before = set(await db.scalars(select(PiMessage.id)))
    await say(pi, text, key)
    fresh = [
        m
        for m in await db.scalars(select(PiMessage))
        if m.id not in before and m.direction == "outbound"
    ]
    return [m.body for m in fresh]


async def test_the_showroom_gets_grounded_ideas_and_no_video_or_page(api, business_db, monkeypatch):
    calls = expert_model(monkeypatch, diagnosis([VIDEO_IDEA, GOOD_ONE, GOOD_TWO]), judged(3))
    pi = await expert_chat(
        api, business_db, monkeypatch, SHOWROOM, "Few walk-ins at the showroom", SHOWROOM
    )
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert "pi_expert_diag" in calls  # the diagnosis was cached after the first message
    bodies = await reply_after(pi, business_db, "give me a solution", "x-2")
    assert len(bodies) == 1, bodies
    [body] = bodies
    low = body.lower()
    assert "video" not in low and "page" not in low
    bullets = [line for line in body.splitlines() if line.startswith("•")]
    assert len(bullets) == 2 and GOOD_ONE.rstrip(".") in body
    await business_db.refresh(conversation)
    assert conversation.service_brief["ideas_given"] == 2
    assert "pi_expert_judge" in calls
    await pi.close()


async def test_the_next_question_targets_the_main_problem_not_an_adjacent_process(
    api, business_db, monkeypatch
):
    expert_model(monkeypatch, diagnosis([GOOD_ONE, GOOD_TWO]), judged(2))
    pi = await expert_chat(
        api, business_db, monkeypatch, SHOWROOM, "Few walk-ins at the showroom", SHOWROOM
    )
    await reply_after(pi, business_db, "it has been like this for a while", "x-2")
    sent = json.loads([p for p in pi.prompts if p.startswith("{")][-1])
    assert sent["main_problem"] == "Few walk-ins at the showroom"
    assert sent["main_problem_causes"][0].startswith("people do not know")
    assert sent["suggested_next_question"] == QUESTION
    # the brief's cache is the application's: the model sees the context keys, not the raw cache
    assert "expert_diag" not in sent["brief"] and "expert_given" not in sent["brief"]
    await pi.close()


async def test_when_every_idea_fails_pi_asks_the_footfall_question_and_gives_no_idea(
    api, business_db, monkeypatch
):
    expert_model(monkeypatch, diagnosis([VIDEO_IDEA]), judged(1))
    pi = await expert_chat(
        api, business_db, monkeypatch, SHOWROOM, "Few walk-ins at the showroom", SHOWROOM
    )
    [body] = await reply_after(pi, business_db, "give me a solution", "x-2")
    assert QUESTION in body and "•" not in body
    assert "video" not in body.lower()
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.service_brief.get("ideas_given", 0) == 0
    await pi.close()


async def test_a_price_question_with_the_fact_question_gets_one_question_and_no_number(
    api, business_db, monkeypatch
):
    """Auditor residual risk: when no idea survives and the owner also asks the price, the reply
    answers the price first in a statement, then the one-more-fact question (one question, last,
    no figure, no quote started)."""
    expert_model(monkeypatch, diagnosis([VIDEO_IDEA]), judged(1))
    pi = await expert_chat(
        api, business_db, monkeypatch, SHOWROOM, "Few walk-ins at the showroom", SHOWROOM
    )
    [body] = await reply_after(pi, business_db, "give me a solution, how much will it cost?", "x-2")
    assert body.startswith(decisions.cost_answer("en"))  # the price question is answered first
    assert "I need one more fact" in body and QUESTION in body
    assert body.count("?") == 1 and body.rstrip().endswith("?")
    assert not any(ch.isdigit() for ch in body)
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state != "S6_PREPARING"
    await pi.close()


async def test_an_explicit_quote_ask_with_a_price_question_starts_the_quote_not_the_fact_question(
    api, business_db, monkeypatch
):
    """Audit L1: with an explicit ask for the quote the gate starts it (R1); the cost line and the
    one-more-fact question do not take its place or come out in the wrong order."""
    expert_model(monkeypatch, diagnosis([VIDEO_IDEA]), judged(1))
    pi = await expert_chat(
        api, business_db, monkeypatch, SHOWROOM, "Few walk-ins at the showroom", SHOWROOM
    )
    [*bodies] = await reply_after(
        pi, business_db, "how much will it cost? send me the quote", "x-2"
    )
    body = " ".join(bodies)
    conversation = await pi.conversation()
    await business_db.refresh(conversation)
    assert conversation.flow_state == "S6_PREPARING"
    assert "I need one more fact" not in body
    assert not any(ch.isdigit() for ch in body)
    await pi.close()


async def test_the_cost_line_is_kept_out_of_the_language_rewrite(api, business_db, monkeypatch):
    """The fixed cost answer promises no figure and no range; a model rewrite of the English
    question must never see it, so a figure the rewrite invents cannot reach the cost line."""
    from app.modules.pi import service_conversation as conversation_service

    seen: list[str] = []

    async def rewrite(manager, scope, policy, conversation, text, language):
        seen.append(text)
        return f"{text} (Rs 5000)"  # a rewrite that invents a figure

    monkeypatch.setattr(conversation_service, "in_one_language", rewrite)
    expert_model(monkeypatch, diagnosis([VIDEO_IDEA]), judged(1))
    pi = await expert_chat(
        api, business_db, monkeypatch, ROMAN, "Few walk-ins at the showroom", SHOWROOM
    )
    bodies = await reply_after(pi, business_db, "give me a solution, kitna kharcha hoga?", "x-2")
    body = " ".join(bodies)
    cost = decisions.cost_answer("roman_ur")
    assert seen, "the rewrite path must run"
    if seen:  # the rewrite ran: it never saw the cost line, and the line is in the reply intact
        assert all(cost not in text for text in seen)
        assert cost in body
        assert not any(ch.isdigit() for ch in cost)
    await pi.close()


async def test_sales_tracking_gets_an_idea_not_no_quick_idea(api, business_db, monkeypatch):
    owner = "My sales team does not update the sheet, so I never know who sold what"
    expert_model(
        monkeypatch,
        diagnosis([TRACKING, GOOD_TWO], problem="the team does not record its sales"),
        judged(2),
    )
    pi = await expert_chat(
        api,
        business_db,
        monkeypatch,
        owner,
        "Sales team does not track sales",
        owner,
        category="sales_revenue",
        subtype="no_sales_visibility",
    )
    [body] = await reply_after(pi, business_db, "can you give me a solution", "x-2")
    assert "quick idea" not in body
    assert "•" in body and "sheet" in body
    await pi.close()


async def test_without_the_flag_the_expert_is_never_called(api, business_db, monkeypatch):
    calls = expert_model(monkeypatch, diagnosis([GOOD_ONE, GOOD_TWO]), judged(2))
    prompts = adaptive(monkeypatch, scripted("Few walk-ins at the showroom", SHOWROOM))
    pi = await workspace(api, business_db)
    pi.prompts = prompts
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"brain": {"solution_mode": True, "learning_frozen": False}}},
    )
    assert response.status_code == 200, response.text
    await say(pi, SHOWROOM, "x-1")
    await reply_after(pi, business_db, "give me a solution", "x-2")
    assert not [c for c in calls if c.startswith("pi_expert")]
    sent = json.loads([p for p in pi.prompts if p.startswith("{")][-1])
    assert "main_problem" not in sent
    await pi.close()
