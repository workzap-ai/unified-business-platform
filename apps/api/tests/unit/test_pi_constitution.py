"""pi's constitution and voice linter (pi Brain spec Parts 1, 2 and 6)."""

import pytest

from app.modules.pi import constitution as c

AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}


def context(latest="my stock keeps running out", history=None, **extra):
    """A conversation where pi already said it is an AI, unless `history` says otherwise."""
    return {
        "latest_customer_message": latest,
        "history": [AI_TURN] if history is None else history,
        **extra,
    }


def rules(reply, **kwargs):
    return {v.rule for v in c.lint(reply, context(**kwargs))}


def test_a_plain_good_reply_breaks_nothing():
    assert (
        c.lint("Noted: best-sellers running out. Is it every shop, or only some?", context()) == []
    )


@pytest.mark.parametrize(
    "reply",
    [
        "Thanks. I've noted it: best-sellers running out ✅. Anything else getting in the way?",
        "Is it the big godown or the one near the port?",
        "• Stock (2)\n• Staff (1)\n• Cash (1)\nIs anything wrong or missing?",
    ],
)
def test_the_spec_own_phrasings_pass(reply):
    assert c.lint(reply, context()) == []


def test_the_first_message_must_say_it_is_an_ai():
    bare = "Tell me what is going wrong in your business."
    assert {v.rule for v in c.lint(bare, context(history=[]))} == {"R-DISC-01"}
    assert c.lint("Hi, I'm pi, an AI from Workzap. What is going wrong?", context(history=[])) == []


def test_repair_adds_the_opening_when_the_ai_line_is_missing():
    fixed = c.repair("What is going wrong?", context(history=[]))
    assert fixed.startswith("Hi, I'm pi, an AI from Workzap.")
    assert c.lint(fixed, context(history=[])) == []
    roman = c.repair("Kya masla hai?", context(history=[], reply_language="roman_ur"))
    assert roman.startswith("Hi, main pi hoon, Workzap ka AI.")


@pytest.mark.parametrize(
    "asked",
    ["are you a bot?", "Is this a real person?", "kya aap insaan ho?", "who am I talking to?"],
)
def test_asked_if_it_is_a_person_the_first_sentence_says_ai(asked):
    assert "R-DISC-02" in rules("Sure. Which shop is it?", latest=asked)
    assert "R-DISC-02" not in rules("I'm an AI, not a person. Which shop is it?", latest=asked)


@pytest.mark.parametrize(
    "reply",
    [
        "I'm a man from Karachi. Which shop?",
        "I know exactly how you feel, I've run a shop too.",
        "My family also had this problem.",
        "I was at the market yesterday and saw the same thing.",
    ],
)
def test_pi_never_claims_to_be_human(reply):
    assert "R-DISC-03" in rules(reply)


def test_pi_never_names_other_companies_as_its_maker():
    assert "R-BRAND-01" in rules("I'm made by Artwing Studios. Which shop?")


@pytest.mark.parametrize(
    "reply",
    [
        "Please send your card number so I can check.",
        "Share your password and I will look.",
        "Can you give me the OTP?",
        "Apna CNIC bhej dein.",
    ],
)
def test_pi_never_asks_for_card_password_otp_or_id(reply):
    assert "R-PAY-02" in rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Please don't send card numbers here. I never need them.",
        "I never ask for passwords or OTPs. Which shop is it?",
        "Card number mat bhejein, iski zaroorat nahi.",
    ],
)
def test_refusing_to_take_sensitive_data_is_allowed(reply):
    assert "R-PAY-02" not in rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Transfer to PK36SCBL0000001123456702 please.",
        "Our IBAN: AE07 0331 2345 6789 0123 456",
        "Account number: 0123456789012",
    ],
)
def test_pi_never_types_bank_details(reply):
    assert "R-PAY-03" in rules(reply)


def test_bank_details_stay_on_the_quote():
    assert "R-PAY-03" not in rules("The bank details are on page two of your approved quote.")


@pytest.mark.parametrize(
    "reply",
    [
        "Payment received, thank you.",
        "We have received your payment.",
        "Your transfer is confirmed.",
    ],
)
def test_pi_never_says_payment_arrived_unless_staff_confirmed(reply):
    assert "R-PAY-05" in rules(reply)
    assert "R-PAY-05" not in rules(reply, payment_confirmed=True)


@pytest.mark.parametrize(
    "reply",
    ["This will fix it.", "We guarantee results.", "You'll save 30% on stock.", "It always works."],
)
def test_pi_never_promises_a_result(reply):
    assert "R-PROM-01" in rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Your sales will rise once you start.",
        "You'll see more customers soon.",
        "Footfall barh jayegi, fikar na karein.",
        "Next year you will be bigger.",
    ],
)
def test_pi_never_forecasts_the_persons_numbers(reply):  # R-PROM-03
    assert "R-PROM-01" in rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "I can't say sales will rise.",
        "Sale barhani hai, ye note kar liya hai.",
        "The document will cover it.",
    ],
)
def test_noting_a_goal_or_refusing_to_forecast_is_fine(reply):
    assert "R-PROM-01" not in rules(reply)


def test_saying_it_cannot_guarantee_is_fine():
    assert "R-PROM-01" not in rules("I can't guarantee anything. Which shop?")


def test_sorted_is_never_solved():
    assert "R-LANG-01" in rules("Your stock problem is solved.")
    assert "R-LANG-01" not in rules("None of it is solved yet.")


def test_one_question_and_it_comes_last():
    assert "R-VOICE-02" in rules("Which shop? And how often?")
    assert "R-VOICE-02" in rules("Which shop is it? I will note it.")
    assert "R-VOICE-02" not in rules("Noted. Which shop is it?")
    assert "R-VOICE-02" not in rules("Kaunsi shop hai؟")


def test_length_caps_for_a_reply_a_summary_and_a_document():
    long = " ".join(["word"] * 61)
    assert "R-VOICE-01" in rules(long)
    assert "R-VOICE-01" not in rules(" ".join(["word"] * 60))
    summary = "\n".join(["• " + " ".join(["a"] * 20)] * 3)  # 60 words, three bullets
    assert "R-VOICE-01" not in rules(summary + "\n" + " ".join(["b"] * 90))
    assert "R-VOICE-01" in rules(summary + "\n" + " ".join(["b"] * 110))
    cover = "Your document: https://workzap.ai/d/abc " + " ".join(["w"] * 80)
    assert "R-VOICE-01" not in rules(cover)


@pytest.mark.parametrize(
    "reply",
    [
        "That is amazing news.",
        "Great question! Which shop?",
        "I'd be happy to help.",
        "Let's unlock growth.",
    ],
)
def test_no_hype(reply):
    assert "R-VOICE-05" in rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "I completely understand how frustrating that must be.",
        "I'm so sorry to hear that.",
        "Thank you for contacting Workzap.",
        "Kindly note that stock is tracked.",
        "As an AI language model I cannot say.",
    ],
)
def test_no_scripted_empathy_or_template_phrases(reply):
    assert "R-VOICE-06" in rules(reply)


def test_real_short_reactions_are_fine():
    for reply in ("That's a real problem.", "That sounds costly.", "Oof, every week?"):
        assert c.lint(reply, context()) == [] or "R-VOICE-06" not in rules(reply)


def test_exclamation_marks_only_when_they_used_one_and_only_one():
    # spec R-VOICE-07: only a festival greeting, only if they used one first, once per conversation
    assert "R-VOICE-07" in rules("Noted!")
    assert "R-VOICE-07" in rules("Noted!", latest="stock khatam ho gaya!")  # not a festival
    assert "R-VOICE-07" not in rules("Eid Mubarak!", latest="Eid Mubarak!")
    assert "R-VOICE-07" in rules("Eid Mubarak! Sorted!", latest="Eid Mubarak!")


def test_emoji_only_a_tick_unless_they_use_emoji():
    assert "R-VOICE-08" not in rules("Noted ✅")
    assert "R-VOICE-08" in rules("Noted 😊")
    assert "R-VOICE-08" not in rules("Noted 😊", latest="stock khatam 😭")
    assert "R-VOICE-08" in rules("Noted ✅ ✅")


def test_repair_removes_stray_bangs_and_emoji():
    assert c.repair("Noted! Thanks!", context()) == "Noted. Thanks."
    assert c.repair("Noted 😊", context()) == "Noted"
    assert c.repair("Noted ✅", context()) == "Noted ✅"
    assert c.repair("Noted! Thanks!", context(latest="Eid Mubarak!")) == "Noted! Thanks."


def test_whatsapp_formatting_only():
    assert "R-VOICE-09" in rules("## Your problems\nStock")
    assert "R-VOICE-09" in rules("**Stock** problem noted.")
    assert "R-VOICE-09" not in rules("*Stock* problem noted.")


def test_say_noted_not_logged():
    assert "R-VOICE-10" in rules("I've logged it.")
    assert "R-VOICE-10" not in rules("I've noted it.")


def test_no_lecturing():
    assert "R-VOICE-12" in rules("You should use a stock register.")
    assert "R-VOICE-12" in rules("Best practices say count weekly.")


def test_jargon_only_if_they_used_it_first():
    assert "R-VOICE-03" in rules("Which SKU runs out?")
    assert "R-VOICE-03" not in rules("Which SKU runs out?", latest="my SKU count is wrong")
    assert "R-VOICE-03" in rules("Is it a pain point?")


def test_no_internal_terms():
    assert "R-VOICE-06" in rules("I loaded your industry pack.")
    assert "R-VOICE-06" in rules("State is S2_CLARIFYING.")


def test_not_the_same_opening_three_times():
    history = [
        AI_TURN,
        {"role": "ai", "text": "Got it, which shop?"},
        {"role": "ai", "text": "Got it, and cash?"},
    ]
    assert "R-VOICE-04" in rules("Got it, how often?", history=history)
    assert "R-VOICE-04" not in rules("Noted. How often?", history=history)


def test_only_hard_rules_stop_a_reply_for_good():
    broke = c.lint("Payment received! Which shop?", context())
    assert {v.rule for v in c.hard(broke)} == {"R-PAY-05"}
    assert "R-VOICE-07" in {v.rule for v in broke}
    assert "R-PAY-05" in c.describe(broke) and "exclamation" in c.describe(broke)


def listening(state="S1_LISTENING", latest="my stock keeps running out"):
    return context(latest=latest, flow={"state": state})


@pytest.mark.parametrize(
    "reply",
    [
        "We can build an app for that. Which shop is it?",
        "Workzap would automate that for you.",
        "Our software handles stock. Which shop is it?",
        "Have you tried nori? Which shop?",
        "Shall I send you a quote?",
        "I'd recommend a stock system.",
    ],
)
def test_no_pitching_while_listening(reply):
    for state in ("S0_NEW", "S1_LISTENING", "S2_CLARIFYING", "S3_NOTED", "S4_SORTED_SUMMARY"):
        found = {v.rule for v in c.lint(reply, listening(state))}
        assert "R-SELL-01" in found, (state, reply)
    assert {v.rule for v in c.lint(reply, listening("S5b_DECLINED"))} >= {"R-SELL-01"}


def test_pitching_is_a_hard_break():
    broke = c.lint("We can build an app for that.", listening())
    assert "R-SELL-01" in {v.rule for v in c.hard(broke)}


def test_the_offer_and_later_states_may_talk_about_a_document_and_quote():
    offer = "Would you like a solution document and a quote for these? You can say no."
    assert "R-SELL-01" not in {v.rule for v in c.lint(offer, listening("S5_READINESS"))}
    assert "R-SELL-01" not in {v.rule for v in c.lint(offer, listening("S7_DELIVERED"))}


def test_a_direct_question_gets_one_honest_line_not_a_description():
    asked = listening(latest="can you fix this? what would you build?")
    honest = (
        "Workzap can prepare a solution document once the problems are noted. Which shop is it?"
    )
    assert "R-SELL-01" not in {v.rule for v in c.lint(honest, asked)}
    describing = "We would build an app that fixes your stock."
    assert "R-SELL-01" in {v.rule for v in c.lint(describing, asked)}


def test_no_state_in_context_means_the_pitch_rule_is_not_applied():
    assert "R-SELL-01" not in rules("Shall I send you a quote?")


@pytest.mark.parametrize(
    "reply",
    ["Limited time: say yes today.", "This is your last chance.", "Only 3 days left on the offer.",
     "We can give a discount if you decide now."],
)  # fmt: skip
def test_no_urgency_scarcity_or_discounts_in_any_state(reply):
    assert "R-SELL-03" in rules(reply)
    assert "R-SELL-03" in {v.rule for v in c.hard(c.lint(reply, listening("S7_DELIVERED")))}


def test_while_listening_pi_does_not_list_back_what_it_already_confirmed():
    earlier = {
        "role": "ai",
        "text": "• Aapka dhanda nahi chal raha hai.\n• Footfall nahi hai.\nKya bechte hain?",
    }
    relist = "• Footfall nahi hai.\nAap ab customers kaise laate hain?"
    said = context(
        latest="Kapron ki dukaan hai, footfall chahiye",
        history=[AI_TURN, earlier],
        flow={"state": "S1_LISTENING"},
    )
    assert "R-VOICE-09" in {v.rule for v in c.lint(relist, said)}


def test_a_short_answer_gets_no_list_of_its_story():
    reply = (
        "• No footfall.\n• Facebook ads and SMS.\n• Shops in Defence.\n"
        "Anything else getting in the way?"
    )
    assert "R-VOICE-09" in {v.rule for v in c.lint(reply, listening(latest="no"))}
    assert "R-VOICE-09" in {
        v.rule for v in c.lint("• Stock out\n• Stock out\nWhich shop?", listening())
    }


def test_several_new_problems_in_one_message_may_be_listed():
    said = (
        "stock runs out, my cashiers come late on weekends and the cash never matches at one branch"
    )
    reply = (
        "Thanks. I've noted three things:\n• Stock running out\n"
        "• Cashiers late on weekends\n• Cash not matching\nWhich of these costs you the most?"
    )
    assert "R-VOICE-09" not in {v.rule for v in c.lint(reply, listening(latest=said))}
    assert "R-VOICE-09" not in {v.rule for v in c.lint(reply, context(latest="no"))}  # no state


def test_a_correction_is_never_met_with_i_did_not_understand():
    reply = "Maaf kijiye, aap ki baat samajh nahi aayi. Kis maslay par baat karni hai?"
    assert "R-CORR-02" in {v.rule for v in c.lint(reply, context(said_wrong=True))}
    assert "R-CORR-02" not in {v.rule for v in c.lint(reply, context())}
    fixed = "Aap sahi keh rahe hain, wo hata diya. Stock kis cheez ka kam ho raha hai?"
    assert "R-CORR-02" not in {v.rule for v in c.lint(fixed, context(said_wrong=True))}


def test_no_stiff_apology():
    assert "R-VOICE-04" in rules("Mujhe maazrat chahiye. Kaunsi shop hai?")


def test_a_complaint_about_the_questions_gets_no_document_talk_but_a_direct_ask_does():
    reply = (
        "Workzap can prepare a solution document once the problems are noted. Is that everything?"
    )
    asked = listening(latest="Kya solution hai tumhare paas?")
    assert "R-SELL-01" not in {v.rule for v in c.lint(reply, asked)}
    pushed = listening(latest="Batao kuch kar sakte hain ya nahi kar sakte?")
    assert "R-SELL-01" not in {v.rule for v in c.lint(reply, pushed)}
    complaint = listening(latest="sawal hi poochti rahogi kya?")
    assert "R-SELL-01" in {v.rule for v in c.hard(c.lint(reply, complaint))}
    pitch = "We can build an app for that. Is that everything?"
    assert "R-SELL-01" in {v.rule for v in c.hard(c.lint(pitch, asked))}


@pytest.mark.parametrize(
    "reply,field,value",
    [
        ("Thanks for that. What is your name?", "name", "Ata"),
        ("Noted. Ap ka naam kya hai?", "name", "Ata"),
        ("Got it. What is your business called?", "business_name", "Ata Traders"),
        ("Theek hai. Business ka naam kya hai?", "business_name", "Ata Traders"),
        ("I see. What kind of business is this?", "business_type", "kiryana store"),
        ("Samjha. Which city are you based in?", "location", "Lahore"),
    ],
)
def test_never_re_asks_a_known_profile_fact(reply, field, value):
    known = {field: value}
    assert "R-MEM-02" in {v.rule for v in c.lint(reply, context(customer_profile=known))}
    assert "R-MEM-02" not in {v.rule for v in c.lint(reply, context())}


def test_profile_reask_check_does_not_flag_unrelated_or_unknown_questions():
    profile = {"name": "Ata", "business_name": "Ata Traders"}
    # A genuinely different question about a field that IS known stays clear.
    assert "R-MEM-02" not in rules(
        "Noted. Is this happening at every branch?", customer_profile=profile
    )
    # The same question about a field that is NOT yet known is still allowed.
    assert "R-MEM-02" not in rules("Thanks. Which city are you based in?", customer_profile=profile)
    # A placeholder value (never really answered) does not count as known.
    assert "R-MEM-02" not in rules("What is your name?", customer_profile={"name": "WhatsApp User"})
