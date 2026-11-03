"""A person taking a chat over puts it in X_HUMAN; giving it back restores the state (R-DISC-04)."""

from types import SimpleNamespace as Chat

from app.modules.pi import flow


def chat(state, brief=None):
    return Chat(flow_state=state, service_brief=brief or {}, flow_state_since=None)


def test_takeover_remembers_the_state_and_return_restores_it():
    c = chat("S3_NOTED")
    flow.hand_to_human(c)
    assert c.flow_state == "X_HUMAN" and c.service_brief["resume_state"] == "S3_NOTED"
    flow.hand_back(c)
    assert c.flow_state == "S3_NOTED" and "resume_state" not in c.service_brief


def test_a_chat_without_a_state_is_left_alone():
    c = chat(None)
    flow.hand_to_human(c)
    flow.hand_back(c)
    assert c.flow_state is None and c.service_brief == {}


def test_a_second_takeover_does_not_overwrite_the_remembered_state():
    c = chat("S7_DELIVERED")
    flow.hand_to_human(c)
    flow.hand_to_human(c)
    flow.hand_back(c)
    assert c.flow_state == "S7_DELIVERED"


def test_returning_without_a_remembered_state_goes_back_to_listening():
    c = chat("X_HUMAN")
    flow.hand_back(c)
    assert c.flow_state == "S1_LISTENING"


def test_handing_back_marks_that_pi_must_say_who_it_is_again():
    c = chat("S3_NOTED")
    flow.hand_to_human(c)
    flow.hand_back(c)
    assert c.service_brief["handback_notice"] is True


def test_the_first_reply_after_a_hand_back_is_the_fixed_line():
    from app.modules.pi.service_conversation import brain_safety

    context = {
        "latest_customer_message": "ok go on",
        "reply_language": "en",
        "handback_notice": True,
    }
    reply = brain_safety(context)
    assert reply is not None and "pi again" in reply.reply and reply.reply.count("?") == 1
    assert brain_safety({"latest_customer_message": "ok go on", "reply_language": "en"}) is None
