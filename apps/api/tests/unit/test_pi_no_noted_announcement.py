# ruff: noqa: E501
"""Platform spec v1.4, 17.6: pi never announces that it noted something."""

from app.modules.pi import reply_voice


def test_the_english_frame_is_taken_out() -> None:
    reply = "Thanks. I've noted it: sales staff absent.\n\nWhich city is it worst in?"
    assert reply_voice.drop_noted(reply) == "Which city is it worst in?"


def test_roman_urdu_frames_are_taken_out() -> None:
    reply = "Note kar liya hai: staff gaib rehta hai. Sab se zyada kis shehar mein hota hai?"
    assert reply_voice.drop_noted(reply) == "Sab se zyada kis shehar mein hota hai?"
    reply = "Shukriya. Maine note kar liya: stock ka hisaab nahi.\n\nHisaab kaun rakhta hai?"
    assert reply_voice.drop_noted(reply) == "Hisaab kaun rakhta hai?"


def test_the_frame_after_the_ideas_is_taken_out_too() -> None:
    reply = "• Count the stock once a week.\n• Write each sale down.\n\nThanks. I've noted it: no stock records. Who keeps the book?"
    out = reply_voice.drop_noted(reply)
    assert "noted" not in out.lower() and out.endswith("Who keeps the book?")
    assert out.count("•") == 2


def test_a_reply_that_is_only_the_announcement_is_left_alone() -> None:
    assert reply_voice.drop_noted("Noted: stock.") == "Noted: stock."


def test_a_reply_without_the_frame_is_unchanged() -> None:
    reply = "Which shops does the salesman visit in a day?"
    assert reply_voice.drop_noted(reply) == reply


def test_maine_teeno_masle_note_kar_liye_is_taken_out() -> None:
    reply = "Maine teeno masle note kar liye hain.\n\nSales staff ka gaib hona kis shehar mein zyada hai?"
    assert reply_voice.drop_noted(reply) == "Sales staff ka gaib hona kis shehar mein zyada hai?"


def test_an_apology_with_a_verdict_is_a_hollow_opener() -> None:
    from app.modules.pi import constitution

    for opener in (
        "Maaf kijiye, ye bohat mushkil hai.",
        "I'm sorry, that sounds really hard.",
        "Sorry, this is stressful.",
    ):
        assert constitution.HOLLOW_OPENER.match(opener), opener
    # a real apology that names something, or a question, is not hollow
    assert not constitution.HOLLOW_OPENER.match("Maaf kijiye, mujhe ye samajh nahi aaya.")
    assert not constitution.HOLLOW_OPENER.match("Sorry for the late reply, I was checking.")


def test_ordinary_speech_with_the_word_noted_is_untouched() -> None:
    reply = "Once I've noted what's going wrong, we can look at the app. For now, what would it fix first?"
    assert reply_voice.drop_noted(reply) == reply
    reply = "I have noted the dates you gave, so which shop is slowest?"
    assert reply_voice.drop_noted(reply) == reply
