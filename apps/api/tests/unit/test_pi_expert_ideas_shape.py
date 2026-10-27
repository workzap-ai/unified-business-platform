# ruff: noqa: E501
"""Expert workspaces: no unasked ideas, a lead line for asked ones, no 'Thanks. I've noted it:' example."""

from app.modules.pi import service_conversation as sc
from app.modules.pi.service_conversation import ServiceTurn, shape_expert_ideas

BULLET = "•"
IDEAS = f"{BULLET} Pehli baat yahan likhi hai.\n{BULLET} Doosri baat yahan likhi hai."
OFFER = (
    "Shall I get one solution document and a quote made for all of these together? You can say no."
)


def ctx(said: str, **more: object) -> dict:
    return {
        "expert_on": True,
        "reply_language": "roman_ur",
        "latest_customer_message": said,
        **more,
    }


def test_ideas_nobody_asked_for_are_dropped_and_the_question_is_kept() -> None:
    turn = ServiceTurn(
        reply=f"Haan, ho sakta hai. Do cheezein:\n\n{IDEAS}\n\n{OFFER}\n\nHarvest kab ek saath aata hai?"
    )
    shape_expert_ideas(turn, ctx("Ajman mein lettuce farm hai, harvest ek saath aata hai."))
    assert BULLET not in turn.reply and "solution document" not in turn.reply
    assert turn.reply.rstrip().endswith("?") and "Harvest kab" in turn.reply


def test_a_dropped_list_without_a_question_gets_the_listening_question() -> None:
    turn = ServiceTurn(reply=f"Theek hai:\n{IDEAS}")
    shape_expert_ideas(turn, ctx("Mera masla naya hai."))
    assert BULLET not in turn.reply and turn.reply.rstrip().endswith("?")


def test_asked_ideas_keep_the_list_and_get_the_lead_if_it_is_missing() -> None:
    turn = ServiceTurn(reply=f"{IDEAS}\n\n{OFFER}")
    shape_expert_ideas(turn, ctx("kuch karo"))
    assert turn.reply.startswith("Ji, ye do ideas abhi aazma sakte hain:")
    assert turn.reply.count(BULLET) == 2 and "solution document" in turn.reply


def test_an_english_owner_gets_the_english_lead() -> None:
    turn = ServiceTurn(reply=IDEAS)
    shape_expert_ideas(turn, {**ctx("what can you do?"), "reply_language": "en"})
    assert turn.reply.startswith("Here are some ideas for you:")


def test_an_existing_lead_is_not_doubled() -> None:
    turn = ServiceTurn(reply=f"Ji, ye do ideas abhi aazma sakte hain:\n{IDEAS}")
    shape_expert_ideas(turn, ctx("kuch karo"))
    assert turn.reply.count("ye do ideas") == 1


def test_one_bullet_or_no_bullets_are_left_alone() -> None:
    turn = ServiceTurn(reply=f"Samajh gaya.\n{BULLET} ek baat\n\nKya wajah hai?")
    shape_expert_ideas(turn, ctx("masla hai"))
    assert BULLET in turn.reply


def test_no_brain_prompt_teaches_the_noted_it_opener() -> None:
    # spec v1.4, 17.6: the base prompt's example of confirming a problem is not "Thanks. I've noted it:"
    for context in ({"pi_mode": "brain"}, {"pi_mode": "brain", "expert_on": True}):
        prompt = sc.system_for(context)
        assert "I've noted it" not in prompt
        assert "naming it in a few of their words" in prompt
