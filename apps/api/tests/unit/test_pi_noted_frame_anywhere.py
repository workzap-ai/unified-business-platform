"""A real Roman Urdu reply kept the English 'Thanks. I've noted it:' after the ideas (the frame was
only translated at the very start of a reply), and one Roman Urdu variant was gendered."""

from app.modules.pi import reply_voice


def test_the_english_noted_frame_is_translated_even_after_the_ideas():
    reply = (
        "Haan, ho sakta hai.\nPehle, ek banda roz rush line check kare.\n"
        "Doosra, wait time likhte jayein.\nThanks. I've noted it: shaam ka rush har hafte hota hai."
    )
    out = reply_voice.localise_noted(reply, "roman_ur", 0)
    assert "I've noted it" not in out and "Thanks." not in out
    assert "note kar liya" in out.lower()
    assert out.endswith("shaam ka rush har hafte hota hai.")


def test_a_frame_at_the_start_still_works_and_other_replies_are_untouched():
    assert reply_voice.localise_noted("Thanks. I've noted it: stock", "roman_ur", 1).startswith(
        "Theek hai"
    )
    plain = "Haan, ho sakta hai. Kaunsi dukaan?"
    assert reply_voice.localise_noted(plain, "roman_ur", 0) == plain
    assert reply_voice.localise_noted("Thanks. I've noted it: x", "fr", 0) == (
        "Thanks. I've noted it: x"
    )


def test_no_roman_urdu_variant_is_gendered():
    from app.modules.pi import constitution

    for frame in reply_voice.FRAMES["roman_ur"]:
        assert not constitution.GENDERED_URDU.search(frame), frame
