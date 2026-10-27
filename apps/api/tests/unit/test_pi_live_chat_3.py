# ruff: noqa: E501  (Roman Urdu replies read better unbroken)
"""Live chat 3 (owner, 2026-10-26 15:52-15:58 PKT): the exact customer messages and the exact replies
pi sent, that the linter let through. Messages: (1) hello (2) the brand and the reels (3) 30-40 people
ask the price in DM (4) both, mostly Instagram (5) "sirf raqam" (6) "sirf raqam puchty hain" (7) "bas
raqam puchty hain" (8) "ap kya kr skty hain"."""

from types import SimpleNamespace as N

from app.modules.pi import constitution, slots
from app.modules.pi.service_conversation import reply_language

M2 = "mera online kapron ka brand hai Lahore mein, Instagram aur WhatsApp par bechta hoon. reels par views bohat aate hain lekin orders nahi aate"
M3 = "roz 30-40 log price poochte hain DM mein. price bata deta hoon to reply hi nahi aata"
M4 = "Dono mai whatsapp and instagram but mostly instagram"

R2 = "Reels views aa rahe hain, orders nahi aa rahe. Instagram ya WhatsApp mein zyada drop-off kahan hota hai?"
R3 = "Note kar liya: price ke baad reply band ho jata hai.\nYe Instagram DMs mein zyada hota hai ya WhatsApp par bhi?"
R4 = "Noted: mostly Instagram.\nWhat happens after they ask the price there?"
R5 = "Aap sahi keh rahe hain. Instagram par price ke baad kya hota hai, phir reply band hota hai ya log aur kuch poochte hain?"
R6 = "Theek hai. Note kar liya: sirf raqam pooch kar chup ho jate hain.\nPhir wo size, colour, ya delivery bhi poochte hain, ya bas raqam par baat ruk jati hai?"


def rules(reply: str, said: str, earlier: list[str] | None = None) -> set[str]:
    history = [{"role": "ai", "text": "x"}] + [
        {"role": "customer", "text": text} for text in earlier or []
    ]
    context = {
        "pi_mode": "brain",
        "flow": {"state": "S3_NOTED"},
        "reply_language": "roman_ur",
        "history": history,
        "latest_customer_message": said,
    }
    return {v.rule for v in constitution.lint(reply, context)}


def test_reply_2_restates_the_customer_and_says_drop_off():
    found = rules(R2, M2)
    assert (
        "R-ECHO-04" in found
    )  # "Reels views aa rahe hain, orders nahi aa rahe." is their sentence
    assert "R-VOICE-03" in found  # "drop-off": they did not say it


def test_reply_3_is_fine():
    assert not rules(R3, M3, [M2]) & {
        "R-ECHO-04",
        "R-ECHO-01",
        "R-VOICE-02",
        "R-VOICE-03",
        "R-CORR-04",
    }


def test_reply_4_switched_to_english_because_the_message_was_code_mixed():
    chat = [
        N(body=M3, sender_type="customer", message_type="text"),
        N(
            body="Note kar liya. Ye Instagram par zyada hota hai?",
            sender_type="ai",
            message_type="text",
        ),
        N(body=M2, sender_type="customer", message_type="text"),
    ]
    language = reply_language(
        N(), N(body=M4, sender_type="customer", message_type="text"), list(reversed(chat))
    )
    assert language["reply_language"] == "roman_ur"


def test_a_plain_english_message_still_switches_the_language():
    chat = [N(body=M2, sender_type="customer", message_type="text")]
    said = "Both WhatsApp and Instagram but mostly Instagram"
    language = reply_language(N(), N(body=said, sender_type="customer", message_type="text"), chat)
    assert language["reply_language"] == "en"


def test_reply_5_you_are_right_to_a_plain_answer_and_the_question_asked_again():
    assert "R-CORR-04" in rules(R5, "sirf raqam", [M2, M3, M4])
    q4 = "What happens after they ask the price there?"  # reply 4's question, English
    q5 = "Instagram par price ke baad kya hota hai, phir reply band hota hai ya log aur kuch poochte hain?"
    assert slots.same_question(q4, q5)
    assert slots.asked_again("", R5, [{"slot": "", "q": q4}]) == q4


def test_reply_6_theek_hai_filler_and_the_two_questions_in_one():
    found = rules(R6, "sirf raqam puchty hain", [M2, M3, M4, "sirf raqam"])
    assert "R-ECHO-01" in found  # "Theek hai." before "Note kar liya"
    assert "R-VOICE-02" in found  # "size, colour, ya delivery bhi poochte hain, ya bas raqam ..."


def test_the_replies_the_new_rules_catch_in_this_chat():
    caught = {
        name: rules(reply, said, earlier)
        for name, reply, said, earlier in (
            ("R2", R2, M2, []),
            ("R3", R3, M3, [M2]),
            ("R4", R4, M4, [M2, M3]),
            ("R5", R5, "sirf raqam", [M2, M3, M4]),
            ("R6", R6, "sirf raqam puchty hain", [M2, M3, M4, "sirf raqam"]),
        )
    }
    assert caught["R2"] and caught["R5"] and caught["R6"]
    assert not (caught["R3"] - {"R-ECHO-05"})  # the old noted opener is banned (spec v1.4, 17.6)


def test_two_different_questions_that_share_one_loan_word_are_not_the_same():
    assert not slots.same_question(
        "What do you sell on Instagram?", "Instagram par price kitna rakhte hain?"
    )
    assert not slots.same_question(
        "How many shops do you have in Karachi?", "Aap ke Lahore mein kitne employees hain?"
    )


def test_the_agreement_fillers_in_other_wordings():
    for filler in (
        "Aap bilkul sahi keh rahe hain.",
        "Aap ne sahi kaha.",
        "You're absolutely right.",
        "You are right.",
        "Good point.",
    ):
        assert "R-CORR-04" in rules(f"{filler} Phir kya hota hai?", "sirf raqam"), filler
    assert "R-CORR-04" not in rules(
        "Aap sahi keh rahe hain. Wo hata diya.", "ye galat hai, maine aisa nahi kaha"
    )


def test_a_list_question_with_one_or_is_one_question():
    found = rules(
        "Note kar liya, customers sirf raqam puchte hain. Kya size, colour ya delivery bhi poochte hain?",
        "sirf raqam",
    )
    assert "R-VOICE-02" not in found
    assert "R-VOICE-02" not in rules(
        "Noted. Do you sell online, in a shop, or both?", "we sell clothes"
    )


def test_the_noted_line_in_their_words_is_still_fine():
    found = rules(
        "Note kar liya, views aate hain magar orders nahi. Views ke baad log DM mein aate hain?",
        "reels par views aate hain lekin orders nahi aate",
    )
    assert not {"R-ECHO-04", "R-ECHO-01", "R-ECHO-03", "R-VOICE-03"} & found, found
