# ruff: noqa: E501  (Roman Urdu replies read better unbroken)
"""Live chat 2026-10-26 15:09-15:14 (+92...598): replies the linter let through that the owner's golden
voice does not allow. The exact replies are the test data."""

from app.modules.pi import constitution

HISTORY = [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}]
SAID = "reels par views aate hain lekin orders nahi aate"


def lint(reply: str, said: str, state: str = "S3_NOTED") -> dict[str, str]:
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": "roman_ur",
        "history": HISTORY,
        "latest_customer_message": said,
    }
    return {v.rule: v.message for v in constitution.lint(reply, context)}


def test_reply_5_verdict_opener_and_stock_thanks_are_caught():
    reply = (
        "Ye real masla hai. Shukriya. Maine note kar liya: reels par views aate hain lekin "
        "orders nahi aate. Kya views ke baad log DM mein aate hain?"
    )
    found = lint(reply, SAID)
    assert "R-TONE-01" in found
    assert "R-ECHO-01" in found or "R-ECHO-03" in found


def test_the_golden_noted_line_is_clean():
    reply = "Note kar liya, views aate hain magar orders nahi. Views ke baad log DM mein aate hain?"
    found = lint(reply, SAID)
    assert not {"R-TONE-01", "R-ECHO-01", "R-ECHO-03", "R-ASK-05"} & set(found), found


def test_a_thank_you_then_the_noted_line_is_caught_but_a_plain_thanks_is_not():
    assert "R-ECHO-01" in lint("Shukriya. Maine note kar liya, orders nahi aate. Kab se?", SAID)
    assert "R-ECHO-01" not in lint("Shukriya, aap ka waqt dene ka. Kab se aisa hai?", SAID)


def test_a_verdict_opener_in_english_is_caught():
    found = lint("That's a real problem. What do you do about it today?", "orders nahi aate")
    assert "R-TONE-01" in found


def test_reply_7_generic_closer_right_after_a_detail_is_caught():
    said = "rozana 30-40 log DM mein price puchte hain phir koi jawab nahi dete"
    reply = "Note kar liya, DM mein price puchne ke baad log chup ho jate hain. Aur kuch is mein add karna hai?"
    assert "R-ASK-05" in lint(reply, said, "S5_READINESS")
    specific = "Note kar liya, DM mein price puchne ke baad log chup ho jate hain. Price batane ke kitni der baad woh chup hote hain?"
    assert "R-ASK-05" not in lint(specific, said, "S5_READINESS")


def test_the_generic_closer_is_fine_after_a_short_answer_and_in_the_summary():
    reply = "Note kar liya. Aur kuch add karna hai?"
    assert "R-ASK-05" not in lint(reply, "nahi")
    said = "rozana 30-40 log DM mein price puchte hain phir koi jawab nahi dete"
    assert "R-ASK-05" not in lint(reply, said, "S4_SORTED_SUMMARY")
