# ruff: noqa: E501  (Roman Urdu lines read better unbroken)
"""Live chat 4 (owner, 2026-10-26 16:25-16:40 PKT, running the live-3 fixes): what slipped through."""

import pytest

from app.modules.pi import constitution, safety

H = [{"role": "ai", "text": "x"}]


def lint(reply, said, earlier=(), state="S3_NOTED", language="roman_ur"):
    history = H + [{"role": "customer", "text": e} for e in earlier]
    context = {
        "pi_mode": "brain",
        "flow": {"state": state},
        "reply_language": language,
        "history": history,
        "latest_customer_message": said,
    }
    return {v.rule for v in constitution.lint(reply, context)}, context


# --- 1. the veterinary and medical advice gate -------------------------------------------------


@pytest.mark.parametrize(
    "said",
    [
        "meri bhens beemar hai kya dawai doon?",
        "bhens beemar hai dawai batao",
        "meri bhains bimar hai kaun si dawai den",
        "gai bimaar hai konsa injection lagaun",
        "bakri ko bukhar hai ilaj bata do",
        "murghiyan bemar hain kya dawa dun",
        "what medicine should I give my sick cow?",
        "my goat has a fever, which injection?",
        "بھینس بیمار ہے کیا دوا دوں؟",
        "भैंस बीमार है कौन सी दवा दूं?",
        "البقرة مريضة ماذا أعطيها من دواء؟",
        "ma vache est malade, quel médicament donner ?",
        "mi vaca está enferma, ¿qué medicina le doy?",
        "گاو من بیمار است چه دارویی بدهم؟",
    ],
)
def test_a_sick_animal_and_a_medicine_is_veterinary_advice_in_any_order_and_spelling(said):
    assert safety.advice_asked(said) is safety.Advice.VETERINARY, said


@pytest.mark.parametrize(
    "said",
    [
        "mere bachay ko bukhar hai kya dawai dun?",
        "my child has a fever, how much dose of paracetamol?",
        "أنا مريض ماذا آخذ من دواء؟",
    ],
)
def test_a_sick_person_and_a_medicine_is_medical_advice(said):
    assert safety.advice_asked(said) is safety.Advice.MEDICAL, said


@pytest.mark.parametrize(
    "said",
    [
        "meri bhainsain bimar rehti hain, doodh kam hai",
        "dawai ki sales kam hain",
        "bukhar ki dawai stock nahi hoti",
        "mera pharmacy business hai aur dawai ka kharcha zyada hai",
        "meri bhains bimar hai, kya karun",
        "roz 30-40 log price poochte hain DM mein",
    ],
)
def test_a_business_that_deals_in_these_things_is_not_stopped(said):
    assert safety.advice_asked(said) is None, said


def test_the_answer_is_the_refusal_line_never_an_idea_or_an_offer():
    line = safety.advice_reply(safety.Advice.VETERINARY, "roman_ur")
    assert "veterinary doctor" in line and "mumkin nahi" in line
    assert "solution document" not in line and "quote" not in line.lower()
    assert "document" not in safety.advice_reply(safety.Advice.VETERINARY, "en").lower()


# --- 2. verdict openers ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "opener",
    [
        "Ye sach mein masla hai.",
        "Ye waqai bara masla hai.",
        "Yeh bilkul asli problem hai.",
        "Ye real masla hai.",
        "That's a real problem.",
        "This is really a big problem.",
        "یہ واقعی ایک سنگین مسئلہ ہے۔",
        "هذه فعلاً مشكلة كبيرة.",
        "यह सच में एक गंभीर समस्या है।",
        "C'est vraiment un vrai problème.",
        "Es realmente un problema serio.",
        "این واقعاً یک مشکل جدی است.",
    ],
)
def test_a_verdict_opener_is_caught_in_any_wording(opener):
    found, _ = lint(f"{opener} Phir kya hota hai?", "orders nahi aate")
    assert "R-TONE-01" in found, opener


def test_a_plain_noted_line_is_not_a_verdict():
    found, _ = lint("Ye masla hai views ka. Phir kya hota hai?", "orders nahi aate")
    assert "R-TONE-01" not in found


# --- 3. the generic closer in other words ------------------------------------------------------


M3 = "roz 30-40 log price poochte hain DM mein. price bata deta hoon to reply hi nahi aata"


@pytest.mark.parametrize(
    "closer",
    [
        "Aur kya cheez mushkil kar rahi hai?",
        "Aur kya cheez mushkil kar rahi hai",
        "Aur kya masla aa raha hai?",
        "Koi aur dikkat hai?",
    ],
)
def test_the_aur_kya_family_is_a_generic_closer_after_a_detail(closer):
    found, _ = lint(f"Note kar liya, log price puchte hain. {closer}", M3)
    assert "R-ASK-05" in found, closer


# --- 4. a sentence that only says again what they said: caught, and taken out when it survives ---


def test_the_restating_sentence_is_caught_and_repaired_away():
    said = "mera online kapron ka brand hai Lahore mein, reels par views bohat aate hain lekin orders nahi aate"
    reply = "Reels views aa rahe hain, orders nahi aa rahe. Instagram ya WhatsApp mein zyada kahan hota hai?"
    found, context = lint(reply, said)
    assert "R-ECHO-04" in found
    assert constitution.repair(reply, context) == "Instagram ya WhatsApp mein zyada kahan hota hai?"


def test_a_soft_slip_that_survives_the_rewrite_is_repaired_in_place():
    said = "customers kam hain"
    for reply, expected in (
        (
            "Ye sach mein masla hai. Note kar liya, customers kam hain. Ye kab se hai?",
            "Note kar liya, customers kam hain. Ye kab se hai?",
        ),
        (
            "Theek hai. Note kar liya, customers kam hain. Ye kab se hai?",
            "Note kar liya, customers kam hain. Ye kab se hai?",
        ),
        (
            "Aap sahi keh rahe hain. Note kar liya, customers kam hain. Ye kab se hai?",
            "Note kar liya, customers kam hain. Ye kab se hai?",
        ),
        (
            "Thanks, note kar liya hai: customers kam hain. Ye kab se hai?",
            "Note kar liya hai: customers kam hain. Ye kab se hai?",
        ),
    ):
        _, context = lint(reply, said)
        assert constitution.repair(reply, context) == expected, reply


def test_repair_never_empties_a_reply():
    _, context = lint("Ye sach mein masla hai.", "orders nahi aate")
    assert constitution.repair("Ye sach mein masla hai.", context).strip()


# --- 5. a question the person already answered ---------------------------------------------------


def test_how_often_after_roz_is_sent_back_and_the_question_is_dropped_when_a_statement_stays():
    reply = "Note kar liya, roz log price poochte hain. Ye kitni dafa hoti hai — roz, haftay mein, ya kabhi kabhi?"
    found, context = lint(reply, M3)
    assert "R-ASK-03" in found
    assert constitution.repair(reply, context) == "Note kar liya, roz log price poochte hain."


def test_cash_side_or_stock_side_after_naming_both_is_sent_back():
    said = "raat ko stock kam nikalta hai, cash bhi kabhi kam hota hai"
    found, _ = lint("Note kar liya. Masla cash side ya stock side?", said)
    assert "R-ASK-03" in found


def test_a_comparison_or_a_new_question_is_not_an_answered_one():
    found, _ = lint(
        "Instagram ya WhatsApp mein zyada drop-off kahan hota hai?",
        "instagram aur whatsapp par bechta hoon",
    )
    assert "R-ASK-03" not in found
    found, _ = lint("Note kar liya. Ye kab se ho raha hai?", M3)
    assert "R-ASK-03" not in found


# --- 6. English function words in a Roman Urdu reply -------------------------------------------


def test_an_english_function_word_in_a_roman_urdu_reply_is_sent_back():
    reply = (
        "Kharcha is par depend karta hai. Quote mein sab likha hota hai before aap decide karein."
    )
    found, _ = lint(reply, "bhai ye batao kitna kharcha hoga?")
    assert "R-LANG-02" in found
    found, _ = lint(reply, "bhai ye batao kitna kharcha hoga?", language="en")
    assert "R-LANG-02" not in found
