"""specrules2: G11 noAssumedIndustry hook (SOFT), PS-7 owner-said links, graph guesses for PS-4.

HONEST LIMIT: one author wrote every sentence; Hindi, Urdu and Arabic forms are not
native-reviewed. The graph lexicon has no Hindi connectives, so a Hindi owner-stated link stays
pi_inferred (safe)."""

import pytest

from app.modules.pi import spec_rules2 as sr
from app.modules.pi.service_conversation import part18_problem

# (language, reply, owner said) -> must be flagged while the trade is unconfirmed
BAD = [
    ("en", "AC units ya spare parts?", ""),
    ("en", "Do you sell restaurant equipment or kitchen tools?", ""),
    ("en", "How many patients do you see in a day?", "things are slow"),
    ("en", "Are the delays on the trucks or at the warehouse?", "things are late"),
    ("roman_ur", "Aap AC bechte hain ya spare parts?", ""),
    ("roman_ur", "Kya aap ki bakery mein cake kam bikte hain?", "bikri kam hai"),
    ("ur", "آپ کے ریسٹورنٹ میں کتنے ویٹر ہیں؟", "عملہ کم ہے"),
    ("ur", "آپ کا کلینک کتنے بجے کھلتا ہے؟", "کام کم ہے"),
    ("ar", "هل لديك مطعم أم مقهى؟", ""),
    ("hi", "आपके रेस्टोरेंट में कितने वेटर हैं?", "स्टाफ कम है"),
    ("hi", "आप एसी बेचते हैं या स्पेयर पार्ट्स?", ""),
]
# normal replies that must pass (zero false positives)
GOOD = [
    ("en", "Ye maal kis cheez ka hai?", ""),
    ("en", "I'm an AI. What does your business sell or do?", ""),
    ("en", "That sounds frustrating. How often does it happen in a week?", "orders go wrong"),
    ("en", "Noted: late payments. What is the biggest part of that problem?", "customers pay late"),
    ("roman_ur", "Aap ka kaam kya hai, aur kis cheez mein dikkat aa rahi hai?", ""),
    ("roman_ur", "Samajh gaya. Yeh kitni baar hota hai?", "maal late aata hai"),
    ("ur", "آپ کا کاروبار کیا کرتا ہے؟", ""),
    ("ur", "سمجھ گیا۔ یہ کتنی بار ہوتا ہے؟", "ادائیگی میں دیر ہوتی ہے"),
    ("ar", "ما هو نشاط عملك؟", ""),
    ("ar", "فهمت. كم مرة يحدث هذا في الأسبوع؟", "الطلبات تتأخر"),
    ("hi", "आपका काम क्या है?", ""),
    ("hi", "समझ गया। यह हफ्ते में कितनी बार होता है?", "देरी होती है"),
    ("en", "You said you sell AC parts. Which part sells slowest?", "I sell AC parts"),
]


def _ctx(said: str, unconfirmed: bool = True, lang: str = "en") -> dict:
    return {
        "industry_unconfirmed": unconfirmed,
        "latest_customer_message": said,
        "reply_language": lang,
        "history": [],
        "pi_mode": "brain",
    }


@pytest.mark.parametrize("lang,reply,said", BAD)
def test_assumed_trade_is_flagged_before_the_business_is_confirmed(lang, reply, said):
    assert sr.assumed_industry(reply, _ctx(said, lang=lang))


@pytest.mark.parametrize("lang,reply,said", BAD)
def test_confirmed_trade_never_flagged(lang, reply, said):
    assert sr.assumed_industry(reply, _ctx(said, unconfirmed=False, lang=lang)) is None


@pytest.mark.parametrize("lang,reply,said", GOOD)
def test_normal_replies_pass(lang, reply, said):
    assert sr.assumed_industry(reply, _ctx(said, lang=lang)) is None


def test_owner_words_from_earlier_messages_are_theirs():
    ctx = _ctx("what next")
    ctx["history"] = [{"role": "customer", "text": "I run a bakery"}]
    assert sr.assumed_industry("How many cakes does the bakery sell?", ctx) is None


def test_hook_is_in_the_part18_reply_guard():
    reason = part18_problem("AC units ya spare parts?", _ctx(""))
    assert reason and "industry word" in reason
    ctx = _ctx("")
    ctx["history"] = [{"role": "customer", "text": "hello"}, {"role": "pi", "text": "hi"}]
    assert "industry word" not in (part18_problem("What does your business do?", ctx) or "")


def test_junk_context_never_raises():
    assert sr.assumed_industry("AC units", {}) is None
    sr.assumed_industry("AC units", {"industry_unconfirmed": True, "history": [None, 3]})


def _two(a, b):
    return [
        {"id": "A", "title": a, "user_words": [a]},
        {"id": "B", "title": b, "user_words": [b]},
    ]


LINKED = [
    (
        "en",
        _two("customers pay late", "cash is short"),
        "My customers pay late because cash is short",
        ("B", "A"),
    ),
    (
        "en",
        _two("customers pay late", "cash is short"),
        "Cash is short because customers pay late",
        ("A", "B"),
    ),
    (
        "roman_ur",
        _two("customers late paise dete hain", "cash kam hai"),
        "Cash kam hai kyunki customers late paise dete hain",
        ("A", "B"),
    ),
    (
        "roman_ur",
        _two("customers late paise dete hain", "cash kam hai"),
        "Customers late paise dete hain is liye cash kam hai",
        ("A", "B"),
    ),
    (
        "ur",
        _two("گاہک دیر سے ادائیگی کرتے ہیں", "نقد کم ہے"),
        "نقد کم ہے کیونکہ گاہک دیر سے ادائیگی کرتے ہیں",
        ("A", "B"),
    ),
    (
        "ar",
        _two("العملاء يتأخرون في الدفع", "السيولة قليلة"),
        "السيولة قليلة لأن العملاء يتأخرون في الدفع",
        ("A", "B"),
    ),
]
NOT_LINKED = [
    ("en", _two("customers pay late", "cash is short"), "Customers pay late. Cash is short."),
    (
        "en",
        _two("customers pay late", "cash is short"),
        "I think maybe customers pay late because cash is short",
    ),
    ("en", _two("customers pay late", "cash is short"), "Cash is short"),
    (
        "roman_ur",
        _two("customers late paise dete hain", "cash kam hai"),
        "Shayad cash kam hai kyunki customers late paise dete hain",
    ),
    (
        "roman_ur",
        _two("customers late paise dete hain", "cash kam hai"),
        "Customers late paise dete hain. Cash kam hai.",
    ),
    (
        "ur",
        _two("گاہک دیر سے ادائیگی کرتے ہیں", "نقد کم ہے"),
        "گاہک دیر سے ادائیگی کرتے ہیں۔ نقد کم ہے۔",
    ),
    (
        "ar",
        _two("العملاء يتأخرون في الدفع", "السيولة قليلة"),
        "ربما السيولة قليلة لأن العملاء يتأخرون في الدفع",
    ),
    ("hi", _two("ग्राहक देर से पैसे देते हैं", "नकदी कम है"), "नकदी कम है क्योंकि ग्राहक देर से पैसे देते हैं"),
]


@pytest.mark.parametrize("lang,problems,said,pair", LINKED)
def test_owner_stated_link_is_found(lang, problems, said, pair):
    assert pair in sr.owner_said_links(problems, [said], lang)


@pytest.mark.parametrize("lang,problems,said", NOT_LINKED)
def test_guess_or_hedge_or_no_connective_is_not_owner_said(lang, problems, said):
    assert sr.owner_said_links(problems, [said], lang) == []


def test_link_helper_never_raises():
    assert sr.owner_said_links([], ["x"]) == []
    assert sr.owner_said_links([{"id": "A"}, {"id": "B"}], [None, 3]) == []  # type: ignore[list-item]


@pytest.mark.parametrize("lang", ["en", "roman_ur", "ur", "ar", "hi"])
def test_guessed_causes_are_labelled_and_never_owner_said(lang):
    out = sr.guess_causes(
        {"id": "A", "title": "customers pay late", "user_words": ["customers pay late"]},
        ["customers pay late"],
        lang,
    )
    assert out
    for c in out:
        assert c["status"] == "pi_inferred" and not c["evidence"]
        assert sr._GUESS[lang] in c["text"]


def test_owner_given_cause_wins_over_a_guess():
    problem = {"id": "A", "title": "late", "cause_raw": {"text": "cash is short"}}
    assert sr.guess_causes(problem, ["late"], "en") == []


# --- DQ1: "do you know my business?" -> honest not yet + link ------------------------------------
KNOW_ASKS = [
    ("en", "Do you know anything about my business?"),
    ("en", "What do you know about my company?"),
    ("roman_ur", "Aap ko meri business ke baray mein kuch pata hai?"),
    ("roman_ur", "Aap ko mere karobar ke bare me kuch maloom hai?"),
    ("ur", "کیا آپ کو میرے کاروبار کے بارے میں کچھ پتا ہے؟"),
    ("ar", "هل تعرف شيئا عن عملي؟"),
    ("hi", "क्या आपको मेरे बिज़नेस के बारे में कुछ पता है?"),
]
NOT_KNOW_ASKS = [
    "How do I pay?",
    "Can you help with my staff problem?",
    "Aap kaun hain?",
    "ہمارا عملہ کم ہے",
    "ما هي ساعات العمل؟",
    "मेरा स्टाफ कम है",
    "Do you know when it ships?",
]
GOOD_DQ1 = [
    "Not yet. Send me the link to your page or website and I will look.",
    "Abhi nahi. Apni website ka link bhej dein to main dekh loon.",
    "ابھی نہیں۔ اپنے صفحے کا لنک بھیج دیں تو میں دیکھ لوں۔",
    "ليس بعد. أرسل لي رابط موقعك وسأطلع عليه.",
    "अभी नहीं। अपनी वेबसाइट का लिंक भेजें तो मैं देख लूँ।",
]
BAD_DQ1 = [
    "Yes, I know your business well. What is the problem?",
    "I am an AI. Tell me about your staff?",
    "Haan, mujhe pata hai. Kya masla hai?",
    "نعم أعرف عملك. ما المشكلة؟",
]


@pytest.mark.parametrize("lang,ask", KNOW_ASKS)
def test_dq1_ask_is_recognised(lang, ask):
    assert sr.knows_business_ask(ask)


@pytest.mark.parametrize("text", NOT_KNOW_ASKS)
def test_dq1_other_questions_are_not_the_ask(text):
    assert not sr.knows_business_ask(text)


@pytest.mark.parametrize("reply", GOOD_DQ1)
def test_dq1_honest_not_yet_with_link_passes(reply):
    assert sr.know_business_problem(reply, {"latest_customer_message": KNOW_ASKS[0][1]}) is None


@pytest.mark.parametrize("reply", BAD_DQ1)
def test_dq1_claiming_to_know_is_flagged(reply):
    assert sr.know_business_problem(reply, {"latest_customer_message": KNOW_ASKS[0][1]})


def test_dq1_silent_when_pi_really_knows_something():
    ctx = {
        "latest_customer_message": KNOW_ASKS[0][1],
        "brief": {"business_profile": {"facts": ["sells fabric"]}},
    }
    assert sr.know_business_problem(BAD_DQ1[0], ctx) is None
    assert sr.know_business_problem(BAD_DQ1[0], {"latest_customer_message": "hi"}) is None


# --- EO2: a correction is owned in the first clause ----------------------------------------------
CORRECTIONS = [
    "I didn't mention any customer problems",
    "That's not what I said",
    "I never said that",
    "Maine aisa kuch nahi kaha",
    "Aap ne galat samjha",
    "میں نے ایسا نہیں کہا",
    "لم أقل ذلك",
    "मैंने ऐसा नहीं कहा",
]
OWNED = [
    "Sorry, my mistake. What is the main problem?",
    "You're right, I got that wrong. What would you like to fix?",
    "Maaf kijiye, meri ghalti. Asal masla kya hai?",
    "معذرت، میری غلطی۔ اصل مسئلہ کیا ہے؟",
    "آسف، أخطأت. ما المشكلة الأساسية؟",
    "माफ़ कीजिए, मेरी गलती। असली समस्या क्या है?",
]
NOT_OWNED = [
    "What is the biggest problem in your business?",
    "Customers paying late sounds hard. How often does it happen?",
    "Aap ka masla kya hai?",
    "ما هي المشكلة الأكبر؟",
]


@pytest.mark.parametrize("said", CORRECTIONS)
def test_eo2_correction_is_recognised_and_unowned_reply_flagged(said):
    assert sr.correction_said(said)
    assert sr.correction_not_owned(NOT_OWNED[0], {"latest_customer_message": said})


@pytest.mark.parametrize("reply", OWNED)
def test_eo2_owned_reply_passes(reply):
    assert sr.correction_not_owned(reply, {"latest_customer_message": CORRECTIONS[0]}) is None


@pytest.mark.parametrize(
    "said",
    [
        "Customers pay late",
        "I never get paid on time",
        "Staff said they will leave",
        "میرا عملہ کم ہے",
        "الطلبات تتأخر",
        "देरी होती है",
        "Mujhe kaam nahi mil raha",
    ],
)
def test_eo2_ordinary_messages_are_no_correction(said):
    assert not sr.correction_said(said)
    assert sr.correction_not_owned(NOT_OWNED[1], {"latest_customer_message": said}) is None
