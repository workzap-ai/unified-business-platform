# ruff: noqa: E501  (Arabic and Urdu lines read better unbroken)
"""The reply linter's hardening pass: the owner's own trade words, one question last, the "must not"
style rules, invented proof, ID and personal-data asks, Arabic and Urdu, advice, and the pack lines."""

import json
from pathlib import Path

import pytest

from app.modules.pi import constitution as c

AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}
PACKS = Path(c.__file__).parent / "packs" / "industry"


def ctx(latest="my stock keeps running out", history=None, state="S1_LISTENING", **extra):
    return {
        "latest_customer_message": latest,
        "history": [AI_TURN] if history is None else history,
        "flow": {"state": state},
        **extra,
    }


def rules(reply, **kwargs):
    return {v.rule for v in c.lint(reply, ctx(**kwargs))}


def hard_rules(reply, **kwargs):
    return {v.rule for v in c.hard(c.lint(reply, ctx(**kwargs)))}


# 1. the owner's own words ------------------------------------------------------------------------
def test_a_trade_word_the_customer_used_may_be_echoed_while_listening():
    said = "our quotes take a day to prepare"
    assert "R-SELL-01" not in hard_rules(
        "Noted, quotes take a day to prepare. Who prepares them?", latest=said
    )
    assert "R-SELL-01" in hard_rules("Noted, quotes take a day to prepare. Who prepares them?")
    assert "R-SELL-01" in hard_rules("Shall I send you a quotation?", latest=said)
    assert "R-SELL-01" not in hard_rules(
        "Got it, noted: no itemised quote, just a total. Most clients?"
    )


def test_the_echo_never_reaches_the_asked_turn():
    asked = ctx(latest="our quotes take a day", solution_asked=True)
    assert "R-OFFER-03" in {v.rule for v in c.hard(c.lint("Workzap can send you a quote.", asked))}


def test_a_word_the_customer_used_is_not_a_promise_but_a_promise_is():
    said = "guest count se zyada log aate hain, guaranteed count ka masla hai"
    assert "R-PROM-01" not in hard_rules(
        "Noted, guaranteed count se zyada log aate hain. Kab tay hota hai?", latest=said
    )
    assert "R-PROM-01" in hard_rules("We guarantee results.", latest=said)
    assert "R-PROM-01" in hard_rules("It is guaranteed to work.", latest=said)


def test_asking_about_the_discounts_they_deal_with_is_not_offering_one():
    assert "R-SELL-03" not in hard_rules(
        "Is it the commission, the discounts, or refunds you can't make sense of?"
    )
    assert "R-SELL-03" in hard_rules("Would you like a discount?")


# 2. one question, last ---------------------------------------------------------------------------
def test_repair_handles_a_multi_line_reply_with_several_questions():
    fixed = c.repair("Noted.\nIs it every shop?\nOr only some?", ctx())
    assert fixed.count("?") == 1 and fixed.endswith("?")
    assert not [v for v in c.lint(fixed, ctx()) if v.rule == "R-VOICE-02"]


def test_repair_keeps_the_bullets_of_a_summary():
    reply = "Here is what I noted:\n• Stock runs out\n• Cashiers are late\n• Cash does not match\nWhich costs most?\nIs it stock?"
    fixed = c.repair(reply, ctx(state="S4_SORTED_SUMMARY"))
    assert fixed.count("•") == 3
    assert fixed.count("?") == 1 and fixed.endswith("Is it stock?")


def test_a_hard_break_that_survives_the_rewrite_falls_back_to_a_safe_line():
    fixed = c.repair("We guarantee this. Which shop?", ctx())
    assert fixed == c.FALLBACK_LISTENING["en"]
    assert c.hard(c.lint(fixed, ctx())) == []


@pytest.mark.parametrize("language", ["en", "roman_ur", "ur", "ar"])
@pytest.mark.parametrize(
    "state",
    [
        "S0_NEW",
        "S1_LISTENING",
        "S2_CLARIFYING",
        "S3_NOTED",
        "S4_SORTED_SUMMARY",
        "S5_READINESS",
        "S10_AWAITING_PAYMENT",
    ],
)
def test_every_safe_line_passes_the_linter(language, state):
    for history in ([], [AI_TURN]):
        for latest in ("my stock keeps running out", "are you a bot?"):
            context = ctx(latest=latest, history=history, state=state, reply_language=language)
            line = c.safe_fallback(context)
            assert c.hard(c.lint(line, context)) == [], (language, state, line)


def test_a_fallback_for_the_first_message_keeps_the_disclosure():
    line = c.repair("Payment received. Hello!", ctx(history=[]))
    assert c.opening_line(ctx(history=[])) in line


def test_asked_if_pi_is_human_repair_adds_the_answer():
    fixed = c.repair("Which shop is it?", ctx(latest="are you a bot?"))
    assert fixed.startswith("I'm an AI, not a person")


# 3. must-not style rules are hard -----------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Your stock problem is solved.",
        "That is amazing.",
        "I completely understand how frustrating that must be.",
        "Our team will get back to you shortly.",
        "I'm just a bot.",
    ],
)
def test_the_must_not_phrases_are_hard(reply):
    assert hard_rules(reply)


def test_hype_the_customer_used_is_not_hype_and_repair_drops_the_phrase():
    assert "R-VOICE-05" not in hard_rules(
        "Noted, the seamless checkout. Which shop?", latest="we want a seamless checkout"
    )
    fixed = c.repair("Great question! Noted, stock runs out. Which shop?", ctx())
    assert "Great question" not in fixed and fixed.endswith("Which shop?")


# 4. R-HONEST-01 ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "We can have it ready in two weeks.",
        "Workzap can deliver by next Friday.",
        "It will take a month.",
        "Kal tak ho jayega.",
        "Do hafte mein ho jayega.",
        "Done within a week.",
        "ہم خلال أسبوعين",
    ],
)
def test_invented_timelines_are_hard(reply):
    assert "R-HONEST-01" in hard_rules(reply)


def test_their_own_dates_are_not_flagged():
    assert "R-HONEST-01" not in hard_rules(
        "Noted, it takes two weeks. Who chases it?", latest="filing takes us 2 weeks every quarter"
    )
    assert "R-HONEST-01" not in hard_rules(
        "Noted, ek hafte tak ki der. Kaun dekhta hai?", latest="kabhi kabhi hafte baad"
    )
    assert "R-HONEST-01" not in hard_rules("How many orders a week?")


@pytest.mark.parametrize(
    "reply",
    [
        "We worked with similar clinics and cut waiting by half.",
        "In one of our case studies, a bakery grew.",
        "Studies show most shops lose sales.",
        "On average owners save a lot.",
        "Ask my colleague Sana about it.",
        "A client of ours saw a 40% rise.",
    ],
)
def test_invented_proof_is_hard(reply):
    assert "R-HONEST-01" in hard_rules(reply)


def test_approved_context_may_carry_a_case_study():
    assert "R-HONEST-01" not in hard_rules(
        "See the case study.", approved_claims=["see the case study"]
    )


def test_an_amount_needs_an_approved_quote_or_their_own_number():
    assert "R-HONEST-01" in hard_rules("It costs Rs 5000.")
    assert "R-HONEST-01" not in hard_rules("It costs Rs 5000.", approved_quote=True)
    assert "R-HONEST-01" not in hard_rules(
        "So 5000 rupees a month, noted.", latest="we lose 5000 rupees a month"
    )
    assert "R-HONEST-01" not in hard_rules("Roughly how much, a few thousand or lakhs?")


# 5. IDs, names, money ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Please share your national ID number.",
        "Send me your ID card photo.",
        "Apna CNIC bhej dein.",
        "Share your driving license number.",
        "May I have your Aadhaar?",
    ],
)
def test_asking_for_ids_is_hard(reply):
    assert hard_rules(reply) & {"R-PRIV-03", "R-PAY-02"}


@pytest.mark.parametrize(
    "reply",
    [
        "Please send the cashier's name and phone number.",
        "What is your staff member's name?",
        "Share the names of your customers.",
    ],
)
def test_asking_for_staff_or_customer_details_is_hard(reply):
    assert "R-PRIV-04" in hard_rules(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Please share the exact revenue figure.",
        "What is your bank balance?",
        "Send me your bank statement.",
        "What is Ali's salary?",
    ],
)
def test_asking_for_revenue_balances_or_salaries_is_hard(reply):
    assert "R-ASK-06" in hard_rules(reply)


def test_rough_scale_and_refusals_are_fine():
    assert hard_rules("Roughly how much, a few thousand or lakhs?") == set()
    assert hard_rules("Please don't send your ID card. I don't need it.") == set()
    assert hard_rules("Who is the cashier, the owner or a hired person?") == set()


# 6. Arabic and Urdu script -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "أرسل لي رقم بطاقتك",
        "شارك كلمة المرور من فضلك",
        "اپنا کارڈ نمبر بھیجیں",
        "اپنا پاس ورڈ بتائیں",
        "أرسل لي صورة بطاقة الهوية",
    ],
)
def test_arabic_and_urdu_asks_for_cards_and_ids_are_hard(reply):
    assert hard_rules(reply) & {"R-PAY-02", "R-PRIV-03"}


@pytest.mark.parametrize(
    "reply",
    [
        "تم استلام الدفع",
        "استلمنا المبلغ",
        "ادائیگی موصول ہو گئی",
        "ہمیں ادائیگی مل گئی",
        "Thanks for the payment.",
    ],
)
def test_arabic_and_urdu_payment_received_is_hard(reply):
    assert "R-PAY-05" in hard_rules(reply)
    assert "R-PAY-05" not in hard_rules(reply, payment_confirmed=True)


def test_arabic_refusal_and_questions_about_payment_are_fine():
    assert "R-PAY-02" not in hard_rules("لا ترسل رقم بطاقتك هنا")
    assert "R-PAY-05" not in hard_rules("Has the payment been received?")
    assert "R-PAY-05" not in hard_rules("Thanks for the payment screenshot. The team will confirm.")


# 7. advice -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "You should charge 17% sales tax on that.",
        "You can legally fire him.",
        "Take a loan from HBL.",
        "Take two tablets of 500 mg.",
        "Ali is stealing from you.",
        "Your cashier is stealing.",
    ],
)
def test_advice_in_the_reply_is_hard(reply):
    assert "R-ADV-01" in hard_rules(reply)


def test_politics_religion_competitors_are_hard():
    assert "R-ADV-04" in hard_rules("The government is corrupt.")
    assert "R-ADV-04" in hard_rules("Zoho is better than QuickBooks".replace("Zoho is", "It is"))
    assert "R-ADV-05" in hard_rules("Here is a joke for you.")


def test_noting_a_tax_problem_is_not_advice():
    assert "R-ADV-01" not in hard_rules("Noted, tax filing takes you a long time. Who does it?")
    assert "R-ADV-01" not in hard_rules(
        "I can't give tax advice. A qualified accountant is the right person."
    )


# 8. disclosure, Meta, never-say, emoji, formatting, spelling -----------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "ہیلو، میں pi ہوں، Workzap کی طرف سے ایک مصنوعی ذہانت۔",
        "مرحباً، أنا pi، ذكاء اصطناعي من Workzap.",
        "مرحباً، أنا pi، الذكاء الإصطناعي من Workzap.",
        "Hi, main pi hoon, Workzap ka AI.",
        "हैलो, मैं pi हूँ, Workzap का एआई।",
    ],
)
def test_the_first_message_discloses_in_every_language(reply):
    assert "R-DISC-01" not in hard_rules(reply, history=[])


def test_the_first_message_that_talks_about_ai_but_not_itself_is_not_a_disclosure():
    assert "R-DISC-01" in hard_rules("Workzap sells AI tools for shops.", history=[])
    assert "R-DISC-01" in hard_rules("السلام علیکم، آپ کا کاروبار کیسا ہے؟", history=[])


def test_free_talk_about_meta_policy_is_hard_but_the_one_line_is_fine():
    assert "R-META-01" in hard_rules("WhatsApp can ban your number if you message too many people.")
    assert "R-META-01" in hard_rules("Meta's policy needs an opt-in first.")
    assert "R-META-01" not in hard_rules(
        "I'm made by Workzap and I chat through WhatsApp's business platform; Meta doesn't run me."
    )
    assert "R-META-01" not in hard_rules(
        "Noted, your number got banned on WhatsApp. When did it start?",
        latest="my whatsapp number got banned",
    )


def test_tool_and_prompt_are_internal_unless_they_said_them():
    assert "R-VOICE-06" in hard_rules("Which tool do you use?")
    assert "R-VOICE-06" in hard_rules("I read the prompt.")
    assert "R-VOICE-06" not in hard_rules(
        "Which tool do you use now?", latest="we use a tool called Tally"
    )


def test_emoji_is_limited_to_a_neutral_one_after_theirs():
    assert "R-VOICE-08" not in rules("Noted 😊", latest="stock khatam 😊")
    assert "R-VOICE-08" in rules("Noted 😂", latest="stock khatam 😂")
    assert "R-VOICE-08" in rules("Noted 😭", latest="stock khatam 😭")
    assert "R-VOICE-08" in rules("Noted 🔥", latest="stock khatam 😊")
    assert "R-VOICE-08" in rules("Noted 😊😊", latest="stock khatam 😊")
    assert c.repair("Noted 😭", ctx(latest="stock khatam 😭")) == "Noted"
    assert c.repair("Noted 😊", ctx(latest="stock khatam 😭")) == "Noted 😊"


def test_bullets_and_single_asterisk_bold_outside_summaries():
    assert "R-VOICE-09" in rules(
        "Noted:\n• Stock\n• Cash\nWhich first?",
        state="S2_CLARIFYING",
        latest="stock and cash and many other things are wrong here",
    )
    assert "R-VOICE-09" in rules("Noted *stock*. Which shop?", state="S2_CLARIFYING")
    assert "R-VOICE-09" not in rules(
        "Thanks. I've noted it: *Stock runs out*. Anything else?", state="S3_NOTED"
    )
    assert "R-VOICE-09" in rules("• Only one bullet\nWhich shop?", state="S4_SORTED_SUMMARY")


def test_made_up_examples_are_labelled_illustrative():
    assert "R-ILLU-01" in rules("For example, a shop with three branches. Which is yours?")
    assert "R-ILLU-01" not in rules("Illustrative: a shop with three branches. Which is yours?")
    assert "R-ILLU-01" not in rules("I can imagine that is tiring. Which shop?")
    assert not c.hard(c.lint("For example, a shop with three branches.", ctx()))


def test_british_spelling_is_a_soft_check():
    found = c.lint("Noted, the color of the labels. Which shop?", ctx())
    assert [v.rule for v in found] == ["R-VOICE-14"] and not c.hard(found)
    assert "R-VOICE-14" not in rules("Noted, the colour of the labels. Which organisation?")
    assert "R-VOICE-14" not in rules(
        "Noted, the color of the labels. Which shop?", latest="the color is wrong"
    )


# 9. flattery -----------------------------------------------------------------------------------------
def test_flattery_is_soft():
    found = c.lint("Great idea, you're clearly smart. Which shop?", ctx())
    assert "R-SELL-03" in {v.rule for v in found} and not c.hard(found)
    assert "R-SELL-03" in {v.rule for v in c.hard(c.lint("Don't wait, prices will go up.", ctx()))}


# the spec's own pi lines ----------------------------------------------------------------------------
def pack_lines():
    for path in sorted(PACKS.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        history = [
            {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. Tell me what's going wrong."}
        ]
        latest = ""
        for turn in pack.get("exchange", []):
            if turn["role"].lower() == "pi":
                yield pack["key"], turn["text"], latest, list(history)
                history.append({"role": "ai", "text": turn["text"]})
            else:
                latest = turn["text"]
                history.append({"role": "customer", "text": latest})


def test_no_pi_line_of_any_industry_pack_fails_a_hard_rule():
    seen = 0
    for key, text, latest, history in pack_lines():
        seen += 1
        context = ctx(latest=latest, history=history[:-1])
        assert c.hard(c.lint(text, context)) == [], (key, text)
    assert seen > 400


def test_the_golden_scripted_replies_still_pass():
    g4 = "Once I've noted what's going wrong, Workzap can prepare a solution document for it, if you want one. For now, what would the app need to fix first?"
    assert c.hard(c.lint(g4, ctx(latest="can you make an app for this?"))) == []
    g9 = "Kharcha is par depend karta hai ke kya banaya jaye. Woh quote par likha hota hai, aap ke faisle se pehle, aur quote muft hai, koi charge nahi."
    assert c.hard(c.lint(g9, ctx(latest="bhai ye batao kitna kharcha hoga?"))) == []


def test_an_arabic_reply_never_keeps_the_english_word_noted() -> None:
    """Production chat 2026-10-24: 'لقد noted: ...' went out in an Arabic reply."""
    from app.modules.pi import constitution

    bad = constitution.lint("لقد noted: نفس البنت الي في الصورة. هل هناك شيء آخر؟", {})
    assert any(v.rule == "R-LANG-02" for v in bad)
    good = constitution.lint("سجلت ذلك: نفس البنت الي في الصورة. هل هناك شيء آخر؟", {})
    assert not any(v.rule == "R-LANG-02" for v in good)
