# ruff: noqa: E501
"""Expert workspaces: no unasked ideas, a lead line for asked ones, no 'Thanks. I've noted it:' example."""

from app.modules.pi import expert_advisor
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
    assert turn.reply.startswith("Here are some ideas you can try now:")


def test_an_existing_lead_is_not_doubled() -> None:
    turn = ServiceTurn(reply=f"Ji, ye do ideas abhi aazma sakte hain:\n{IDEAS}")
    shape_expert_ideas(turn, ctx("kuch karo"))
    assert turn.reply.count("ye do ideas") == 1


def test_one_bullet_or_no_bullets_are_left_alone() -> None:
    turn = ServiceTurn(reply=f"Samajh gaya.\n{BULLET} ek baat\n\nKya wajah hai?")
    shape_expert_ideas(turn, ctx("masla hai"))
    assert BULLET in turn.reply


def test_the_noted_it_example_is_replaced_in_the_expert_prompt_only() -> None:
    assert expert_advisor.OLD_CONFIRM in sc.BRAIN_PROBLEMS
    expert = sc.system_for({"pi_mode": "brain", "expert_on": True})
    plain = sc.system_for({"pi_mode": "brain"})
    assert expert_advisor.NEW_CONFIRM in expert and expert_advisor.OLD_CONFIRM not in expert
    assert expert_advisor.OLD_CONFIRM in plain
