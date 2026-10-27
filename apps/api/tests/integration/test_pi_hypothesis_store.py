# ruff: noqa: E501
"""The hypothesis ledger is updated from the owner's reply (Book 5, Part 3.5), behind
response_rules.brain.thinking: evidence for or against, a question left unanswered marked ignored,
`confirmed` only by an explicit owner yes, stored strings redacted, nothing when thinking is off."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_brain_problems import say, workspace

from app.ai.manager import LLMManager
from app.modules.pi.service_conversation import ServiceTurn, ThinkingServiceTurn
from app.modules.pi.think_models import PiHypothesis
from app.modules.pi.think_plan import MovePlan

pytestmark = pytest.mark.integration

HYPOTHESIS = "parents forget the due date because nobody reminds them"
FIRST = "Mere school mein parents fee late dete hain"
ASKING = "I have a guess and I may be wrong: parents forget the due date because nobody reminds them. Is that the reason?"


def script(monkeypatch, thinking: bool = True):
    calls: dict = {"first": True}

    async def complete(self, scope, output, **kwargs):
        if kwargs.get("purpose") == "pi_problem_extract":
            return SimpleNamespace(value=output(), response=SimpleNamespace(attempts=[]))
        text = kwargs["messages"][-1].text()
        if text.startswith("{"):  # a rewrite request repeats the turn built for the last message
            calls["first"] = json.loads(text)["latest_customer_message"] == FIRST
        first = calls["first"]
        # the first message asks the hypothesis question; later ones are plain Roman Urdu questions
        reply = ASKING if first else "Theek hai. Is mein kitne parents shamil hain?"
        language = "en" if first else "roman_ur"
        if thinking:
            plan = MovePlan(
                move="M4_hypothesis" if first else "ask",
                reason="test the leading cause",
                asks_question=True,
            )
            value = ThinkingServiceTurn(reply=reply, language=language, move_plan=plan)
        else:
            value = ServiceTurn(reply=reply, language=language)
        return SimpleNamespace(value=value, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)


async def start(api, db, monkeypatch, *, thinking=True, confidence="low"):
    script(monkeypatch, thinking)
    pi = await workspace(api, db)
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": {"thinking": True} if thinking else {}}},
    )
    assert response.status_code == 200, response.text
    await say(pi, FIRST, "hy-1")
    conversation = await pi.conversation()
    db.add(
        PiHypothesis(
            tenant_id=conversation.tenant_id,
            environment_id=conversation.environment_id,
            conversation_id=conversation.id,
            text=HYPOTHESIS,
            evidence_for=[],
            evidence_against=[],
            confidence=confidence,
            cheapest_test="ask when the last reminder went out",
            status="open",
            ignored=False,
        )
    )
    await db.flush()
    return pi


async def ledger(db) -> PiHypothesis:
    rows = list(await db.scalars(select(PiHypothesis)))
    assert len(rows) == 1
    await db.refresh(rows[0])
    return rows[0]


async def test_an_explicit_yes_to_the_hypothesis_question_confirms_it(
    api, business_db, monkeypatch
):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, "haan bilkul, wo bhool jate hain", "hy-2")
    row = await ledger(business_db)
    assert row.status == "confirmed" and row.confidence == "high"
    assert row.evidence_for == ["haan bilkul, wo bhool jate hain"]
    await pi.close()


async def test_a_reply_that_supports_the_cause_adds_evidence_but_never_confirms(
    api, business_db, monkeypatch
):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, "parents due date bhool jate hain, koi unko reminder nahi bhejta", "hy-2")
    row = await ledger(business_db)
    assert row.status == "open" and row.confidence == "medium"
    assert len(row.evidence_for) == 1 and row.evidence_against == []
    await pi.close()


async def test_a_reply_that_contradicts_it_adds_evidence_against(api, business_db, monkeypatch):
    pi = await start(api, business_db, monkeypatch, confidence="medium")
    await say(pi, "nahi, ye wajah nahi hai, paise nahi hote unke paas", "hy-2")
    row = await ledger(business_db)
    assert row.status == "open" and row.confidence == "low"
    assert row.evidence_against == ["nahi, ye wajah nahi hai, paise nahi hote unke paas"]
    await pi.close()


async def test_evidence_against_a_low_confidence_hypothesis_drops_it(api, business_db, monkeypatch):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, "nahi, ye wajah nahi hai", "hy-2")
    assert (await ledger(business_db)).status == "dropped"
    await pi.close()


@pytest.mark.parametrize("said", ["ok", "pata nahi", "solution do", "kitna kharcha aayega?"])
async def test_a_deflected_hypothesis_question_is_marked_ignored(
    api, business_db, monkeypatch, said
):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, said, "hy-2")
    row = await ledger(business_db)
    assert row.ignored is True and row.status == "open" and row.evidence_for == []
    await pi.close()


async def test_stored_evidence_is_redacted(api, business_db, monkeypatch):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, "haan parents due date bhool jate hain, mujhe 0300 1234567 par call karo", "hy-2")
    row = await ledger(business_db)
    assert row.evidence_for and "1234567" not in row.evidence_for[0]
    await pi.close()


async def test_the_same_message_twice_does_not_double_the_evidence(api, business_db, monkeypatch):
    pi = await start(api, business_db, monkeypatch)
    await say(pi, "parents due date bhool jate hain, koi unko reminder nahi bhejta", "hy-2")
    await say(pi, "parents due date bhool jate hain, koi unko reminder nahi bhejta", "hy-3")
    row = await ledger(business_db)
    assert len(row.evidence_for) == 1
    await pi.close()


async def test_with_thinking_off_the_ledger_is_never_touched(api, business_db, monkeypatch):
    pi = await start(api, business_db, monkeypatch, thinking=False)
    await say(pi, "haan bilkul, wo bhool jate hain", "hy-2")
    row = await ledger(business_db)
    assert row.status == "open" and row.evidence_for == [] and row.ignored is False
    await pi.close()
