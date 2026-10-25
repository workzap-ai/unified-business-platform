# ruff: noqa: E501
"""Ideas read as plain sentences (no dots), other scripts keep their own language, and short
Roman Urdu asks and dislikes are understood."""

import pytest

from app.modules.pi import solution_ask, solution_score
from app.modules.pi.language import in_script, other_script
from app.modules.pi.solution_rules import count_ideas, idea_lines

CHINESE = "Chinese (Simplified)"


def test_idea_lines_are_prose_not_bullets() -> None:
    text = idea_lines(
        [
            "Count the till together at shift change, so a gap is placed.",
            "Log each order in one book, so none is missed.",
        ]
    )
    assert text.splitlines()[0].startswith("First, count the till")
    assert text.splitlines()[1].startswith("Second, log each order")
    assert "•" not in text
    assert count_ideas(text) == 2


def test_one_idea_is_one_sentence() -> None:
    assert (
        idea_lines(["Write the order down, so it is not missed"])
        == "Write the order down, so it is not missed."
    )


@pytest.mark.parametrize(
    "text",
    [
        "你好，我经营一家小型制造工厂。我们每天生产几百件产品。",
        "我们有三个仓库和五十名员工。我还希望系统能够预测需求",
    ],
)
def test_chinese_is_its_own_language(text: str) -> None:
    assert other_script(text) == CHINESE
    assert in_script(text, CHINESE)


def test_latin_and_arabic_are_not_other_scripts() -> None:
    assert other_script("Hello, I own a shop") is None
    assert other_script("مرحبا، لدي شركة توصيل طلبات") is None
    assert not in_script("I have noted the three points", CHINESE)


@pytest.mark.parametrize(
    "text",
    [
        "Idea psnd NH aiya mujhe",
        "idea pasand nahi aya",
        "ye idea acha nahi hai",
        "I don't like these ideas",
    ],
)
def test_disliked_ideas_ask_for_a_different_kind(text: str) -> None:
    reaction = solution_score.classify(text)
    assert reaction is not None and reaction.signal == "idea_generic"


@pytest.mark.parametrize(
    "text", ["Aur idea dw", "aur idea chahiye", "or idea do", "idea dena", "mazeed suggestions"]
)
def test_more_ideas_in_roman_urdu_is_an_ask(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def _turn(reply: str):  # noqa: ANN202
    from types import SimpleNamespace

    return SimpleNamespace(reply=reply, _summary=False, _free=False)


def test_model_bullets_become_prose_for_handed_ideas() -> None:
    from app.modules.pi.service_conversation import asked_without_ideas, brain_prose_ideas

    turn = _turn("Theek hai.\n• Sheets alag rakhein.\n• Roz update karein.\n\nKya main banwa doon?")
    brain_prose_ideas(turn, {"solution_ideas": ["x"], "reply_language": "roman_ur"})
    assert turn.reply.splitlines()[1] == "Pehle, sheets alag rakhein."
    assert turn.reply.splitlines()[2] == "Doosra, roz update karein."
    assert asked_without_ideas(
        {
            "ideas_given": 2,
            "latest_customer_message": "Idea psnd NH aiya",
            "flow": {"state": "S3_NOTED"},
        }
    )


def test_summary_lists_and_other_languages_keep_their_dots() -> None:
    from app.modules.pi.service_conversation import brain_prose_ideas

    summary = _turn("Noted:\n• one\n• two")
    summary._summary = True
    brain_prose_ideas(summary, {"solution_ideas": ["x"], "reply_language": "en"})
    assert "•" in summary.reply
    arabic = _turn("نعم\n• أ\n• ب")
    brain_prose_ideas(arabic, {"solution_ideas": ["x"], "reply_language": "ar"})
    assert "•" in arabic.reply


@pytest.mark.parametrize("text", ["给我一些建议", "有什么办法解决这个问题", "我们该如何解决"])
def test_chinese_ask_for_ideas(text: str) -> None:
    assert solution_ask.asked_for_ideas(text)


def test_a_message_that_tells_the_problem_and_asks_for_a_fix_is_still_extracted() -> None:
    from app.modules.pi import problem_extract

    said = "Orders get missed, staff make mistakes, I cannot track sales. Can you help me fix this?"
    base = {"pi_mode": "brain", "flow": {"state": "S1_LISTENING"}, "latest_customer_message": said}
    assert problem_extract.wants_extraction({**base, "solution_asked_no_ideas": True}, "", [])
    noted = {**base, "solution_asked": True, "noted_problems": [{"ref": "p1"}]}
    assert not problem_extract.wants_extraction(noted, "", [])


def test_covers_is_a_noun_phrase_even_for_are_set_in_the_document() -> None:
    covered = solution_ask.covers(
        {"free_stops": "Recall intervals and message flow are set in the solution document."}
    )
    assert covered == "Recall intervals and message flow"


def test_free_ideas_never_state_a_time() -> None:
    from app.modules.pi import solution_free

    ideas = [
        "Check this week's payouts against the order slips, so you can see which brand is mixed up.",
        "Keep one list per brand with the last promise, so chasing stays tidy and nothing is forgotten.",
    ]
    kept = solution_free.vetted(ideas, "payouts are mixed up", [])
    assert kept == [
        "Keep one list per brand with the last promise, so chasing stays tidy and nothing is forgotten."
    ]


def test_brain_never_leaves_an_empty_reply() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_never_empty

    turn = SimpleNamespace(
        reply="", request_human=False, _decision=None, _summary=False, awaiting_customer=False
    )
    context = {
        "reply_language": "en",
        "latest_customer_message": "Ye kaise karna hai?",
        "flow": {"state": "S3_NOTED"},
        "history": [{"role": "ai", "text": "Hi"}],
    }
    brain_never_empty(turn, context)
    assert "solution document once the problems are noted" in turn.reply and turn.reply.strip()


def test_roman_urdu_idea_lines_lose_their_english_scaffolding() -> None:
    from types import SimpleNamespace

    from app.modules.pi.service_conversation import brain_prose_ideas

    turn = SimpleNamespace(
        reply="Sure.\nFirst, register dekho, so nuksan saaf ho.\nSecond, safha alag likho, so hisaab milay.",
        _summary=False,
        _free=True,
    )
    brain_prose_ideas(turn, {"solution_ideas": ["x"], "reply_language": "roman_ur"})
    assert "Pehle, register dekho, taake nuksan saaf ho." in turn.reply
    assert "Doosra, safha alag likho, taake hisaab milay." in turn.reply


def _promise_turn(reply: str):  # noqa: ANN202
    from types import SimpleNamespace

    return SimpleNamespace(
        reply=reply,
        request_human=False,
        _decision=None,
        _summary=False,
        awaiting_customer=False,
        problem_ops=[],
    )


def test_the_document_is_never_promised_before_the_offer_was_accepted() -> None:
    from app.modules.pi.service_conversation import brain_no_early_promise

    noted = {
        "reply_language": "roman_ur",
        "flow": {"state": "S2_CLARIFYING"},
        "noted_problems": [{"ref": "p1"}],
    }
    turn = _promise_turn("Theek hai. Workzap solution document aur quote ab tayar kiya jayega.")
    brain_no_early_promise(turn, noted)
    assert "tayar kiya jayega" not in turn.reply and turn._decision is not None
    assert turn._decision.to.value == "S5_READINESS" if hasattr(turn._decision, "to") else True

    nothing = _promise_turn("The document and quote will be prepared and sent here.")
    brain_no_early_promise(nothing, {"reply_language": "en", "flow": {"state": "S1_LISTENING"}})
    assert "once the problems are noted" in nothing.reply and nothing._decision is None


def test_the_conditional_line_and_later_states_are_left_alone() -> None:
    from app.modules.pi.service_conversation import brain_no_early_promise

    fine = _promise_turn("Workzap solution document tab banega jab problems note ho jayen.")
    brain_no_early_promise(fine, {"flow": {"state": "S2_CLARIFYING"}})
    assert fine.reply.startswith("Workzap solution document tab banega")
    later = _promise_turn("Maine Workzap se document aur quote tayyar karne ko keh diya hai.")
    brain_no_early_promise(later, {"flow": {"state": "S5_READINESS"}})
    assert later.reply.startswith("Maine Workzap")
