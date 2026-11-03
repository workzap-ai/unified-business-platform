"""Tests that close gaps the rule index (rule_index.json) found: rules that had code but no test of
their own, rules that were only in the prompt, and one rule the code broke. No database."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi import business_form, decisions, flow, followup_policy, safety, spec_handbook
from app.modules.pi import service_conversation as sc
from app.modules.pi_saas import models as saas_models
from app.modules.pi_saas import requests as team_requests

S = flow.State


# --- R-CONV-01..04 ("No forms. Just chat.", promise P2) ------------------------------------------


def _form_case(rules: dict[str, str]):
    """A chat where pi has asked for the business once already and asks again now: the point at
    which the older code sends the 'Business details' form. The session cannot be used, so a
    path that goes on to send or queue anything raises."""
    conversation = SimpleNamespace(
        id=uuid4(), service_brief={"business_asks": 1}, language="en", customer_id=uuid4()
    )
    policy = SimpleNamespace(response_rules=rules, whatsapp_config={})
    return conversation, policy


def test_brain_mode_never_sends_the_business_form():
    conversation, policy = _form_case({"pi_mode": "brain"})
    reply = "Which business is this for, a shop or a farm?"
    asyncio.run(
        business_form.after_turn(
            None, None, conversation, SimpleNamespace(id=uuid4()), policy, reply, "calm"
        )  # type: ignore[arg-type]
    )
    assert conversation.service_brief == {"business_asks": 1}  # not even counted


def test_the_other_mode_still_reaches_the_form_so_the_test_above_proves_something():
    conversation, policy = _form_case({})
    reply = "Which business is this for, a shop or a farm?"
    with pytest.raises(AttributeError):  # the unusable session was touched: the form path ran
        asyncio.run(
            business_form.after_turn(
                None, None, conversation, SimpleNamespace(id=uuid4()), policy, reply, "calm"
            )  # type: ignore[arg-type]
        )


# --- R-CANT-03: nothing pi can do helps, so it passes it to the team (reason cant_help) ----------


def test_cant_help_is_an_escalation_reason_with_a_ticket_text_and_kind():
    kind, priority = team_requests.escalation_route("cant_help")
    assert kind == "cant_help" and kind in saas_models.REQUEST_KINDS
    assert priority == "high"
    assert "cant_help" in saas_models.ESCALATION_KINDS


def test_in_brain_mode_ask_team_raises_a_cant_help_escalation(monkeypatch):
    raised: list[tuple[str, str]] = []

    async def record(session, scope, conversation, reason, question, said=""):
        raised.append((reason, question))

    monkeypatch.setattr(sc, "raise_escalation", record)
    brain_chat = SimpleNamespace(
        id=uuid4(), customer_id=uuid4(), flow_state=S.S2_CLARIFYING.value, service_brief={}
    )
    asyncio.run(sc.ask_team(None, None, brain_chat, "Wants a refund on a car.", "fix my car"))  # type: ignore[arg-type]
    assert [reason for reason, _ in raised] == ["cant_help"]
    assert "pi could not help" in raised[0][1]


# --- R-KICK-03: no kickoff agenda beyond "to agree the details" ----------------------------------


def test_the_kickoff_is_only_described_as_agreeing_the_details():
    for language in ("en", "roman_ur"):
        confirmed = decisions.text("payment_confirmed", language)
        assert "agenda" not in confirmed.lower() and "kickoff" in confirmed.lower()
    assert "agree the details" in decisions.text("payment_confirmed", "en")
    assert "agree the details" in flow.GUIDANCE[S.S12_KICKOFF]
    for kind in ("kickoff_24h", "kickoff_1h"):
        for language in ("en", "roman_ur"):
            line = followup_policy.text_for(kind, language, when="Monday 10:00")
            assert "Monday 10:00" in line
            assert not any(
                word in line.lower() for word in ("agenda", "we will cover", "bring", "prepare")
            )


# --- X5: business distress is not an emergency; the distress guidance is in the prompt -----------


@pytest.mark.parametrize(
    "said",
    ["I'm going bankrupt", "we will shut down next month", "I can't pay salaries this week"],
)
def test_business_distress_is_not_an_emergency_and_brings_the_distress_guidance(said):
    assert safety.emergency(said) is None
    assert safety.advice_asked(said) is None
    rules, _ = spec_handbook.chosen_ids("S1_LISTENING", said)
    assert "7.N.distress" in rules and "6.5" in rules
    book = spec_handbook.sections()
    assert book["7.N.distress"]["text"].strip() and book["6.5"]["text"].strip()


# --- the rules that live only in the prompt are really in it (R-PRIV-08, R-VOICE-11/13, ...) ----


@pytest.mark.parametrize(
    "rule",
    ["R-PRIV-08", "R-VOICE-11", "R-VOICE-13", "R-ASK-04", "R-ASK-05", "R-CANT-01", "R-CANT-02"],
)
def test_a_prompt_only_rule_is_in_the_text_pi_reads_while_listening(rule):
    assert rule in spec_handbook.guidance("S1_LISTENING"), f"{rule} is no longer in the prompt"


# --- Addendum 2 Job S8: the first question people answer with less is retired -------------------


class _Rows:
    """Just enough of an async session for learn_ask_first: it reads rows and flushes."""

    def __init__(self, rows):
        self.rows = rows

    async def scalars(self, query):
        return self.rows

    async def flush(self):
        return None


def _ask(key: str, engaged: int, flat: int, problem: str = "stock_out"):
    from app.modules.pi import solution_ideas
    from app.modules.pi.solution_models import PiIdeaArm

    return PiIdeaArm(
        arm_key=key,
        industry_key="retail_shops",
        problem_id=problem,
        language="en",
        text=f"Which item {key}?",
        kind=solution_ideas.ASK,
        status="active",
        stats={"ask_engaged": engaged, "ask_flat": flat},
    )


def test_the_ask_first_question_people_answer_less_is_retired():
    from app.modules.pi import learning_solutions
    from app.shared.scope import WorkspaceScope

    scope = WorkspaceScope.system(uuid4(), uuid4(), frozenset(), "learning")
    good = _ask("runs out most", engaged=40, flat=10)  # 80% engage
    poor = _ask("sells least", engaged=10, flat=40)  # 20% engage, 50 seen
    young = _ask("is new", engaged=1, flat=9, problem="late_cash")  # alone for its problem
    thin = _ask("has few answers", engaged=2, flat=8)  # too few answers to judge
    result = asyncio.run(
        learning_solutions.learn_ask_first(_Rows([good, poor, young, thin]), scope)
    )  # type: ignore[arg-type]
    assert result == {"asks_retired": 1}
    assert poor.status == "retired" and poor.retired_reason
    assert {good.status, young.status, thin.status} == {"active"}


# --- R-VOICE-13: contractions are fine in English --------------------------------------------


def test_contractions_are_fine_in_english():
    from app.modules.pi import constitution

    context = {
        "latest_customer_message": "my stock keeps running out",
        "history": [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
    }
    reply = (
        "Thanks. I've noted it: stock that's running out. We'll go one shop at a time. Which one?"
    )
    assert constitution.lint(reply, context) == []


# --- spec 1.9: the order of priority when rules collide ------------------------------------------


def _gate(said: str, **extra):
    context = {
        "latest_customer_message": said,
        "reply_language": "en",
        "history": [{"role": "ai"}],
        **extra,
    }
    return sc.brain_safety(context)


def test_the_gates_run_in_the_specs_priority_order():
    everything = (
        "Fire in my shop! Are you a real person? Is it legal to fire staff? "
        "Give me a discount and send me your bank details."
    )
    emergency = _gate(everything)
    assert emergency is not None and emergency._decision.why == "R-EMER"
    assert emergency._decision.next_state == S.X_EMERGENCY
    without_fire = everything.replace("Fire in my shop! ", "")
    identity = _gate(without_fire)
    assert identity is not None and identity._decision.why == "R-DISC"  # honesty before advice
    without_identity = without_fire.replace("Are you a real person? ", "")
    advice = _gate(without_identity)
    assert advice is not None and advice._decision.why == "R-ADV"  # advice before the person's asks
    money = _gate("Give me a discount and send me your bank details.")
    assert money is not None and money._decision.why == "R-BOUNDARY"
