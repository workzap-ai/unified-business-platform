# ruff: noqa: E501
"""Live chat 2026-10-28: "Ji, ye do ideas ..." over ONE idea, and the reply ended on the idea."""

from app.modules.pi.service_conversation import (
    ASK_AFTER_IDEAS,
    IDEAS_LEAD,
    ONE_IDEA_LEAD,
    ServiceTurn,
    settle_ideas,
)

B = "•"


def run(reply, language="roman_ur"):
    turn = ServiceTurn(reply=reply)
    settle_ideas(turn, {"reply_language": language})
    return turn.reply


def test_one_idea_left_says_one_idea_and_gets_its_question() -> None:
    lead = IDEAS_LEAD["roman_ur"]
    out = run(f"{lead}\n\n{B} Ek salesman chunein.")
    assert out.startswith(ONE_IDEA_LEAD["roman_ur"])
    assert out.endswith(ASK_AFTER_IDEAS["roman_ur"]["one"]) and out.count("?") == 1


def test_two_ideas_keep_their_lead_and_get_the_question() -> None:
    lead = IDEAS_LEAD["en"]
    out = run(f"{lead}\n\n{B} First thing.\n{B} Second thing.", "en")
    assert out.startswith(lead) and out.endswith(ASK_AFTER_IDEAS["en"]["many"])


def test_an_offer_or_a_question_after_the_ideas_is_left_alone() -> None:
    lead = IDEAS_LEAD["roman_ur"]
    offered = f"{lead}\n\n{B} Ek.\n{B} Do.\n\nKya main ek solution document aur quote banwa doon? Aap mana bhi kar sakte hain."
    assert run(offered) == offered
    asked = f"{lead}\n\n{B} Ek.\n{B} Do.\n\nKaun si dukaan zyada bechti hai?"
    assert run(asked) == asked


def test_a_lead_with_no_idea_left_is_dropped() -> None:
    out = run(f"{IDEAS_LEAD['roman_ur']}\n\nKaun si dukaan zyada bechti hai?")
    assert IDEAS_LEAD["roman_ur"] not in out and out.endswith("bechti hai?")


def test_other_languages_and_plain_replies_are_untouched() -> None:
    assert run(f"{B} one idea", "fr") == f"{B} one idea"
    assert run("Kaun si dukaan?") == "Kaun si dukaan?"
