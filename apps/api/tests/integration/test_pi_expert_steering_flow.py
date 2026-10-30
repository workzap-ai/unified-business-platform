# ruff: noqa: E501
"""The expert advisor steering a real chat (webhook, worker, gates and database are real, the model
is scripted): a school-fee replay where the reply model drifts to "how do parents pay" and the
linter sends it back to the cached diagnosis; the idea caps per business and per problem across the
conversations of one customer."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_pi_brain_problems import create, say, workspace
from test_pi_expert_flow import (
    GOOD_ONE,
    GOOD_TWO,
    judged,
    reply_after,
    the_offer_is_open,  # noqa: F401 - autouse fixture of the expert flow tests
)
from test_pi_service_conversations import turn

from app.ai.manager import LLMManager
from app.modules.pi.models import PiConversation

pytestmark = pytest.mark.integration

OPENING = "Hi, main pi hoon, Workzap ka AI."
FIRST = "Mere school mein parents fee late dete hain"
TITLE = "Parents pay the school fee late"
HELLO = "hello"
IDENTITY = "Hi, main pi hoon, Workzap ka AI. Aap ke school ka naam kya hai?"
WHY = "Wo late fee dete waqt kya wajah batate hain?"
DRIFT = "Parents fee kaise jama karwate hain, challan, cash ya online?"
FEE_QUESTIONS = (
    "What reason do parents give when the fee comes late?",
    "Which week of the month does the fee come in latest?",
    "Do parents get any reminder before the due date?",
)


def light_diag(n: int) -> dict:
    return {
        "problem": "parents pay the fee late",
        "causes": [
            {"cause": "parents forget the due date", "evidence_for": [], "evidence_against": []},
            {
                "cause": "money runs short at month start",
                "evidence_for": [],
                "evidence_against": [],
            },
        ],
        "missing_fact": "why they are late",
        "question": FEE_QUESTIONS[min(n, len(FEE_QUESTIONS)) - 1],
    }


def fee_models(monkeypatch):
    """The reply model (drifts on the third message, then obeys the rewrite request) and the
    diagnosis call, by purpose. Returns what was sent to each."""
    sent: dict = {"replies": [], "diag": [], "rewrites": []}

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{") and json.loads(text).get("latest_customer_message") == HELLO:
            sent["last"] = turn(reply=IDENTITY, language="roman_ur")  # v1.5 18.2 opening
        elif text.startswith("{"):
            sent["replies"].append(json.loads(text))
            n = len(sent["replies"])
            if n == 1:
                value = turn(
                    reply=f"{OPENING} Fee ka masla yeh hai. {WHY}",
                    language="roman_ur",
                    problem_ops=[
                        create(
                            TITLE,
                            "parents fee late dete hain",
                            category="cash_collections",
                            subtype="receivables_late",
                            confidence=0.9,
                        )
                    ],
                )
            elif n == 2:
                value = turn(
                    reply="Wo kab tak de dete hain, mahine ke aakhir tak?", language="roman_ur"
                )
            else:
                value = turn(reply=f"Cash. {DRIFT}", language="roman_ur")
            sent["last"] = value
        else:
            sent["rewrites"].append(text)
            sent["last"] = turn(
                reply="Cash mein dete hain. Un ko yaad dilane wala koi hai jab fee ki tarikh qareeb aati hai?",
                language="roman_ur",
            )
        return SimpleNamespace(value=sent["last"], response=SimpleNamespace(attempts=[]))

    async def complete(self, scope, **kwargs):
        if kwargs["purpose"] == "pi_expert_diag":
            sent["diag"].append(json.loads(kwargs["messages"][-1].text()))
            return SimpleNamespace(text=json.dumps(light_diag(len(sent["diag"]))))
        raise RuntimeError("no other model call is scripted")

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    monkeypatch.setattr(LLMManager, "complete", complete)
    return sent


async def expert_workspace(api, db):
    pi = await workspace(api, db)
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
    return pi


async def test_the_replay_does_not_drift_to_how_parents_pay(api, business_db, monkeypatch):
    sent = fee_models(monkeypatch)
    pi = await expert_workspace(api, business_db)
    await say(pi, HELLO, "f-0")
    await say(pi, FIRST, "f-1")
    assert sent["replies"], "the reply model was not called"
    assert len(sent["diag"]) == 1, sent["replies"][0][
        "noted_problems"
    ]  # the diagnosis after the first message
    await say(pi, "wo bhool jate hain", "f-2")
    assert len(sent["diag"]) == 2  # the answer added a fact: refreshed once, cheaply
    assert sent["diag"][1]["facts_owner_already_answered"][-1] == "wo bhool jate hain"
    assert sent["diag"][1]["previous_diagnosis"]["causes"]
    assert '"ideas"' not in json.dumps(sent["diag"][1]["pi_already_said_do_not_repeat_or_reword"])
    bodies = await reply_after(pi, business_db, "cash", "f-3")
    assert len(bodies) == 1 and "challan" not in bodies[0], bodies
    assert sent["rewrites"] and "R-ASK-08" in sent["rewrites"][0]
    assert FEE_QUESTIONS[1] in sent["rewrites"][0]  # the cached question is named for the rewrite
    third = sent["replies"][2]
    assert third["main_problem"] == TITLE and third["main_problem_causes"]
    assert third["owner_answers_since"] == ["cash"]
    assert third["questions_already_asked"]
    assert len(sent["diag"]) == 3  # one diagnosis call per turn, never two in a turn
    await pi.close()


async def test_an_ok_does_not_pay_for_another_diagnosis(api, business_db, monkeypatch):
    sent = fee_models(monkeypatch)
    pi = await expert_workspace(api, business_db)
    await say(pi, HELLO, "g-0")
    await say(pi, FIRST, "g-1")
    await say(pi, "ok", "g-2")
    assert len(sent["diag"]) == 1
    await pi.close()


# --- the caps across the conversations of one customer -----------------------------------------


def expert_diag_model(monkeypatch, ideas):
    calls: list[str] = []

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{") and json.loads(text).get("latest_customer_message") == HELLO:
            return SimpleNamespace(
                value=turn(reply=IDENTITY, language="roman_ur"),
                response=SimpleNamespace(attempts=[]),
            )
        if text.startswith("{") and not calls:
            calls.append("reply")
            return SimpleNamespace(
                value=turn(
                    reply=f"{OPENING} Fee ka masla. {WHY}",
                    language="roman_ur",
                    problem_ops=[
                        create(
                            TITLE,
                            "parents fee late dete hain",
                            category="cash_collections",
                            confidence=0.9,
                        )
                    ],
                ),
                response=SimpleNamespace(attempts=[]),
            )
        return SimpleNamespace(
            value=turn(reply="Yes. Workzap can prepare a solution document for it.", language="en"),
            response=SimpleNamespace(attempts=[]),
        )

    async def complete(self, scope, **kwargs):
        calls.append(kwargs["purpose"])
        if kwargs["purpose"] == "pi_expert_diag":
            return SimpleNamespace(
                text=json.dumps(
                    {
                        **light_diag(1),
                        "ideas": [
                            {"idea": i, "addresses": "x", "assumes": [], "current_practice": "y"}
                            for i in ideas
                        ],
                    }
                )
            )
        if kwargs["purpose"] == "pi_expert_judge":
            return SimpleNamespace(text=json.dumps(judged(len(ideas))))
        raise RuntimeError("not scripted")

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    monkeypatch.setattr(LLMManager, "complete", complete)
    return calls


FEE_IDEAS = [
    "Ask three parents who paid late last month what made them late, so you hear the real reason from the parents themselves.",
    "Look at which families pay late again and again in the fee register, so you see whether it is the same few or many.",
]


async def sibling_chat(db, conversation, **brief):
    """Another (closed) chat of the same customer, with ideas already given in it."""
    db.add(
        PiConversation(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            customer_id=conversation.customer_id,
            connection_id=conversation.connection_id,
            contact_wa_id=conversation.contact_wa_id,
            status="closed",
            last_message_at=conversation.last_message_at,
            service_brief=brief,
        )
    )
    await db.flush()


async def start(api, db, monkeypatch, ideas=FEE_IDEAS):
    calls = expert_diag_model(monkeypatch, ideas)
    pi = await expert_workspace(api, db)
    await say(pi, HELLO, "h-0")
    await say(pi, FIRST, "h-1")
    conversation = await pi.conversation()
    return pi, conversation, calls


async def test_two_ideas_are_given_when_the_other_chats_left_room(api, business_db, monkeypatch):
    pi, conversation, calls = await start(api, business_db, monkeypatch)
    await sibling_chat(business_db, conversation, ideas_given=6)
    [body] = await reply_after(pi, business_db, "solution do", "h-2")
    assert body.count("•") == 2 and "register" in body
    row = await business_db.get(PiConversation, conversation.id)
    await business_db.refresh(row)
    assert row.service_brief["ideas_elsewhere"] == 6 and row.service_brief["ideas_given"] == 2
    await pi.close()


async def test_a_business_that_had_eight_in_other_chats_gets_none_and_the_honest_line(
    api, business_db, monkeypatch
):
    pi, conversation, calls = await start(api, business_db, monkeypatch)
    await sibling_chat(business_db, conversation, ideas_given=5)
    await sibling_chat(business_db, conversation, ideas_given=3)
    before = len(calls)
    [body] = await reply_after(pi, business_db, "solution do", "h-2")
    assert "•" not in body and "itne hi ideas" in body
    assert calls[before:] == []  # no call spent on a business with nothing left
    await pi.close()


async def test_a_problem_that_got_two_ideas_in_another_chat_is_closed_here(
    api, business_db, monkeypatch
):
    pi, conversation, calls = await start(api, business_db, monkeypatch)
    await sibling_chat(business_db, conversation, ideas_given=2, expert_given={TITLE: 2})
    [body] = await reply_after(pi, business_db, "solution do", "h-2")
    assert "•" not in body and "itne hi ideas" in body
    await pi.close()


async def test_only_the_same_business_in_the_same_workspace_counts(api, business_db, monkeypatch):
    from app.modules.pi import solution_context

    pi, conversation, calls = await start(api, business_db, monkeypatch)
    await sibling_chat(business_db, conversation, ideas_given=8)
    row = await business_db.get(PiConversation, conversation.id)
    other = SimpleNamespace(tenant_id=uuid4(), environment_id=conversation.environment_id)
    await solution_context.sync_elsewhere(business_db, other, row)  # type: ignore[arg-type]
    assert solution_context.elsewhere(row.service_brief) == 0  # another workspace: nothing
    here = SimpleNamespace(
        tenant_id=conversation.tenant_id, environment_id=conversation.environment_id
    )
    await solution_context.sync_elsewhere(business_db, here, row)  # type: ignore[arg-type]
    assert solution_context.elsewhere(row.service_brief) == 8
    await pi.close()


async def test_the_new_problem_gets_its_two_after_the_first_is_capped(
    api, business_db, monkeypatch
):
    pi, conversation, calls = await start(api, business_db, monkeypatch)
    row = await business_db.get(PiConversation, conversation.id)
    row.service_brief = {**row.service_brief, "ideas_given": 2, "expert_given": {TITLE: 2}}
    await business_db.flush()
    # the owner starts a different problem and asks for a fix in the same message
    seen = {"n": 0}

    async def structured(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        seen["n"] += 1
        return SimpleNamespace(
            value=turn(
                reply="Yes. Workzap can prepare a solution document for it.",
                language="en",
                problem_ops=[
                    create(
                        "Teachers leave in the middle of the year",
                        "teachers chhod jate hain, solution do",
                        category="people_staff",
                        confidence=0.9,
                    )
                ],
            ),
            response=SimpleNamespace(attempts=[]),
        )

    monkeypatch.setattr(LLMManager, "complete_structured", structured)
    teacher_ideas = [
        "Ask each teacher who left what finally made them decide, so you hear the real reason before the next one goes.",
        GOOD_TWO.replace("showroom", "school"),
    ]

    async def complete(self, scope, **kwargs):
        if kwargs["purpose"] == "pi_expert_diag":
            return SimpleNamespace(
                text=json.dumps(
                    {
                        "problem": "teachers leave in the middle of the year",
                        "causes": [
                            {"cause": "pay or workload", "evidence_for": [], "evidence_against": []}
                        ],
                        "missing_fact": "why they leave",
                        "question": "What do teachers say when they hand in their notice?",
                        "ideas": [
                            {"idea": i, "addresses": "x", "assumes": [], "current_practice": "y"}
                            for i in teacher_ideas
                        ],
                    }
                )
            )
        return SimpleNamespace(text=json.dumps(judged(2)))

    monkeypatch.setattr(LLMManager, "complete", complete)
    [body] = await reply_after(pi, business_db, "teachers chhod jate hain, solution do", "h-2")
    assert body.count("•") == 2 and "teacher" in body.lower()
    assert GOOD_ONE not in body
    await business_db.refresh(row)
    assert row.service_brief["ideas_given"] == 4
    await pi.close()
