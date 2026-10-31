"""L2-3 third audit: invented outcomes, savings and free or cost claims in all five languages,
honest hedges that are not promises, a seal no stored value can equal, and saving claims as money.
Each test fails against the previous commit (ac8681e)."""

import dataclasses

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import blueprint_text as bt
from app.modules.pi.constitution import PROMISE

P = {"P1", "P2"}


def option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (bm.mark_verified(bm.Evidence("m1", ("count", "stock"))),),
    }
    base.update(over)
    return bm.Option(**base)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


CLAIMS = [
    # Roman Urdu
    "is se roz do ghante bachte hain",
    "kharcha aadha ho jayega",
    "20 fisad zyada orders milenge",
    "sales double ho jayegi",
    "kharcha nahi hoga",
    "paisa wasool ho jayega",
    # Urdu
    "اس سے روزانہ دو گھنٹے بچتے ہیں",
    "خرچ آدھا ہو جائے گا",
    "بیس فیصد زیادہ آرڈر ملیں گے",
    "خرچ نہیں ہوگا",
    # Hindi
    "इससे रोज़ दो घंटे बचते हैं",
    "खर्च आधा हो जाएगा",
    "बीस प्रतिशत ज़्यादा ऑर्डर मिलेंगे",
    "खर्च नहीं होगा",
    # Arabic
    "يوفر ساعتين يوميا",
    "يخفض التكلفة إلى النصف",
    "زيادة الطلبات بنسبة عشرين بالمئة",
    "بدون رسوم",
    # English
    "Free for the first year",
    "It is free of cost",
    "Costs less than a clerk",
    "It saves 30% of your costs",
]

HEDGES = [
    "There is no guarantee it will fix everything",
    "No guarantee it will work",
    "Nothing here is guaranteed",
    "pakka nahi hai ke kaam karega",
    "یقینی نہیں ہے",
    "पक्का नहीं है",
    "لا نضمن النتيجة",
    "ليس مضمونا",
]

NOT_CLAIMS = [
    "Feel free to say no",
    "This would free up the evening count",
    "The owner is free to decline",
    "A short checklist would be agreed for the evening count",
    "It would cover 4 shops since 2024",
]


@pytest.mark.parametrize("text", CLAIMS)
def test_an_invented_outcome_saving_or_cost_claim_is_caught_in_every_language(text):
    assert bt.promise_in(text, PROMISE, bt.WILL) or bt.money_in(text), text
    issues = br.option_issues(option(what=text), P)
    assert "OPT-MONEY" in codes(issues) or "OPT-PROMISE" in codes(issues), text


@pytest.mark.parametrize("text", CLAIMS)
def test_each_of_them_is_reported_as_money_and_the_outcome_ones_as_a_promise_too(text):
    assert bt.money_in(text), text


@pytest.mark.parametrize("text", CLAIMS[:1] + CLAIMS[2:4] + CLAIMS[6:9] + CLAIMS[10:13])
def test_the_outcome_claims_are_also_promises(text):
    assert bt.promise_in(text, PROMISE, bt.WILL), text


def test_a_saving_claim_is_money_by_its_code_and_by_its_text():
    issues = br.option_issues(option(what="It saves 30% of your costs"), P)
    assert "OPT-MONEY" in codes(issues)
    assert "OPT-PROMISE" in codes(issues)


@pytest.mark.parametrize("text", NOT_CLAIMS)
def test_plain_text_is_not_a_claim(text):
    assert not bt.money_in(text), text
    assert not bt.promise_in(text, PROMISE, bt.WILL), text


@pytest.mark.parametrize("text", CLAIMS[:6])
def test_the_owners_own_figure_in_expected_outcome_stays_exempt(text):
    issues = br.option_issues(option(expected_outcome=text), P)
    assert "OPT-MONEY" not in codes(issues) and "OPT-PROMISE" not in codes(issues)


# --- honest hedges ------------------------------------------------------------------------------


@pytest.mark.parametrize("text", HEDGES)
def test_an_honest_hedge_is_not_a_promise(text):
    assert not bt.promise_in(text, PROMISE, bt.WILL), text
    assert br.option_issues(option(what=text), P) == []


@pytest.mark.parametrize(
    "text",
    [
        "No guarantee, but it will definitely work",
        "There is no guarantee it will fix everything but it never fails",
        "pakka nahi hai lekin zaroor hoga",
        "لا نضمن النتيجة لكن بلا شك سينجح",
    ],
)
def test_a_promise_next_to_a_hedge_is_still_a_promise(text):
    assert bt.promise_in(text, PROMISE, bt.WILL), text


# --- the seal ----------------------------------------------------------------------------------


def test_the_seal_is_not_a_string_and_not_importable_by_name():
    ref = bm.mark_verified(bm.Evidence("m1", ("count",)))
    assert not isinstance(ref.seal, str)
    assert not hasattr(bm, "SEAL")


@pytest.mark.parametrize("seal", ["blueprint-rules-verified", True, 1, "", object()])
def test_a_stored_dict_cannot_forge_the_seal(seal):
    stored = {"msg": "m1", "words": ("count",), "role": "owner", "verified": True, "seal": seal}
    forged = bm.Evidence(**stored)
    assert option(evidence=(forged,)).evidence_strength == 0
    assert br.strength(option(evidence=(forged,))) == 0
    assert br.recommendable(option(evidence=(forged,))) is False


def test_the_seal_does_not_survive_a_copy_through_a_dict():
    data = option().to_dict()["evidence"][0]
    assert "seal" not in data
    rebuilt = bm.Evidence(**data)
    assert dataclasses.replace(rebuilt, verified=True).seal is None
    assert option(evidence=(rebuilt,)).evidence_strength == 0


# --- the same classes in other wordings ---

EXTRA_CLAIMS = [
    "roz aadha ghanta bachega",
    "har hafte paanch ghante bachenge",
    "kharcha 30 fisad kam ho jayega",
    "bachat hogi",
    "aap ka waqt bachega",
    "orders 50 percent barh jayenge",
    "sales dugni ho jayegi",
    "aap ke paise bachenge",
    "30 percent zyada customers aayenge",
    "bilkul free hai",
    "koi charge nahi lagega",
    "ہر ہفتے پانچ گھنٹے بچیں گے",
    "خرچ تیس فیصد کم ہو جائے گا",
    "سیلز دگنی ہو جائے گی",
    "آپ کا وقت بچے گا",
    "بالکل مفت ہے",
    "کوئی چارج نہیں لگے گا",
    "हर हफ्ते पांच घंटे बचेंगे",
    "खर्च तीस प्रतिशत कम हो जाएगा",
    "बिक्री दोगुनी हो जाएगी",
    "आपका समय बचेगा",
    "बिल्कुल मुफ्त है",
    "कोई शुल्क नहीं लगेगा",
    "يوفر خمس ساعات اسبوعيا",
    "يقلل التكلفة بنسبة ثلاثين بالمئة",
    "يضاعف مبيعاتك",
    "سيوفر وقتك",
    "مجاني تماما",
    "لا توجد اي رسوم",
    "saves five hours every week",
    "halves your costs",
    "doubles your orders",
    "30% more customers",
    "It is completely free",
    "free trial",
    "costs nothing",
    "no charge",
    "reduces costs by a third",
]
EXTRA_CLEAN = [
    "Feel free to say no",
    "Free up the evening count",
    "A short checklist would be agreed",
    "The owner counts stock at night",
    "aap ka kaam kaise chalta hai",
    "کیا آپ رات کو سٹاک گنتے ہیں",
    "आप रात को स्टॉक गिनते हैं",
    "هل تعد المخزون ليلا",
    "It would cover 4 shops since 2024",
    "Staff check the till once a week",
    "ek hafta pehle",
    "دو دن پہلے",
    "तीन दिन पहले",
    "A reviewer would check the notes before they are sent",
]


@pytest.mark.parametrize("text", EXTRA_CLAIMS)
def test_the_same_classes_are_caught_in_other_wordings(text):
    assert bt.money_in(text) or bt.promise_in(text, PROMISE, bt.WILL), text
    issues = br.option_issues(option(what=text), P)
    assert "OPT-MONEY" in codes(issues) or "OPT-PROMISE" in codes(issues), text


@pytest.mark.parametrize("text", EXTRA_CLEAN)
def test_ordinary_questions_and_plans_in_every_language_are_clean(text):
    assert not bt.money_in(text), text
    assert not bt.promise_in(text, PROMISE, bt.WILL), text


def test_feel_free_is_not_a_cost_claim_and_a_denied_risk_word_still_counts():
    assert not bt.money_in("Feel free to reply whenever it suits")
    assert bt.promise_in("There is no risk guaranteed", PROMISE, bt.WILL)
