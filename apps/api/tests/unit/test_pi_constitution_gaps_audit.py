# ruff: noqa: E501  (one case per line reads better than wrapped strings)
"""Audit fixes for constitution_gaps.py: false positives found by an independent audit, the rules that
were demoted or narrowed, the rule-id split, and a test for every exemption that used to be untested."""

import pytest

from app.modules.pi import constitution as c
from app.modules.pi import constitution_gaps as gaps

AI_TURN = {"role": "ai", "text": "Hi, I'm pi, an AI from Workzap. What is going wrong?"}


def ctx(latest, convo=(), **extra):
    history = [AI_TURN]
    for who, text in convo:
        history.append({"role": "customer" if who == "c" else "ai", "text": text})
    return {"latest_customer_message": latest, "history": history, **extra}


def broke(reply, context):
    return {f[0] for f in gaps.check(reply, context)}


def state(name):
    return {"flow": {"state": name}}


# ---- R-SOL-09: quantities and units are not medicine; ideas about perfume, coffee, hardware pass ----
UNIT_IDEAS = [
    "Give customers a 5 ml sample of the new perfume. Which shop sells the most perfume?",
    "Try the 250 ml bottle as the default size for the juice. Is it every shop, or only some?",
    "Start with a 500 ml iced coffee offer on Mondays. Which shop is busiest on Mondays?",
    "Offer a 10 ml travel perfume at the till. Is it every shop, or only some?",
    "Sell the 1 litre juice pack next to the cold drinks. Which shop has the fridge?",
    "Give regulars a free 30 ml oud sample on their third visit. Which shop has most regulars?",
    "Try a 200 mg caffeine-free blend as the evening coffee. Is it weekdays, or weekends?",
    "Start a 750 ml cold brew bottle for office orders. Which shop is near offices?",
    "Give every order over 2000 a 5 ml attar vial. Which shop has the larger orders?",
    "Try 100 ml tester bottles on the perfume shelf. Is it the main shop, or a smaller one?",
    "Start weighing the 5 kg nails pack before it goes on the shelf. Which shop has the scale?",
    "Stock the 20 litre paint tin near the brushes. Is it every shop, or some?",
    "Offer 250 g screw packs at the counter. Which shop sells screws?",
    "Bundle the 10 mm drill bits with the drill. Is it a few items, or many?",
    "Give contractors a printed price list for the 50 kg cement bags. Which shop serves contractors?",
    "Count the paracetamol packs on the shelf each evening. Which shop has the most packs?",
    "Keep a register of antibiotics sold each day, as the law already asks. Which shop keeps it?",
    "Label each 100 mg tablet strip with its expiry date. Is it every shop, or some?",
    "Sort the insulin pens in the fridge by expiry date. Which shop has the fridge?",
    "Give the customer a printed receipt for each prescription filled. Which shop prints it?",
    "Start a shelf card for the 500 mg vitamin packs. Which shop sells vitamins?",
    "Try a 60 ml hand sanitiser at the till. Is it every shop, or some?",
    "Give walk-in customers a 15 ml lotion sample. Which shop has walk-ins?",
    "Start a 1.5 litre water bottle bundle for families. Which shop has families?",
    "Offer the 330 ml can as a single, and the 6 pack as a deal. Which shop sells cans?",
    "Try a 100 g trial pack of the new tea. Is it weekdays, or weekends?",
    "Give new buyers a 250 ml sample of the floor cleaner. Which shop has new buyers?",
    "Stock the 5 ml super glue tubes by the till. Is it every shop, or some?",
    "Start a 2 litre refill price for the shampoo. Which shop has the refill station?",
    "Keep the 30 ml tester of each perfume behind the counter. Which shop has the counter?",
    "Try a 3 mg per sachet saffron pack as the gift option. Is it a few items, or many?",
    "Offer a 20 ml fragrance oil in the gift box. Is it every shop, or some?",
]


@pytest.mark.parametrize("reply", UNIT_IDEAS)
def test_quantities_and_units_are_not_regulated_advice(reply):
    assert "R-SOL-09" not in broke(reply, ctx("sales are slow")), reply
    assert "R-SOL-09" not in {v.rule for v in c.lint(reply, ctx("sales are slow"))}, reply


@pytest.mark.parametrize(
    "reply",
    [
        "File each GST invoice in a folder by month. Which shop files them?",
        "Start a vaccination calendar for each calf on a wall chart. Which farm?",
        "Apply a 10% discount on fertiliser bags bought in pairs. Which shop?",
        "Get the interest rate in writing from each supplier. Which one first?",
        "Reduce fertiliser waste by weighing each bag at the door. Which shop?",
        "Use a sheet to log the pesticide bought each week. Which shop?",
        "Khaad ka hisaab roz likh dein. Kaunsi dukaan?",
        "کھاد کا حساب روز لکھ دیں۔ کون سی دکان؟",
        "खाद का हिसाब रोज़ लिख दें। कौन सी दुकान?",
    ],
)
def test_other_domain_words_in_operational_ideas_pass(reply):
    assert "R-SOL-09" not in broke(reply, ctx("sales are slow")), reply


# ---- R-PROM-03 is soft and ignores generic seasonality --------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Demand will increase before Eid, so shops usually plan ahead. Which shop is busiest?",
        "Sales will rise and fall through the year in most shops. Which shop is yours?",
        "Business will usually slow down in summer. Which shop feels it?",
        "Har saal Eid se pehle sales barh jati hain. Kaunsi dukaan?",
        "عید سے پہلے فروخت بڑھے گی۔ کون سی دکان؟",
        "المبيعات ستزداد قبل العيد عادة. أي فرع؟",
        "ईद से पहले बिक्री बढ़ेगी। कौन सी दुकान?",
    ],
)
def test_generic_seasonality_is_not_a_forecast(reply):
    assert "R-PROM-03" not in broke(reply, ctx("sales are slow")), reply


def test_forecasts_are_soft():
    found = [
        f
        for f in gaps.check("Your sales will drop next month. Which shop?", ctx("stock runs out"))
        if f[0] == "R-PROM-03"
    ]
    assert found
    assert not any(f[2] for f in found)


def test_forecast_the_person_already_said_is_exempt():
    context = ctx("our sales will drop next month, I am sure")
    assert "R-PROM-03" not in broke("Sales will drop next month, you say. Which shop?", context)
    assert "R-PROM-03" in broke(
        "Sales will drop next month, I think. Which shop?", ctx("stock runs out")
    )


def test_a_conditional_forecast_is_exempt():
    assert "R-PROM-03" not in broke(
        "Your sales will drop if stock keeps running out. Which shop?", ctx("stock runs out")
    )
    assert "R-PROM-03" in broke("Your sales will drop. Which shop?", ctx("stock runs out"))


# ---- R-PROM-02 flags deciding, not recommending ---------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "My recommendation is to count the slips first. Which shop?",
        "My suggestion is to start with stock. Which one first?",
        "I'd suggest looking at cash before staff. Which shop?",
        "Mera mashwara hai ke pehle stock dekhein. Kaunsi dukaan?",
        "میرا مشورہ ہے کہ پہلے اسٹاک دیکھیں۔ کون سی دکان؟",
        "نصيحتي أن نبدأ بالمخزون. أي فرع؟",
        "मेरी सलाह है कि पहले स्टॉक देखें। कौन सी दुकान?",
    ],
)
def test_a_recommendation_is_allowed(reply):
    assert "R-PROM-02" not in broke(reply, ctx("three things are wrong")), reply


# ---- X5 ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        ("I'm here with you. Which shop is hit hardest?", "I'm going bankrupt"),
        ("That sounds hard. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Sorry to hear that. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Thank you for telling me. Which shop is hit hardest?", "I'm going bankrupt"),
        ("Main aap ke saath hoon. Kaunsi dukaan sab se zyada mutasir hai?", "dewaliya ho jaunga"),
        ("سن کر افسوس ہوا۔ کون سی دکان زیادہ متاثر ہے؟", "میں دیوالیہ ہونے والا ہوں"),
        ("أنا هنا معك. أي فرع الأكثر تأثراً؟", "سأفلس قريباً"),
        ("मैं आपके साथ हूँ। कौन सी दुकान सबसे ज़्यादा प्रभावित है?", "मैं दिवालिया हो जाऊँगा"),
    ],
)
def test_ordinary_empathy_is_an_acknowledgement(reply, latest):
    assert "X5" not in broke(reply, ctx(latest)), reply


@pytest.mark.parametrize(
    "reply",
    [
        "That's a lot to carry. I won't tell you whether to borrow or invest. Which shop is hit hardest?",
        "That sounds hard. I can't advise on whether to borrow. Which shop is hit hardest?",
        "I'm sorry. I'm not going to tell you to invest or borrow. Which shop is hit hardest?",
    ],
)
def test_declining_to_advise_is_not_advice(reply):
    assert "X5" not in broke(reply, ctx("I'm going bankrupt")), reply


@pytest.mark.parametrize(
    "reply",
    [
        "That's a lot to carry. You should borrow money from a cousin. Which shop?",
        "That's a lot to carry. Invest in a second shop. Which shop?",
    ],
)
def test_advice_to_borrow_or_invest_is_flagged(reply):
    assert "X5" in broke(reply, ctx("I'm going bankrupt")), reply


def test_x5_stays_quiet_in_an_emergency_state():
    reply = "Noted: going bankrupt. Which shop is hit hardest?"
    assert "X5" in broke(reply, ctx("I'm going bankrupt"))
    assert "X5" not in broke(reply, ctx("I'm going bankrupt", **state("X_EMERGENCY")))


# ---- R-CANT-01 / R-CANT-02 -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        (
            "Thank you. I can't confirm payment myself, staff confirm it. Which shop is it?",
            "did my payment go through",
        ),
        (
            "Shukriya. Payment main khud confirm nahi kar sakta, staff karega. Kaunsi dukaan?",
            "meri payment ho gayi",
        ),
        (
            "شکریہ۔ میں ادائیگی خود کنفرم نہیں کر سکتا، عملہ کرے گا۔ کون سی دکان؟",
            "میری ادائیگی ہو گئی",
        ),
        ("شكراً. لا أستطيع تأكيد الدفع بنفسي، الموظفون يؤكدونه. أي فرع؟", "هل تم الدفع"),
        ("धन्यवाद। मैं भुगतान खुद पुष्टि नहीं कर सकता, स्टाफ करेगा। कौन सी दुकान?", "मेरा भुगतान हो गया"),
        (
            "I can't confirm payment myself. Staff confirm it, then I tell you.",
            "did my payment go through",
        ),
    ],
)
def test_a_limit_after_a_pleasantry_or_as_the_first_sentence_is_fine(reply, latest):
    found = broke(reply, ctx(latest))
    assert "R-CANT-01" not in found, reply
    assert "R-CANT-02" not in found, reply


def test_cant_02_is_exempt_with_emergency_numbers_or_a_next_step():
    assert "R-CANT-02" not in broke(
        "I can't help with that. Please call 1122 now.", ctx("my shop is on fire")
    )
    assert "R-CANT-02" not in broke(
        "I can't confirm that. Staff will confirm it.", ctx("is it paid")
    )
    assert "R-CANT-02" in broke("I can't confirm that.", ctx("is it paid"))


def test_a_refusal_that_is_a_question_or_a_conditional_is_not_a_refusal():
    sentences_before = "Noted. We looked at the stock together. "
    assert broke(sentences_before + "I can't give tax advice. Which shop?", ctx("tax")) >= {
        "R-CANT-01"
    }
    assert "R-CANT-01" not in broke(
        sentences_before + "Can I tell you why I can't give tax advice? Which shop?", ctx("tax")
    )
    assert "R-CANT-01" not in broke(
        sentences_before + "If I can't help with that, I will say so. Which shop?", ctx("tax")
    )
    assert "R-CANT-02" not in broke("Can I explain why I can't give tax advice?", ctx("tax"))
    assert "R-CANT-02" not in broke("If I can't help, I will say so.", ctx("tax"))


# ---- R-ANS-02 and the AI-disclosure non-negotiable --------------------------------------------------
HUMAN_ASKED = [
    ("Are you human?", "I'm an AI from Workzap, not a person. Which shop is it?"),
    ("Are you human?", "I'm pi, an AI. Which shop is it?"),
    ("kya aap insaan hain?", "Main AI hoon, Workzap ka. Kaunsi dukaan?"),
    ("کیا آپ انسان ہیں؟", "میں اے آئی ہوں، Workzap کی طرف سے۔ کون سی دکان؟"),
    ("هل أنت إنسان؟", "أنا ذكاء اصطناعي من Workzap. أي فرع؟"),
    ("क्या आप इंसान हैं?", "मैं एक एआई हूँ, Workzap का। कौन सी दुकान?"),
    ("Pouvez-vous me dire si vous êtes humain ?", "Je suis une IA de Workzap. Quel magasin ?"),
]


@pytest.mark.parametrize(("asked", "reply"), HUMAN_ASKED)
def test_i_am_an_ai_answers_are_you_human(asked, reply):
    context = ctx(asked)
    assert "R-ANS-02" not in broke(reply, context), reply
    assert "R-ANS-02" not in {v.rule for v in c.lint(reply, context)}, reply


def test_the_ai_disclosure_rule_is_never_blocked_by_ans_02():
    for asked, reply in HUMAN_ASKED:
        context = ctx(asked)
        assert not any(v.rule in ("R-ANS-02", "R-DISC-02") for v in c.lint(reply, context)), (
            asked,
            reply,
        )


def test_a_workzap_statement_answers_can_you_fix_this():
    assert "R-ANS-02" not in broke(
        "Workzap handles stock problems like this. Which shop is it?", ctx("Can you fix this?")
    )
    assert "R-ANS-02" in broke("Stock problems are common.", ctx("Can you fix this?"))


@pytest.mark.parametrize(
    ("reply", "latest"),
    [
        ("Of course. Which shop?", "Can you help with stock?"),
        ("They are available. Which shop?", "Are they open on Friday?"),
        ("Kar sakte hain. Kaunsi dukaan?", "kya aap stock ka masla theek kar sakte hain?"),
        ("ہو سکتا ہے۔ کون سی دکان؟", "کیا یہ ہو سکتا ہے؟"),
        ("कर सकते हैं। कौन सी दुकान?", "क्या आप स्टॉक की समस्या हल कर सकते हैं?"),
    ],
)
def test_phrase_answers_count_as_yes_or_no(reply, latest):
    assert "R-ANS-02" not in broke(reply, ctx(latest)), reply


# ---- R-VOICE-11 -------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "reply",
    [
        "Item 1 is the quote, Item 2 is the terms. Which shop?",
        "Unit 1 has the freezer. Which shop?",
        "Customer 2 asked for a refund. Which shop?",
        "Step 2 is counting the till. Which shop?",
        "Point 3 is about delivery. Which shop?",
        "Option A is weekly, option B is monthly. Which shop?",
        "Branch 2 is not named yet, so which branch is it?",
    ],
)
def test_structural_labels_are_not_invented_names(reply):
    assert "R-VOICE-11" not in broke(reply, ctx("stock runs out")), reply


def test_a_location_label_is_still_caught_and_a_document_is_exempt():
    assert "R-VOICE-11" in broke("Stock runs out at Location 2. Which shop?", ctx("stock runs out"))
    assert "R-VOICE-11" not in broke(
        "Quote line: Location 2 delivery. Which shop?", ctx("stock runs out", **state("S8_REVIEW"))
    )
    # "Branch 2" is only a label where the owner talks about branches
    assert "R-VOICE-11" in broke("Branch B is late. Which one?", ctx("the Gulberg branch is late"))
    assert "R-VOICE-11" not in broke("Branch B is late. Which one?", ctx("the second shop is late"))


# ---- the rule-id split --------------------------------------------------------------------------------
def test_the_skipped_question_check_has_its_own_id_and_the_old_closer_keeps_r_ask_05():
    asked = (("a", "How many staff work in the evening shift?"),)
    reasked = {
        v.rule for v in c.lint("How many staff are on the evening shift?", ctx("skip", asked))
    }
    assert "R-ASK-05R" in reasked and "R-ASK-05" not in reasked
    closer = c.lint(
        "Noted: stock runs out at the Gulberg shop every Friday. Anything else?",
        ctx(
            "stock runs out at the Gulberg shop every Friday and it costs us a lot",
            **state("S1_LISTENING"),
        ),
    )
    assert "R-ASK-05" in {v.rule for v in closer}
    assert "R-ASK-05R" not in {v.rule for v in closer}


# ---- exemptions that used to be untested -------------------------------------------------------------
def test_regulated_advice_the_person_already_said_is_exempt():
    said = ctx("the agronomist told us to apply urea twice")
    assert "R-SOL-09" not in broke("So you apply urea twice. Which field?", said)
    assert "R-SOL-09" in broke("Apply urea twice. Which field?", ctx("the crop is weak"))


def test_the_comfort_line_is_not_pressure():
    hesitant = ctx("I'd rather not say the amount")
    assert "R-PRIV-08" not in broke(
        "Please just tell me what you're comfortable sharing. Which shop?", hesitant
    )
    assert "R-PRIV-08" in broke("Please just tell me the amount. Which shop?", hesitant)


def test_brief_writer_limit_is_five_words_and_choice_questions_are_closed():
    brief = (("c", "stock"), ("a", "Noted: stock. Which part of it?"), ("c", "yes"))
    longer = (("c", "mostly the second shop at the main road"), ("a", "Noted. Which part of it?"))
    assert "R-ASK-04" in broke("How does that happen in your shops?", ctx("mostly", brief))
    assert "R-ASK-04" not in broke(
        "How does that happen in your shops?", ctx("mostly the second shop at the road", longer)
    )
    assert "R-ASK-04" not in broke("How does it go, daily or weekly?", ctx("mostly", brief))
    assert "R-ASK-04" not in broke("How does that happen in your shops?", ctx("mostly", longer))


def test_noted_twice_needs_most_of_the_words_to_repeat():
    before = (("a", "Noted: best-sellers running out badly. Which shop?"),)
    assert "R-ECHO-01" in broke(
        "Noted: best sellers running low. Is it weekly?", ctx("it is weekly", before)
    )
    assert "R-ECHO-01" not in broke(
        "Noted: best selling mugs breaking. Is it weekly?", ctx("it is weekly", before)
    )
    assert "R-ECHO-01" not in broke(
        "Noted: sellers moving slowly. Is it weekly?", ctx("it is weekly", before)
    )


def test_bullets_that_only_partly_repeat_earlier_messages_pass():
    earlier = (
        ("c", "cashiers come late on weekends"),
        ("a", "Noted."),
        ("c", "daily cash does not match the till"),
        ("a", "Noted."),
    )
    mixed = "• Cashiers come late on weekends at the airport shop\n• Daily cash does not match at the airport till\nIs anything missing?"
    assert "R-ECHO-02" not in broke(mixed, ctx("stock runs out", earlier, **state("S3_NOTED")))
    plain = "• Cashiers come late on weekends\n• Daily cash does not match the till\nIs anything missing?"
    assert "R-ECHO-02" in broke(plain, ctx("stock runs out", earlier, **state("S3_NOTED")))


def test_a_confirming_question_is_not_a_re_ask():
    said = ctx(
        "stock runs out at the Gulberg shop every Friday and that is correct", (("c", "ok"),)
    )
    assert "R-ASK-03" not in broke(
        "Stock runs out at the Gulberg shop every Friday, correct?", said
    )
    assert "R-ASK-03" in broke("Does stock run out at the Gulberg shop every Friday?", said)


def test_advice_the_person_said_first_is_exempt_even_when_phrased_as_an_instruction():
    said = ctx("the agronomist told us to apply urea twice")
    assert "R-SOL-09" not in broke("Apply urea twice, as the agronomist said. Which field?", said)
    assert "R-SOL-09" in broke("Apply urea twice, as I said. Which field?", ctx("the crop is weak"))


def test_a_sentence_that_declines_to_advise_on_a_loan_is_not_advice():
    distress = ctx("I'm going bankrupt")
    assert "X5" not in broke(
        "That sounds hard. I can't tell you whether to take a loan. Which shop?", distress
    )
    assert "X5" in broke("That sounds hard. Take a loan from the bank. Which shop?", distress)


def test_a_decision_the_person_quoted_is_not_pi_deciding():
    said = ctx("the consultant said you must fire the manager")
    assert "R-PROM-02" not in broke(
        "Noted: the consultant said you must fire the manager. Which shop?", said
    )
    assert "R-PROM-02" in broke(
        "You must fire the manager. Which shop?", ctx("the manager is slow")
    )
