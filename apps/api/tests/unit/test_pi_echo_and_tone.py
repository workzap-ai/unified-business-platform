"""Book 2 Part 10.1 and 10.2: pi does not echo the person back (R-ECHO-01..03, RT35) and never
judges the person or the business (R-TONE-01, RT36). Found in the audited live chat."""

from app.modules.pi import constitution


def lint_rules(said: str, reply: str, state: str = "S3_NOTED", history=None) -> list[str]:
    context = {
        "latest_customer_message": said,
        "history": history or [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}],
        "flow": {"state": state},
    }
    return [v.rule for v in constitution.lint(reply, context)]


LONG = (
    "Bhai mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein aur footfall "
    "nahi hai kya karun"
)


def test_a_reply_that_restates_the_message_is_flagged_as_an_echo():
    echo = (
        "Aap ne kaha ke mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein aur "
        "footfall nahi hai. Kaunsi cheez ki dukaanain hain?"
    )
    assert "R-ECHO-03" in lint_rules(LONG, echo)


def test_a_short_confirmation_and_a_fresh_reply_are_not_echoes():
    assert "R-ECHO-03" not in lint_rules(
        LONG, "Noted: footfall is low. Kaunsi cheez ki dukaanain hain?"
    )
    fresh = (
        "Haan, is par kaam ho sakta hai. Footfall kam hona ek hal hone wala masla hai. Sahi idea "
        "dene ke liye ek cheez batayein: dukaanon mein kis cheez ka kaam hai?"
    )
    assert "R-ECHO-03" not in lint_rules(LONG, fresh)


def test_the_summary_may_restate_what_was_noted():
    summary = (
        "Here is what I have noted and sorted so far. None of it is solved yet. "
        "Mera dhanda nahi chal raha aur meri kuch dukaanain hain defense mein aur "
        "footfall nahi hai."
    )
    assert "R-ECHO-03" not in lint_rules(LONG, summary, state="S4_SORTED_SUMMARY")


def test_judging_the_person_or_the_business_is_banned_even_if_they_said_it_first():
    for reply in (
        "Your business is not doing well. What do you sell?",
        "Your sales are bad right now. Which shop is worst?",
        "You are doing it wrong. Which channel do you use?",
        "Aapka business fail ho raha hai. Kaunsi dukaan sab se kam chalti hai?",
    ):
        assert "R-TONE-01" in lint_rules("my business is not doing well", reply), reply
    for reply in (
        "Sales and footfall are low, noted. Which shop is the slowest?",
        "Aap ke footfall kam hain, note kar liya. Kaunsi dukaan sab se kam chalti hai?",
    ):
        assert "R-TONE-01" not in lint_rules("sale kam hai", reply), reply
