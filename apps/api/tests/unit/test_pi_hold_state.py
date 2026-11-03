"""Platform spec v1.4, 11.1 S_HOLD (G46, RT48): entered live after a heavy disclosure."""

from types import SimpleNamespace
from typing import Any

from app.modules.pi import flow, hold, turn_state

S = flow.State


def convo(state: flow.State = S.S1_LISTENING) -> SimpleNamespace:
    return SimpleNamespace(flow_state=state.value, flow_state_since=None, service_brief={})


def test_heavy_disclosures_and_distress_are_heavy() -> None:
    assert hold.heavy(
        "meri salary dene ke paise nahi hain aur bohat pareshan hoon", first_message=True
    )
    assert hold.heavy("I can't take it any more, I give up")
    assert hold.heavy("mujhe bohat gussa hai in logon par")
    assert not hold.heavy("stock kam hai is hafte")
    assert not hold.heavy("customers gussa ho jate hain jab late hota hai")


def test_a_heavy_message_holds_a_listening_chat_and_the_next_one_releases_it() -> None:
    c = convo()
    said = "I can't take it any more, the debts are crushing me"
    assert turn_state.enter(c, S.S1_LISTENING, said, ["hello"], {}) == S.S_HOLD
    assert c.flow_state == "S_HOLD"
    calm = "theek hai, ab stock ki baat karte hain"
    assert turn_state.enter(c, S.S_HOLD, calm, ["a"], {}) == S.S1_LISTENING
    assert c.flow_state == "S1_LISTENING"


def test_a_message_that_is_still_heavy_stays_on_hold() -> None:
    c = convo(S.S_HOLD)
    assert turn_state.enter(c, S.S_HOLD, "I give up, truly hopeless", ["a"], {}) == S.S_HOLD


def test_a_heavy_first_message_goes_through_listening_to_hold() -> None:
    c = convo(S.S0_NEW)
    state = turn_state.enter(c, S.S0_NEW, "I can't cope, wages are due", [], {})
    assert state == S.S_HOLD and c.flow_state == "S_HOLD"


def test_an_owner_who_also_asks_for_ideas_is_not_held() -> None:
    c = convo()
    said = "debts are crushing me, what is your solution? please suggest ideas"
    assert turn_state.enter(c, S.S1_LISTENING, said, ["a"], {}) == S.S1_LISTENING


def test_offer_documents_and_exceptions_are_never_put_on_hold() -> None:
    for state in (S.S5_READINESS, S.S8_REVIEW, S.X_HUMAN, S.X_EMERGENCY):
        c = convo(state)
        assert turn_state.enter(c, state, "I can't take it any more, I give up", ["a"], {}) == state


def test_a_held_turn_loses_its_solution_context_and_gets_the_note() -> None:
    ctx: dict[str, Any] = {
        "flow": {"state": "S_HOLD"},
        "solution_ideas": ["x"],
        "solution_asked": True,
        "open_ask": True,
    }
    out = hold.clear_solutions(ctx)
    assert "solution_ideas" not in out and "solution_asked" not in out and out["hold_note"]
    free = {"flow": {"state": "S1_LISTENING"}, "solution_ideas": ["x"]}
    assert hold.clear_solutions(dict(free)) == free


def test_a_held_reply_with_ideas_or_a_chain_of_questions_is_rewritten() -> None:
    ctx = {"flow": {"state": "S_HOLD"}}
    ideas = "That sounds heavy.\n• Count stock weekly.\n• Call late payers."
    assert "no ideas" in (turn_state.guard(ideas, ctx) or "")
    assert "questions" in (turn_state.guard("Kab se? Kitna? Kyun?", ctx) or "")
    assert turn_state.guard("Ye bohat bhari hai. Kya aap bata sakte hain kab se?", ctx) is None
    assert turn_state.guard(ideas, {"flow": {"state": "S1_LISTENING"}}) is None
