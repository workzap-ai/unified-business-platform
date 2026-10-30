"""Live chat 2026-10-30 11:16 (Artwing Studios, new number): the owner gave only a name and asked
"do you know anything about it?"; pi sent the page request and never answered, never asked what the
business does. Later it sent a fixed "no more ideas" line ending in "you can say no" (spec 18.3)."""

from app.modules.pi import reply_gates, warmup
from app.modules.pi.service_conversation import (
    NO_IDEA_AGAIN,
    NO_IDEA_LINES,
    NO_MORE_IDEAS,
)


def ctx(said: str, step: str = warmup.IDENTITY_ASKED, **state: object) -> dict[str, object]:
    return {
        "warmup": {"enabled": True},
        "brief": {"warmup": {"step": step, **state}},
        "latest_customer_message": said,
        "reply_language": "roman_ur",
    }


def test_a_direct_question_about_what_pi_knows_is_answered_first() -> None:
    plan = warmup.plan(ctx("Its artwing studios. Aap ko iskay baray mai kuch pata hai?"))
    assert plan is not None
    assert plan.reply == warmup.KNOWS_NOT["roman_ur"]
    assert "link" not in plan.reply and plan.reply.count("?") == 1 and plan.reply.endswith("?")
    assert plan.state["step"] == warmup.IDENTITY_ASKED  # the page is not asked for yet


def test_the_english_question_gets_the_english_answer() -> None:
    plan = warmup.plan({**ctx("Artwing Studios. Do you know us?"), "reply_language": "en"})
    assert plan is not None and plan.reply == warmup.KNOWS_NOT["en"]


def test_a_name_alone_is_followed_by_what_does_it_do() -> None:
    plan = warmup.plan(ctx("Its artwing studios"))
    assert plan is not None and plan.reply == warmup.ASK_WHAT["roman_ur"]
    assert plan.state["step"] == warmup.IDENTITY_ASKED and plan.state["asked_what"] is True


def test_the_what_does_it_do_question_is_asked_once_then_the_page() -> None:
    plan = warmup.plan(ctx("branding", asked_what=True))
    assert plan is not None and plan.reply == warmup.PAGE_ASK["roman_ur"]
    assert plan.state["step"] == warmup.PAGE_ASKED


def test_a_full_answer_goes_straight_to_the_page_request() -> None:
    said = "Artwing Studios, hum brands ke liye websites aur AI systems banate hain"
    plan = warmup.plan(ctx(said))
    assert plan is not None and plan.reply == warmup.PAGE_ASK["roman_ur"]


def test_a_link_in_the_answer_is_looked_at_not_questioned() -> None:
    plan = warmup.plan(ctx("https://artwingstudios.co/"))
    assert plan is not None and plan.ask_page == "https://artwingstudios.co/"


def test_the_fixed_no_more_ideas_lines_do_not_pressure_and_end_with_one_question() -> None:
    for table in (NO_MORE_IDEAS, NO_IDEA_AGAIN):
        for language, line in table.items():
            assert reply_gates.without_say_no(line) == line, (language, line)
            assert "mana bhi kar" not in line and "say no" not in line
    for language in ("en", "roman_ur"):
        assert NO_MORE_IDEAS[language].rstrip().endswith("?")
        assert NO_IDEA_AGAIN[language].rstrip().endswith("?")
        assert NO_MORE_IDEAS[language].count("?") == 1
    assert NO_IDEA_LINES["en"]  # unchanged


def test_a_model_written_roman_urdu_say_no_is_removed() -> None:
    reply = "Document mein poora hal likha hota hai, aur aap mana bhi kar sakte hain."
    cleaned = reply_gates.without_say_no(reply)
    assert "mana" not in cleaned and cleaned == "Document mein poora hal likha hota hai."
    english = "The document goes further, and you can say no to it."
    assert reply_gates.without_say_no(english) == "The document goes further."
