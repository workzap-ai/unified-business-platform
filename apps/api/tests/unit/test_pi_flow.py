"""pi's conversation states and the legal moves between them (pi Brain spec, Part 3)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.pi import flow
from app.modules.pi.flow import State as S
from app.modules.pi.service_conversation import advance_flow, brain_context, greeting_reply

HAPPY_PATH = [
    S.S0_NEW, S.S1_LISTENING, S.S2_CLARIFYING, S.S3_NOTED, S.S4_SORTED_SUMMARY,
    S.S5_READINESS, S.S6_PREPARING, S.S7_DELIVERED, S.S8_REVIEW, S.S9_APPROVED,
    S.S10_AWAITING_PAYMENT, S.S11_PAYMENT_CONFIRMED, S.S12_KICKOFF, S.S13_IN_BUILD,
]  # fmt: skip


def test_every_state_has_moves_and_guidance():
    assert set(flow.TRANSITIONS) == set(S)
    assert set(flow.GUIDANCE) == set(S)
    assert len(S) == 28  # the Brain's states, S_ADVISE replaced by the six of Book 5, 11.1
    assert "S_ADVISE" not in {s.value for s in S}


def test_the_whole_journey_is_legal_one_step_at_a_time():
    for source, target in zip(HAPPY_PATH, HAPPY_PATH[1:], strict=False):
        assert flow.advance(source, target) == target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (S.S0_NEW, S.S4_SORTED_SUMMARY),  # no summary before anything was heard
        (S.S1_LISTENING, S.S5_READINESS),  # no offer while still listening
        (S.S4_SORTED_SUMMARY, S.S6_PREPARING),  # no document without the offer and a yes
        (S.S5_READINESS, S.S7_DELIVERED),  # delivery needs preparation
        (S.S7_DELIVERED, S.S9_APPROVED),  # approval needs a review first
        (S.S8_REVIEW, S.S10_AWAITING_PAYMENT),  # payment needs approval
        (S.S9_APPROVED, S.S11_PAYMENT_CONFIRMED),  # only after waiting for payment
        (S.S10_AWAITING_PAYMENT, S.S12_KICKOFF),  # kickoff needs confirmed payment
        (S.S11_PAYMENT_CONFIRMED, S.S9B_DECLINED_QUOTE),  # no cancelling after payment
        (S.S13_IN_BUILD, S.S1_LISTENING),
    ],
)
def test_skipping_a_step_is_refused(source, target):
    assert not flow.can_move(source, target)
    with pytest.raises(flow.IllegalTransition):
        flow.advance(source, target)


def test_the_listening_loop_and_the_decision_branches():
    assert flow.can_move(S.S3_NOTED, S.S1_LISTENING)  # a new problem
    assert flow.can_move(S.S2_CLARIFYING, S.S1_LISTENING)
    assert flow.can_move(S.S5_READINESS, S.S5B_DECLINED)  # "no" to the offer
    assert flow.can_move(S.S5B_DECLINED, S.S1_LISTENING)  # they add problems
    assert flow.can_move(S.S8_REVIEW, S.S8B_CHANGES_REQUESTED)
    assert flow.can_move(S.S8B_CHANGES_REQUESTED, S.S7_DELIVERED)  # revised version
    assert flow.can_move(S.S8_REVIEW, S.S9B_DECLINED_QUOTE)
    assert flow.can_move(S.S10_AWAITING_PAYMENT, S.S9B_DECLINED_QUOTE)  # cancel before payment


def test_any_state_can_move_to_an_exception_and_staying_is_fine():
    for source in S:
        for target in flow.EXCEPTIONS:
            assert flow.can_move(source, target)
        assert flow.can_move(source, source)


def test_leaving_an_exception_state():
    assert flow.can_move(S.X_HUMAN, S.S7_DELIVERED)  # a person hands back mid-journey
    assert flow.can_move(S.X_PAUSED, S.S5_READINESS)
    assert not flow.can_move(S.X_HUMAN, S.S0_NEW)
    assert flow.can_move(S.X_EMERGENCY, S.S1_LISTENING)
    assert not flow.can_move(S.X_EMERGENCY, S.S7_DELIVERED)  # an emergency never resumes there
    assert flow.can_move(S.X_BLOCKED, S.S1_LISTENING)
    assert not flow.can_move(S.X_BLOCKED, S.S5_READINESS)


def test_listening_states_and_the_no_offer_states():
    assert flow.LISTENING == {
        S.S0_NEW,
        S.S1_LISTENING,
        S.S2_CLARIFYING,
        S.S3_NOTED,
        S.S4_SORTED_SUMMARY,
    }
    assert S.S5B_DECLINED in flow.NO_OFFER and S.S5_READINESS not in flow.NO_OFFER


def test_allowed_next_lists_real_moves_only():
    moves = flow.allowed_next(S.S1_LISTENING)
    assert S.S2_CLARIFYING in moves and S.S3_NOTED in moves and S.X_EMERGENCY in moves
    assert S.S1_LISTENING not in moves and S.S5_READINESS not in moves


def test_a_state_name_is_parsed_or_ignored():
    assert flow.parse("S5b_DECLINED") == S.S5B_DECLINED
    assert flow.parse("nonsense") is None
    assert flow.parse(None) is None


def test_the_listening_loop_moves_on_its_own_events():
    assert flow.after_turn(S.S0_NEW, asked_question=False) == S.S1_LISTENING
    assert flow.after_turn(S.S0_NEW, asked_question=True) == S.S1_LISTENING
    assert flow.after_turn(S.S1_LISTENING, asked_question=True) == S.S2_CLARIFYING
    assert flow.after_turn(S.S2_CLARIFYING, asked_question=False) == S.S1_LISTENING
    # Offers, documents, approvals and payments never move because of a model's reply.
    for state in (
        S.S3_NOTED,
        S.S4_SORTED_SUMMARY,
        S.S5_READINESS,
        S.S8_REVIEW,
        S.S10_AWAITING_PAYMENT,
    ):
        assert flow.after_turn(state, asked_question=True) == state


def test_a_chat_that_already_has_a_reply_starts_listening():
    assert flow.initial_state(False) == S.S0_NEW
    assert flow.initial_state(True) == S.S1_LISTENING


def test_pi_mode_setting():
    from app.modules.pi.configuration import DEFAULTS

    assert DEFAULTS["response_rules"]["pi_mode"] == "standard"
    assert flow.brain_mode({"pi_mode": "brain"}) and not flow.brain_mode({"pi_mode": "standard"})
    assert not flow.brain_mode(None)
    assert flow.strict_voice({"pi_mode": "brain"})  # brain implies the linter
    assert flow.strict_voice({"constitution": True})
    assert not flow.strict_voice({})


def conversation(state=None):
    return SimpleNamespace(flow_state=state, flow_state_since=None)


def message(sender):
    return SimpleNamespace(sender_type=sender)


def test_brain_context_gives_a_new_chat_its_first_state_and_the_prompt_view():
    brain = SimpleNamespace(response_rules={"pi_mode": "brain"})
    chat = conversation()
    context = brain_context(brain, chat, [])
    assert chat.flow_state == "S0_NEW" and chat.flow_state_since is not None
    assert context["pi_mode"] == "brain" and context["strict_voice"] is True
    assert context["flow"]["state"] == "S0_NEW"
    assert "S1_LISTENING" in context["flow"]["allowed_next"]
    started = conversation()
    brain_context(brain, started, [message("customer"), message("ai")])
    assert started.flow_state == "S1_LISTENING"


def test_brain_context_keeps_a_chats_existing_state():
    chat = conversation("S5_READINESS")
    context = brain_context(SimpleNamespace(response_rules={"pi_mode": "brain"}), chat, [])
    assert context["flow"]["state"] == "S5_READINESS" and chat.flow_state == "S5_READINESS"


def test_standard_mode_has_no_state_and_the_linter_flag_alone_adds_only_strict_voice():
    chat = conversation()
    assert brain_context(SimpleNamespace(response_rules={}), chat, []) == {}
    assert chat.flow_state is None
    only_lint = brain_context(SimpleNamespace(response_rules={"constitution": True}), chat, [])
    assert only_lint == {"strict_voice": True} and chat.flow_state is None


def test_advance_flow_follows_the_question_and_stamps_the_time():
    chat = conversation("S0_NEW")
    advance_flow(chat, SimpleNamespace(reply="Which shop is it?"))
    assert chat.flow_state == "S1_LISTENING" and isinstance(chat.flow_state_since, datetime)
    advance_flow(chat, SimpleNamespace(reply="Which shop is it?"))
    assert chat.flow_state == "S2_CLARIFYING"
    advance_flow(chat, SimpleNamespace(reply="Noted."))
    assert chat.flow_state == "S1_LISTENING"
    offered = conversation("S5_READINESS")
    advance_flow(offered, SimpleNamespace(reply="Shall I go ahead?"))
    assert offered.flow_state == "S5_READINESS"
    assert offered.flow_state_since is None
    assert datetime.now(UTC)  # stamp is timezone-aware, checked above by isinstance


def test_advance_flow_ignores_a_chat_without_a_state():
    chat = conversation()
    advance_flow(chat, SimpleNamespace(reply="Which shop?"))
    assert chat.flow_state is None


def test_the_opening_is_the_fixed_line_in_brain_mode():
    english = greeting_reply({"pi_mode": "brain", "history": [], "company": "Workzap"})
    assert english == flow.OPENING["en"]
    assert english.startswith("Hi, I'm pi, an AI from Workzap.")
    roman = greeting_reply({"pi_mode": "brain", "history": [], "reply_language": "roman_ur"})
    assert roman == flow.OPENING["roman_ur"]
    shared = greeting_reply({"history": [], "company": "Workzap"})
    assert "reads this chat" in shared  # the standard intro is unchanged


def test_path_finds_the_legal_steps_between_states():
    assert flow.path(S.S0_NEW, S.S0_NEW) == []
    assert flow.path(S.S0_NEW, S.S1_LISTENING) == [S.S1_LISTENING]
    assert flow.path(S.S0_NEW, S.S3_NOTED) == [S.S1_LISTENING, S.S3_NOTED]
    assert flow.path(S.S1_LISTENING, S.S4_SORTED_SUMMARY) == [S.S3_NOTED, S.S4_SORTED_SUMMARY]
    assert flow.path(S.S7_DELIVERED, S.S9_APPROVED) == [S.S8_REVIEW, S.S9_APPROVED]
    assert flow.path(S.S5_READINESS, S.X_HUMAN) == [S.X_HUMAN]  # an exception is one move
    assert flow.path(S.S13_IN_BUILD, S.S1_LISTENING) is None  # nothing leads back
    chain = [S.S0_NEW, *(flow.path(S.S0_NEW, S.S13_IN_BUILD) or [])]
    assert chain[-1] == S.S13_IN_BUILD
    for step_from, step_to in zip(chain, chain[1:], strict=False):
        assert flow.can_move(step_from, step_to)


def test_s_listen_think_takes_the_old_s_advise_moves():
    think = S.S_LISTEN_THINK
    for source in (
        S.S1_LISTENING,
        S.S2_CLARIFYING,
        S.S3_NOTED,
        S.S4_SORTED_SUMMARY,
        S.S5B_DECLINED,
    ):
        assert flow.can_move(source, think)
    for target in (S.S1_LISTENING, S.S5_READINESS, S.S6_PREPARING, S.S5B_DECLINED, S.X_PAUSED):
        assert flow.can_move(think, target)
    assert not flow.can_move(think, S.S7_DELIVERED)
    assert think not in flow.NO_OFFER and think not in flow.LISTENING


def test_a_stored_s_advise_reads_as_s_listen_think():
    assert flow.parse("S_ADVISE") == S.S_LISTEN_THINK
    assert flow.parse("S_HOLD") == S.S_HOLD
    assert flow.parse("nonsense") is None


def test_the_book_5_states_have_sensible_moves():
    assert flow.can_move(S.S_LISTEN_THINK, S.S_MAP_SHARE)
    assert flow.can_move(S.S_MAP_SHARE, S.S_BOX_OFFER)
    assert flow.can_move(S.S_BOX_OFFER, S.S_BOX_DRAFT)
    assert flow.can_move(S.S_BOX_DRAFT, S.S6_PREPARING)
    assert not flow.can_move(S.S1_LISTENING, S.S_BOX_OFFER)  # only through the thinking step
    assert not flow.can_move(S.S_HOLD, S.S_BOX_OFFER)  # no offer after a heavy disclosure
    assert S.S_HOLD in flow.NO_OFFER
    assert flow.can_move(S.S_HOLD, S.X_EMERGENCY)  # emergency states stay reachable from all
