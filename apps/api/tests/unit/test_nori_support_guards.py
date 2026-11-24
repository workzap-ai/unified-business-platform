"""Nori support mode: what a support reply must pass, and how nori's facts are read. No database."""

from datetime import date

from app.modules.pi_saas.nori_support import facts, guards

HOST = "nori.test"
TODAY = date(2026, 11, 17)
WORKSPACE = {
    "name": "Mendeez Demo",
    "business": {"industry": "retail", "summary": "Two shops", "country": "PK"},
    "owner": {"name": "Owner", "phone": "923001112222"},
    "plan": "Starter",
    "status": "trial",
    "trial_ends_at": "2026-11-20T10:00:00Z",
    "subscription_ends_at": None,
    "credits": 120,
    "credits_low": False,
    "health": {"status": "ok", "note": None},
}


def vet(reply, *, facts_text="", person="hello", first=False, language="en"):
    return guards.vet(
        reply,
        facts_text=facts_text,
        person_text=person,
        nori_host=HOST,
        language=language,
        first_reply=first,
    )


def block():
    parsed = facts.parse(WORKSPACE)
    assert parsed is not None
    return parsed.block(TODAY)


# --- facts ---


def test_facts_keep_only_what_nori_sent_and_never_the_owner_phone():
    text = block()
    assert "Workspace name: Mendeez Demo" in text
    assert "Trial ends on: 20 November 2026" in text
    assert "Days left: 3" in text
    assert "Credits left: 120" in text
    assert "923001112222" not in text  # the owner's phone is not part of what the model sees
    assert "Subscription ends" not in text  # null stays absent, nothing is invented


def test_facts_redact_personal_data_in_free_text_and_drop_the_owner_name():
    parsed = facts.parse(
        {
            **WORKSPACE,
            "business": {"summary": "Call 0300 1234567 or mail a@b.co"},
            "owner": {"name": "Olive"},
        }
    )
    assert parsed is not None
    text = parsed.block(TODAY)
    assert "1234567" not in text and "a@b.co" not in text
    assert "Olive" not in text


def test_facts_days_left_goes_negative_after_the_end():
    parsed = facts.parse({**WORKSPACE, "trial_ends_at": "2026-11-10T00:00:00Z"})
    assert parsed is not None
    assert parsed.days_left(TODAY) == -7
    assert "Days since it ended: 7" in parsed.block(TODAY)


def test_facts_reject_garbage_and_cap_text():
    assert facts.parse(None) is None
    assert facts.parse({}) is None
    assert facts.parse({"credits": True, "status": "weird", "health": {"status": "meh"}}) is None
    long = facts.parse({"name": "x" * 500})
    assert long is not None and long.name is not None and len(long.name) == 120


# --- the reply checks ---


def test_a_grounded_reply_passes_and_the_first_one_says_it_is_an_ai():
    reply = "Your trial ends on 20 November and 120 credits are left. Do you want more time?"
    assert vet(reply, facts_text=block(), first=False) == reply
    first = vet(reply, facts_text=block(), first=True)
    assert first is not None and first.startswith("I'm pi, an AI assistant.")


def test_the_disclosure_follows_the_language():
    said = vet(
        "Aap ka trial 20 November ko khatam hoga.",
        facts_text=block(),
        first=True,
        language="roman_ur",
    )
    assert said is not None and said.startswith("Main pi hoon, ek AI assistant.")


def test_an_invented_number_or_date_is_refused():
    assert vet("You have 999 credits left.", facts_text=block()) is None
    assert vet("Your trial ends on 20 December.", facts_text=block()) is None
    assert vet("Your trial ends in 5 days.", facts_text=block()) is None


def test_a_number_the_person_typed_is_not_a_licence_to_state_it_as_fact():
    assert vet("You have 42 credits.", person="i think i have 42 credits") is None


def test_the_ai_line_must_be_in_the_first_sentence():
    said = vet("Your AI credits are low, so please open nori.", first=True)
    assert said is not None and said.startswith("I'm pi, an AI assistant. Your AI credits")
    kept = vet("I'm pi, an AI assistant. Noted for the team.", first=True)
    assert kept == "I'm pi, an AI assistant. Noted for the team."


def test_payment_receipt_and_credit_claims_are_refused():
    assert vet("Thanks, your payment has been received.") is None
    assert vet("Payment received, credits are added.") is None
    assert vet("Your credits were added just now.") is None


def test_secret_words_in_plural_roman_urdu_and_urdu_are_refused():
    assert vet("Please send the card numbers.") is None
    assert vet("Apna password bata dein.") is None
    assert vet("اپنا پاسورڈ بھیجیں۔", language="ur") is None
    assert vet("Pay with JazzCash please.") is None


def test_promises_and_upsell_are_refused():
    assert vet("The team will fix it tomorrow.") is None
    assert vet("We will add it within two days.") is None
    assert vet("I recommend you upgrade to the best plan.") is None


def test_advice_in_the_reply_is_refused():
    assert vet("You should register a company to pay less tax on this.") is None


def test_a_fixed_safety_line_keeps_its_warning_words():
    line = "Please do not type card details or bank details in chat."
    kwargs = {"facts_text": "", "person_text": "", "nori_host": HOST, "language": "en"}
    assert guards.vet(line, first_reply=True, fixed=True, **kwargs) is not None
    assert guards.vet(line, first_reply=False, **kwargs) is None


def test_no_facts_means_no_figure_at_all():
    assert vet("You have 120 credits left.", facts_text="") is None
    assert vet("I will check with the Workzap team.", facts_text="") is not None


def test_one_question_and_it_is_last():
    assert vet("Noted. Which page? Which user?") is None
    assert vet("Which page is it? I have noted it.") is None
    assert vet("I have noted it. Which page is it?") is not None
    assert vet("میں نے نوٹ کر لیا۔ کون سا صفحہ ہے؟", language="ur") is not None


def test_secrets_payment_and_foreign_links_are_refused():
    assert vet("Please send your card number here.") is None
    assert vet("Tell me the OTP you received.") is None
    assert vet("Pay by bank transfer to this account.") is None
    assert vet("Open https://evil.example/pay to top up.") is None
    assert vet("Open https://nori.test/billing to top up.") is not None


def test_empty_or_too_long_or_control_characters():
    assert vet("") is None
    assert vet(None) is None
    assert vet("x" * (guards.MAX_REPLY + 1)) is None
    assert vet("Noted\x00 for the team.") == "Noted for the team."
