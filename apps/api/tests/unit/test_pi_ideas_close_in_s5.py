"""R-VAL-06 (Book 3): a message with ideas never ends on nothing. Found by the real-model replay
(driving schools, 2026-10-26): at S5 the ideas ended after the second idea, no line, no question."""

from app.modules.pi import flow, solution_ask
from app.modules.pi.service_conversation import ServiceTurn, brain_offer

IDEAS = (
    "Yes.\nFirst, agree a cancellation rule and tell students when they book.\n"
    "Second, remind students the day before."
)
S5 = {
    "flow": {"state": "S5_READINESS"},
    "noted_problems": [{"ref": "a", "group": "x", "title": "Late cancellations"}],
    "solution_asked": True,
    "solution_ideas": ["First, ...", "Second, ..."],
    "reply_language": "en",
}


def test_ideas_at_the_open_offer_close_with_the_offer_and_the_move_stays_s5():
    t = ServiceTurn(reply=IDEAS)
    brain_offer(t, S5)
    assert t.reply.endswith(solution_ask.offer_line("en"))
    assert t._decision is None  # no state change: the chat stays at S5
    assert t.awaiting_customer


def test_it_does_not_double_up_when_the_reply_already_asks_or_offers():
    asked = ServiceTurn(reply=IDEAS + "\nWhich of these is hardest for you?")
    brain_offer(asked, S5)
    assert asked.reply == IDEAS + "\nWhich of these is hardest for you?"
    offered = ServiceTurn(reply=IDEAS + "\n" + solution_ask.offer_line("en"))
    brain_offer(offered, S5)
    assert offered.reply.count("solution document") == 1


def test_a_declined_offer_is_never_repeated_and_other_states_are_untouched():
    for state in (flow.State.S5B_DECLINED, flow.State.S6_PREPARING):
        t = ServiceTurn(reply=IDEAS)
        brain_offer(t, {**S5, "flow": {"state": state.name}})
        assert t.reply == IDEAS, state
    no_ideas = ServiceTurn(reply="Noted.")
    brain_offer(no_ideas, {k: v for k, v in S5.items() if k != "solution_ideas"})
    assert no_ideas.reply == "Noted."
