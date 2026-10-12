"""Reply checks from a real test chat: a Roman Urdu line in an English chat, "sent to
the team" plus "shall I send it?", an exact repeat, and generic closing lines."""

from app.modules.pi.service_conversation import contradicts_itself, mixed_line, without_filler

REPLY = (
    "• Modern advanced website for online sales\n"
    "• Management of high stocks and volumes\n"
    "Ye brief team ko bhej diya hai. Shall I send this to the team?"
)


def test_a_roman_urdu_line_in_an_english_chat_is_caught():
    assert mixed_line(REPLY, "en") == "roman_ur"
    assert mixed_line("Thanks, noted. How many products will the shop have?", "en") is None


def test_sent_and_shall_i_send_together_is_caught():
    assert contradicts_itself(REPLY, {})
    assert contradicts_itself("Shall I send this to the team?", {}) is None


def test_repeating_the_last_message_is_caught():
    said = "• Online store for 200 products\n• Stock management\nHow many staff will use it?"
    context = {"history": [{"role": "customer", "text": "hi"}, {"role": "ai", "text": said}]}
    assert "repeats" in str(contradicts_itself(said.replace("\n", "\n\n"), context))


def test_generic_closings_are_dropped_but_real_questions_stay():
    assert (
        without_filler(
            "Workzap offers an AI assistant. If you have specific needs, feel free to share!"
        )
        == "Workzap offers an AI assistant."
    )
    assert without_filler("Noted. How many products?") == "Noted. How many products?"
