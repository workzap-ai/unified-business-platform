"""The offer and decision gates: reading a yes, and pi's fixed replies and moves
(pi Brain spec 3.8, 5.5, 5.6, 6.4)."""

import pytest

from app.modules.pi import decisions as d
from app.modules.pi.decisions import Answer
from app.modules.pi.flow import State as S


@pytest.mark.parametrize(
    "said",
    [
        "yes", "Yes!", "yeah", "sure", "yes please", "go ahead", "okay go ahead", "haan",
        "ji", "ji haan", "theek hai", "haan kar do", "bilkul", "bana do", "👍", "نعم", "جی ہاں",
        "haan theek hai bana do",
    ],
)  # fmt: skip
def test_a_plain_yes_is_an_explicit_yes(said):
    answer, confidence = d.classify(said)
    assert answer == Answer.YES and confidence >= d.YES_AT


@pytest.mark.parametrize(
    "said",
    [
        "ok", "okay", "hmm", "hmmm", "maybe", "let me think", "I'll think about it",
        "dekhte hain", "how much?", "yes but how much", "yes, if it is cheap",
        "please explain how it works", "ji aap ka rate kya hai", "what does it cost", "",
    ],
)  # fmt: skip
def test_ok_hmm_maybe_and_hedged_answers_are_not_a_yes(said):
    answer, _ = d.classify(said)
    assert answer != Answer.YES


@pytest.mark.parametrize(
    "said", ["no", "No thanks", "nope", "nahi", "nahi shukriya", "not interested", "لا", "نہیں"]
)
def test_a_no(said):
    assert d.classify(said)[0] == Answer.NO


@pytest.mark.parametrize("said", ["later", "not now", "baad mein", "abhi nahi", "maybe later"])
def test_later_is_not_a_no(said):
    assert d.classify(said)[0] == Answer.LATER


def test_the_button_titles_fit_whatsapp():
    for group in (d.OFFER_BUTTONS, d.DECISION_BUTTONS):
        for titles in group.values():
            assert len(titles) <= 3 and all(len(t) <= 20 for t in titles)
    for title in d.OFFER_BUTTONS["en"][:1] + d.OFFER_BUTTONS["roman_ur"][:1]:
        assert d.classify(title)[0] != Answer.NO


def test_the_offer_buttons_ride_on_the_offer_and_the_confirm_question():
    assert d.buttons_for(d.text("offer", "en")) == d.OFFER_BUTTONS["en"]
    assert d.buttons_for(d.text("offer", "roman_ur")) == d.OFFER_BUTTONS["roman_ur"]
    assert d.buttons_for(d.text("confirm_go", "en")) == d.OFFER_BUTTONS["en"]
    assert d.buttons_for(d.text("re_offer", "en")) == d.OFFER_BUTTONS["en"]
    assert d.buttons_for("Noted. Which shop is it?") is None


def facts(**changes):
    base = {
        "message_id": "m2",
        "can_approve": True,
        "business": "Bright Studio",
        "problem_count": 3,
        "group_count": 2,
        "problem_refs": ["a1", "b2", "c3"],
        "chosen_refs": [],
        "changed": False,
        "brief": {},
        "open_quote": None,
    }
    return {**base, **changes}


def go(state, said, **changes):
    return d.decide(state, said, "en", facts(**changes))


# --- S4: the summary was shown ------------------------------------------------------------


@pytest.mark.parametrize("said", ["ok", "looks right", "theek hai", "that's all correct", "yes"])
def test_after_the_summary_a_confirmation_brings_the_offer(said):
    decision = go(S.S4_SORTED_SUMMARY, said)
    assert decision.next_state == S.S5_READINESS and decision.reply == d.text("offer", "en")
    assert "You can say no" in decision.reply and "an offer, not a charge" in decision.reply
    assert decision.why == "R-OFFER-01"


def test_no_offer_while_a_correction_or_a_question_is_pending():
    assert go(S.S4_SORTED_SUMMARY, "ok", changed=True) is None
    assert go(S.S4_SORTED_SUMMARY, "ok", problem_count=0) is None
    assert go(S.S4_SORTED_SUMMARY, "wait, the second one is wrong") is None
    assert go(S.S4_SORTED_SUMMARY, "what does it cost?") is None


# --- S5: the offer was made ---------------------------------------------------------------


def test_a_yes_to_the_offer_with_one_group_goes_straight_to_preparing():
    decision = go(S.S5_READINESS, "yes please", group_count=1)
    assert decision.next_state == S.S6_PREPARING and decision.effects == ["request_solution"]
    assert decision.brief["offer"] == {
        "yes_message_id": "m2",
        "confirm_message_id": "m2",
        "problem_refs": ["a1", "b2", "c3"],
    }
    assert decision.reply == d.text("preparing", "en")
    assert "promise" not in decision.reply and not any(c.isdigit() for c in decision.reply)


def test_with_two_groups_pi_asks_all_or_some_once():
    decision = go(S.S5_READINESS, "yes")
    assert (
        decision.next_state is None
        and decision.reply == "Should it cover all of these, or only some?"
    )
    assert decision.brief == {"scope_asked": True, "offer_yes_id": "m2"}
    asked = {"scope_asked": True, "offer_yes_id": "m2"}
    everything = go(S.S5_READINESS, "all of them", brief=asked, message_id="m3")
    assert everything.next_state == S.S6_PREPARING
    assert everything.brief["offer"]["yes_message_id"] == "m2"
    assert everything.brief["offer"]["confirm_message_id"] == "m3"
    assert everything.brief["offer"]["problem_refs"] == ["a1", "b2", "c3"]
    assert everything.brief["scope_done"] is True
    some = go(S.S5_READINESS, "only the stock ones", brief=asked, chosen_refs=["a1"])
    assert some.next_state == S.S6_PREPARING and some.brief["offer"]["problem_refs"] == ["a1"]
    assert go(S.S5_READINESS, "only the stock ones", brief=asked) is None  # the model picks refs


def test_no_to_the_offer_is_accepted_without_persuasion():
    decision = go(S.S5_READINESS, "no thanks")
    assert decision.next_state == S.S5B_DECLINED and decision.brief == {"offer_declined": True}
    assert (
        decision.reply
        == "No problem. Everything you've told me is kept here if you change your mind."
    )
    assert decision.effects == []


def test_later_pauses_and_remembers_where():
    decision = go(S.S5_READINESS, "later")
    assert decision.next_state == S.X_PAUSED
    assert decision.brief == {"paused_from": "S5_READINESS"}
    assert decision.reply.startswith("No rush.")


@pytest.mark.parametrize("said", ["ok", "hmm", "maybe", "let me think"])
def test_a_hedge_gets_one_confirming_question_and_not_a_second(said):
    decision = go(S.S5_READINESS, said)
    assert decision.reply == "Shall I go ahead and ask Workzap to prepare them?"
    assert decision.next_state is None and decision.brief == {"yes_asked": True}
    assert go(S.S5_READINESS, said, brief={"yes_asked": True}) is None


def test_a_cost_question_goes_to_the_model_not_the_gate():
    assert go(S.S5_READINESS, "how much would it cost?") is None
    assert go(S.S5_READINESS, "yes but how much") is None


def test_a_team_member_cannot_say_yes_for_the_business():
    decision = go(S.S5_READINESS, "yes", can_approve=False)
    assert decision.next_state is None and decision.effects == []
    assert "The owner of Bright Studio needs to say yes" in decision.reply
    assert "workzap.ai/pi/talk-to-pi" in decision.reply
    assert decision.brief == {"offer_wanted_by_member": True, "non_decider_asked": True}
    # R-OFFER-06: asked once whether the decision-maker should receive the document.
    assert decision.reply.endswith("how would you like to involve them?")


def test_adding_a_problem_while_the_offer_waits_changes_nothing_here():
    assert go(S.S5_READINESS, "yes", changed=True) is None


# --- S5b: declined -------------------------------------------------------------------------


def test_after_a_no_pi_stays_quiet_unless_they_raise_it():
    assert go(S.S5B_DECLINED, "the cashier is late again") is None
    assert go(S.S5B_DECLINED, "ok") is None
    again = go(S.S5B_DECLINED, "actually please send me the document and quote")
    assert again.next_state == S.S5_READINESS and again.brief == {"yes_asked": True}
    assert again.reply.startswith("Sure. Shall I ask Workzap")


# --- S8: the person reads the quote --------------------------------------------------------

QUOTE = {"id": "Q-12", "total": "Rs 450,000"}


def review(said, **changes):
    return go(S.S8_REVIEW, said, open_quote=QUOTE, **changes)


def test_approval_needs_two_confirmations():
    first = review("Approve")
    assert first.next_state is None
    assert first.reply == "Just to confirm: you approve quote Q-12 for Rs 450,000. Is that right?"
    assert first.brief["approval_pending"] == {"quote": "Q-12", "message_id": "m2"}
    pending = {"approval_pending": {"quote": "Q-12", "message_id": "m2"}}
    second = review("yes", brief=pending, message_id="m3")
    assert second.next_state == S.S10_AWAITING_PAYMENT and second.effects == ["record_approval"]
    assert second.brief["approval"] == {"quote": "Q-12", "confirm_message_ids": ["m2", "m3"]}
    assert second.brief["approval_pending"] is None
    assert "bank transfer" in second.reply and "don't send card details" in second.reply


def test_anything_but_a_yes_drops_a_pending_approval():
    pending = {"approval_pending": {"quote": "Q-12", "message_id": "m2"}}
    for said in ("no", "wait", "hmm", "what about the date?"):
        dropped = review(said, brief=pending)
        assert dropped.next_state is None and dropped.brief == {"approval_pending": None}
        assert dropped.reply.startswith("Okay, I haven't approved anything.")


def test_only_someone_who_can_approve_approves():
    decision = review("Approve", can_approve=False)
    assert decision.next_state is None and "approval_pending" not in decision.brief
    assert "needs to say yes" in decision.reply
    pending = {"approval_pending": {"quote": "Q-12", "message_id": "m2"}}
    assert review("yes", brief=pending, can_approve=False).next_state is None


def test_ask_for_changes_and_say_no():
    changes = review("Ask for changes")
    assert (
        changes.next_state == S.S8B_CHANGES_REQUESTED
        and changes.reply == "What would you like changed?"
    )
    declined = review("Say no")
    assert declined.next_state == S.S9B_DECLINED_QUOTE and "Nothing is charged" in declined.reply
    assert declined.effects == []


def test_a_question_about_the_quote_is_for_the_model():
    assert review("what does the support period cover?") is None
    assert go(S.S8_REVIEW, "Approve") is None  # no quote on the table: nothing to approve


def test_cancelling_before_payment_is_accepted_and_told_to_workzap():
    decision = go(S.S10_AWAITING_PAYMENT, "I want to cancel")
    assert decision.next_state == S.S9B_DECLINED_QUOTE and decision.effects == [
        "cancel_before_payment"
    ]
    assert "Nothing is charged" in decision.reply
    assert go(S.S10_AWAITING_PAYMENT, "how do I pay?") is None
    # after payment it is a human matter: pi passes it on and decides nothing (R-DEC-05)
    later = go(S.S11_PAYMENT_CONFIRMED, "cancel")
    assert later.effects == ["escalate"] and later.next_state is None
    assert go(S.S9_APPROVED, "I want to cancel").next_state == S.S9B_DECLINED_QUOTE


def test_replies_come_in_roman_urdu_too():
    offer = d.decide(S.S4_SORTED_SUMMARY, "theek hai", "roman_ur", facts())
    assert offer.reply == d.TEXT["offer"]["roman_ur"]
    no = d.decide(S.S5_READINESS, "nahi shukriya", "roman_ur", facts())
    assert no.reply == d.TEXT["declined"]["roman_ur"]
    unknown = d.decide(S.S5_READINESS, "no", "fr", facts())
    assert unknown.reply == d.TEXT["declined"]["en"]  # an unlisted language falls back to English


def test_the_other_states_make_no_decision():
    for state in (S.S1_LISTENING, S.S3_NOTED, S.S6_PREPARING, S.S7_DELIVERED, S.S13_IN_BUILD):
        assert go(state, "yes") is None


# --- S10: waiting for payment (R-PAY-05, R-PAY-06) ------------------------------------------


@pytest.mark.parametrize(
    "said",
    [
        "I have paid",
        "done",
        "paid already",
        "transfer kar diya",
        "payment ho gayi",
        "I sent the money",
        "bhej diya",
    ],
)
def test_saying_they_paid_is_only_a_claim(said):
    decision = go(S.S10_AWAITING_PAYMENT, said)
    assert decision.reply == "Thanks. The Workzap team will confirm here when the transfer arrives."
    assert decision.effects == ["payment_claimed"] and decision.next_state is None
    assert "received" not in decision.reply.lower()


def test_a_screenshot_is_a_claim_too():
    for kind in ("image", "document"):
        decision = go(S.S10_AWAITING_PAYMENT, "", message_kind=kind)
        assert decision.effects == ["payment_claimed"]
    assert go(S.S10_AWAITING_PAYMENT, "see this", message_kind="text") is None


@pytest.mark.parametrize(
    "said", ["how do I pay?", "what is the account number?", "kab tak karna hai?"]
)
def test_a_question_about_paying_is_not_a_claim(said):
    assert go(S.S10_AWAITING_PAYMENT, said) is None


def test_cancelling_beats_a_claim_and_the_notice_waits_in_s11():
    assert go(S.S10_AWAITING_PAYMENT, "cancel, I have not paid").effects == [
        "cancel_before_payment"
    ]
    notice = go(S.S11_PAYMENT_CONFIRMED, "hello", brief={"payment_notice_due": True})
    assert notice.reply.startswith("Workzap has confirmed your transfer.")
    assert notice.brief == {"payment_notice_due": None}
    assert go(S.S11_PAYMENT_CONFIRMED, "hello", brief={}) is None
    roman = d.decide(
        S.S11_PAYMENT_CONFIRMED, "hi", "roman_ur", facts(brief={"payment_notice_due": True})
    )
    assert roman.reply.startswith("Workzap ne aap ka transfer confirm kar diya hai.")


def test_a_quote_past_its_date_is_not_approved_as_it_stands():
    from datetime import date, timedelta

    quote = {
        "id": "Q-0001",
        "total": "PKR 100,000",
        "valid_until": (date.today() - timedelta(days=1)).isoformat(),
    }
    decision = d.decide(S.S8_REVIEW, "Approve", "en", facts(open_quote=quote))
    assert decision is not None and decision.effects == ["escalate"]
    assert "past its valid-until date" in decision.reply
    fresh = {**quote, "valid_until": (date.today() + timedelta(days=5)).isoformat()}
    ok = d.decide(S.S8_REVIEW, "Approve", "en", facts(open_quote=fresh))
    assert ok is not None and "Just to confirm" in ok.reply
