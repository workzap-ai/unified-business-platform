"""A registry person's greeting stays in the chat; a real request, or any media, is a card."""

import pytest

from app.modules.pi_saas.nori_board import chat_only


@pytest.mark.parametrize(
    "text",
    [
        "Hello",
        "hi!",
        "Assalamualaikum",
        "Salam bhai",
        "ok",
        "Thanks a lot",
        "Shukriya",
        "جی",
        "السلام علیکم",
        "👍",
        "Good morning team",
        "Hello Hello",
    ],
)
def test_greetings_and_thanks_are_only_conversation(text):
    assert chat_only.is_chat_only(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Please I want to erp system integration",
        "Hello, the stock export is not working",
        "Mujhe nori mai calling features chahiye",
        "ok but when will the report be ready",
        "hello hello hello hello hello hello",
        "calling",
    ],
)
def test_anything_else_is_a_requirement(text):
    assert chat_only.is_chat_only(text) is False


def test_every_acknowledgement_says_it_is_an_ai_in_the_persons_language():
    for table in (chat_only.FILED_ACK, chat_only.CHAT_ACK):
        assert set(table) == {"en", "roman_ur", "ur"}
        assert "AI" in table["en"] and "AI" in table["roman_ur"] and "AI" in table["ur"]
    assert chat_only.ack_text(False, None, "The stock export is not working").startswith("I'm pi")
    assert chat_only.ack_text(False, "roman_ur", "x").startswith("Main pi hoon")
    assert chat_only.ack_text(True, "ur", "x").startswith("میں pi ہوں")
    # one question at most, and it is the last sentence (R-Q-01)
    assert chat_only.CHAT_ACK["en"].count("?") == 1 and chat_only.CHAT_ACK["en"].endswith("?")
