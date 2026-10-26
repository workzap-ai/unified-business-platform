# ruff: noqa: E501  (Roman Urdu replies read better unbroken)
"""Live chat 3 (owner, 2026-10-26 15:52-15:58 PKT): replies the linter let through. The replies are
rebuilt from what the owner's chat showed; the person's words are the closest wording we have."""

from app.modules.pi import constitution, slots

H = [{"role": "ai", "text": "x"}]


def rules(reply: str, said: str, state: str = "S3_NOTED") -> set[str]:
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": "roman_ur",
        "history": H,
        "latest_customer_message": said,
    }
    return {v.rule for v in constitution.lint(reply, context)}


def test_reply_5_restating_the_customer_and_the_word_drop_off_are_caught():
    found = rules(
        "Reels views aa rahe hain, orders nahi aa rahe. Is drop-off ka sabab kya lagta hai?",
        "reels ke views aa rahe hain, orders nahi aa rahe",
    )
    assert "R-ECHO-04" in found
    assert "R-VOICE-03" in found  # drop-off: they did not say it


def test_the_noted_line_in_their_words_is_still_fine():
    found = rules(
        "Note kar liya, views aate hain magar orders nahi. Views ke baad log DM mein aate hain?",
        "reels par views aate hain lekin orders nahi aate",
    )
    assert not {"R-ECHO-04", "R-ECHO-01", "R-ECHO-03", "R-VOICE-03"} & found, found


def test_a_sentence_that_is_new_is_not_a_restatement():
    found = rules(
        "Views ke baad log DM mein price puchte hain. Un mein se kitne order karte hain?",
        "reels ke views aa rahe hain, orders nahi aa rahe",
    )
    assert "R-ECHO-04" not in found


def test_reply_11_you_are_right_to_a_plain_answer_is_caught_in_every_wording():
    for filler in (
        "Aap sahi keh rahe hain.",
        "Aap bilkul sahi keh rahe hain.",
        "Aap ne sahi kaha.",
        "You're absolutely right.",
        "You are right.",
        "Good point.",
    ):
        found = rules(f"{filler} Instagram par price ke baad kya hota hai?", "sirf raqam")
        assert "R-CORR-04" in found, filler


def test_you_are_right_is_fine_when_they_corrected_something():
    found = rules("Aap sahi keh rahe hain. Wo hata diya.", "ye galat hai, maine aisa nahi kaha")
    assert "R-CORR-04" not in found


def test_reply_11_asks_again_in_another_language_what_reply_9_asked():
    reply_9 = "What happens after you tell them the price on Instagram?"
    reply_11 = "Instagram par price batane ke baad kya hota hai, log kya kehte hain?"
    assert slots.same_question(reply_9, reply_11)
    closed = [{"slot": "", "q": reply_9}]
    assert slots.asked_again("", reply_11, closed) == reply_9


def test_two_different_questions_that_share_one_loan_word_are_not_the_same():
    assert not slots.same_question(
        "What do you sell on Instagram?", "Instagram par price kitna rakhte hain?"
    )
    assert not slots.same_question(
        "How many shops do you have in Karachi?", "Aap ke Lahore mein kitne employees hain?"
    )


def test_reply_13_theek_hai_before_the_noted_line_is_caught():
    found = rules(
        "Theek hai. Note kar liya: customers sirf raqam puchte hain. Kya size bhi poochte hain?",
        "sirf raqam",
    )
    assert "R-ECHO-01" in found


def test_reply_13_an_or_question_with_a_second_or_is_two_questions():
    found = rules(
        "Note kar liya, customers sirf raqam puchte hain. Size, colour, ya delivery bhi poochte hain, ya bas raqam par baat ruk jati hai?",
        "sirf raqam",
    )
    assert "R-VOICE-02" in found


def test_a_list_question_with_one_or_is_one_question():
    found = rules(
        "Note kar liya, customers sirf raqam puchte hain. Kya size, colour ya delivery bhi poochte hain?",
        "sirf raqam",
    )
    assert "R-VOICE-02" not in found
    found = rules("Noted. Do you sell online, in a shop, or both?", "we sell clothes")
    assert "R-VOICE-02" not in found
