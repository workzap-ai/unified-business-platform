"""L1 re-audit: owner endorsement and the owner as the subject of an attempt are POSITIVE rules; the
default is pi_inferred / unset. The auditor's failing inputs, the keep-passing ones, the 60%
threshold of the legacy believes_cause path, phone and name redaction."""

import pytest

from app.modules.pi import problem_fields as pf
from app.modules.pi import tried_outcome as to
from app.modules.pi.problems import ProblemBook, ProblemNote


def status(word, text):
    cause, _ = pf.merge_cause(None, word, True, [word], "m1", text)
    return cause["status"]


NOT_OWNERS_CAUSE = [
    ("rent", "customers say the rent makes prices high"),
    ("rent", "the staff think rent is the reason"),
    ("rent", "my supplier believes it is the rent"),
    ("rent", "accountant told me the rent is the cause"),
    ("rent", "he told me it is the rent"),
    ("rent", "she thinks it is the rent"),
    ("pricing", "a consultant said the pricing is wrong"),
    ("price", "the market says my price is high"),
    ("location", "they say the location is bad"),
    ("location", "people say the location is bad"),
    ("location", "everyone says the location is bad"),
    ("dirty", "customers complain the shop is dirty"),
    ("delays", "supplier blames me for delays"),
    ("کرایہ", "میرے ساتھی نے کہا کرایہ وجہ ہے"),
    ("किराया", "दोस्त ने कहा किराया वजह है"),
    ("kiraya", "staff ka khayal hai kiraya zyada hai"),
    ("الإيجار", "قالوا إن الإيجار هو السبب"),
    ("الإيجار", "الزبائن قالوا الإيجار مرتفع"),
    ("rent", "you asked whether rent is the cause; not sure"),
    ("rent", "you mentioned rent might be it, hmm"),
    ("rent", "I don't think it's the rent"),
    ("rent", "I'm not sure it's the rent"),
    ("rent", "I doubt rent is the reason"),
    ("rent", "rent has nothing to do with it"),
    ("rent", "not really the rent"),
    ("rent", "rent, maybe not"),
    ("rent", "rent ka masla nahi hai"),
    ("kiraya", "kiraya masla nahi hai"),
    ("kiraya", "mujhe nahi lagta kiraya wajah hai"),
    ("کرایہ", "کرایہ مسئلہ نہیں ہے"),
    ("کرایہ", "مجھے نہیں لگتا کرایہ وجہ ہے"),
    ("किराया", "मुझे नहीं लगता किराया वजह है"),
    ("rent", "oh sure, it's the rent, right, like that's the real reason"),
    ("rent", "yeah right, the rent. as if"),
]


@pytest.mark.parametrize("word,text", NOT_OWNERS_CAUSE)
def test_not_the_owners_cause(word, text):
    assert status(word, text) == "pi_inferred", text
    note = ProblemNote(title="t", believes_cause=word)
    got, _ = ProblemBook.requirement_values(note, None, "m", text)
    assert "person_believes_cause" not in got, text


@pytest.mark.parametrize(
    "word,text",
    [
        ("rent", "I think the rent is the problem"),
        ("rent", "I believe the rent is too high"),
        ("kiraya", "mera khayal hai kiraya zyada hai"),
        ("kiraya", "mujhe lagta hai kiraya wajah hai"),
        ("کرایہ", "میرا خیال ہے کرایہ زیادہ ہے"),
        ("الإيجار", "أعتقد أن الإيجار مرتفع"),
        ("किराया", "मुझे लगता है किराया ज़्यादा है"),
        ("rent", "I think the rent is too high"),
    ],
)
def test_the_owners_own_claim_is_owner_said(word, text):
    assert status(word, text) == "owner_said", text


# ------------------------------------------------------------------ tried: the owner is the subject
def stored(what, text, outcome=""):
    note = ProblemNote(title="Sales fell", tried=[{"what": what, "outcome": outcome}])
    got, _ = ProblemBook.requirement_values(note, None, "m", text)
    return got.get("tried") or []


NOT_STORED = [
    ("flyers", "my staff tried flyers and it did not work"),
    ("flyers", "supplier tried flyers for me, it did not work"),
    ("flyers", "customers tried the flyers and said it was useless"),
    ("flyers", "I haven't tried flyers, didn't work for others"),
    ("flyers", "humne flyers try nahi kiye, kaam nahi aaya sab ka"),
    ("ads", "ads? we never tried ads"),
    ("flyers", "we have not tried flyers yet"),
    ("flyers", "I plan to try flyers, hopefully it won't fail"),
    ("flyers", "humne flyers kabhi try nahi kiye"),
    ("flyers", "I heard flyers don't work, so I never tried"),
]


@pytest.mark.parametrize("what,text", NOT_STORED)
def test_an_attempt_the_owner_did_not_make_is_not_stored(what, text):
    assert stored(what, text) == [], text
    assert to.failed_attempt(text) is None, text


def test_worked_at_first_then_stopped_is_failed_not_worked():
    (entry,) = stored("flyers", "we tried flyers, it worked at first then stopped")
    assert entry["outcome"] == "failed"


def test_a_sarcastic_report_is_never_stored_as_worked():
    got = stored("flyers", "sure, I tried flyers. brilliant, did nothing obviously")
    assert all(e["outcome"] != "worked" for e in got)


def test_the_arabic_negated_failure_is_not_a_failed_item():
    text = "لم يفشل الإعلان عندما جربته"
    assert to.failed_attempt(text) is None
    assert all(e["outcome"] != "failed" for e in stored("الإعلان", text))
    assert all("لم ي" not in e["what"] for e in stored("الإعلان", text))


def test_the_owners_own_attempt_in_each_language_is_still_stored():
    cases = [
        ("flyers", "we tried flyers and it did not work", "failed"),
        ("rang wale folder", "maine rang wale folder try kiye lekin mix ho gaye", "failed"),
        ("اشتہار", "ہم نے اشتہار آزمائے لیکن ناکام رہا", "failed"),
        ("الاعلانات", "جربت الاعلانات وفشل", "failed"),
        ("विज्ञापन", "मैंने विज्ञापन आजमाए लेकिन काम नहीं आया", "failed"),
    ]
    for what, text, outcome in cases:
        (entry,) = stored(what, text)
        assert entry["outcome"] == outcome, text


# ------------------------------------------------------------------ withdrawal
def test_a_third_partys_withdrawal_is_not_the_owners():
    assert not pf.withdrawal_said("my partner says that wasn't the cause")
    assert not pf.withdrawal_said("he told me that wasn't the reason")
    assert not pf.withdrawal_said("the accountant said I take that back")


def test_the_arabic_emphatic_no_before_the_withdrawal_is_a_withdrawal():
    assert pf.withdrawal_said("لا ليس هذا السبب")
    assert pf.withdrawal_said("نہیں، یہ وجہ نہیں تھی")
    assert pf.withdrawal_said("nahi, wo wajah nahi thi")


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize("number", ["042-111-222-333", "03 00 1234567", "0300 12 34567"])
def test_more_phone_forms_are_redacted(number):
    text, changed = pf.clean(f"call {number} now", 200)
    assert changed and "111" not in text and "1234567" not in text


@pytest.mark.parametrize(
    "text",
    [
        "budget 300000 rupees",
        "deadline 01-15-2024",
        "we lose 2024 rupees a day",
        "only 12 34 56 staff",
    ],
)
def test_figures_stay(text):
    assert pf.clean(text, 200) == (text, False)


@pytest.mark.parametrize(
    "text,name",
    [
        ("meri biwi Sara kehti hai", "Sara"),
        ("employee named Usman steals", "Usman"),
        ("my accountant called Bilal said", "Bilal"),
        ("mere bhai Ahmed ne kaha", "Ahmed"),
    ],
)
def test_a_third_partys_name_is_not_kept(text, name):
    assert name not in pf.clean(text, 200)[0]


# ------------------------------------------------------------------ the 60% threshold (N6)
def legacy(believes, text):
    note = ProblemNote(title="Sales fell", believes_cause=believes)
    got, _ = ProblemBook.requirement_values(note, None, "m", text)
    return got["cause"]["status"]


def test_the_legacy_believes_cause_needs_sixty_percent_of_its_content_words():
    believes = "supplier delays big shipments weekly"  # five content words
    assert legacy(believes, "I think the supplier delays big shipments") == "owner_said"  # 4 of 5
    assert legacy(believes, "I think the supplier delays shipments") == "owner_said"  # 3 of 5 = 60%
    assert legacy(believes, "I think the supplier delays") == "pi_inferred"  # 2 of 5 = 40%
    assert legacy(believes, "I think the supplier") == "pi_inferred"
