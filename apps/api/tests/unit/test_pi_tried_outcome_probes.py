"""Audit probes for tried_outcome (en / roman_ur / ur / ar / hi): negated failures, weak cues,
hypotheticals and questions, third parties, Arabic 'wa' + failed."""

import pytest

from app.modules.pi import tried_outcome as to

FAILED = [
    "we tried ads and it did not work",
    "ads: it never worked",
    "we tried flyers, it did not help",
    "we tried flyers, not helped at all",
    "I tried discounts before but it failed",
    "humne ads try kiye lekin kaam nahi aaya",
    "humne flyers try kiye, fayda nahi hua",
    "humne discount try kiya lekin nakam raha",
    "folder try kiye lekin mix ho gaye",
    "humne offer try kiya, bekaar raha",
    "ہم نے اشتہار آزمائے لیکن ناکام رہا",
    "ہم نے پوسٹر آزمائے، کوئی فائدہ نہیں",
    "ہم نے ڈسکاؤنٹ آزمایا لیکن کام نہیں آیا",
    "جربت الاعلانات وفشل",
    "جربنا الخصم لكن لم ينجح",
    "جربت الفلاير لم يفد",
    "मैंने विज्ञापन आजमाए लेकिन काम नहीं आया",
    "हमने पोस्टर आज़माए पर फायदा नहीं हुआ",
    "हमने ऑफर कोशिश की लेकिन असफल",
]
NOT_FAILED = [
    "we tried ads and they have not failed",
    "we tried ads, it has never failed",
    "I tried ads, it did not fail",
    "humne ads try kiye aur nakam nahi hue",
    "humne offer try kiya, nakam nahi raha",
    "ہم نے اشتہار آزمائے اور ناکام نہیں ہوا",
    "हमने ऑफर आज़माया और असफल नहीं हुआ",
    "my shop failed to open",
    "we started a shop and it failed to impress",
    "they used our flyers and said useless",
    "the delivery van failed to arrive but we tried again",
]
THIRD_PARTY = [
    "my competitor tried ads and it failed",
    "my brother tried discounts, it did not work",
    "the neighbour tried flyers and it failed",
    "they tried ads but it did not work",
    "woh log ne ads aazmaye lekin kaam nahi aaya",
    "padosi ne offer try kiya, fayda nahi hua",
    "neighbour ne aazmaya, kaam nahi aaya",
    "بھائی نے اشتہار آزمائے، کوئی فائدہ نہیں",
    "انہوں نے پوسٹر آزمائے لیکن ناکام رہے",
    "جاري جرب الاعلانات لكن لم ينجح",
    "पड़ोसी ने ऑफर आज़माया पर काम नहीं आया",
    "उन्होंने विज्ञापन आजमाए, असफल रहे",
]
HYPOTHETICAL = [
    "if I tried ads it would not work",
    "what if we tried flyers and it failed?",
    "do you think ads did not work for others",
    "should I try discounts, it may not work",
    "agar main ads try karun to kaam nahi aayega",
    "kya main flyers try karun, fayda nahi hoga?",
    "اگر ہم اشتہار آزمائیں تو کام نہیں آئے گا",
    "کیا ہم پوسٹر آزمائیں اور ناکام ہو جائیں",
    "إذا جربت الاعلانات لم ينجح",
    "هل جربنا الاعلانات ولم ينجح؟",
    "अगर मैं विज्ञापन आजमाऊं तो काम नहीं आएगा",
    "क्या हम पोस्टर आज़माएं और असफल हों?",
]


@pytest.mark.parametrize("text", FAILED)
def test_a_failed_attempt_by_the_owner_is_failed(text):
    assert to.outcome_of(text) == "failed", text
    assert to.failed_attempt(text) is not None, text


@pytest.mark.parametrize("text", NOT_FAILED)
def test_a_negated_or_weak_or_unrelated_failure_is_not_failed(text):
    assert to.outcome_of(text) != "failed", text
    assert to.failed_attempt(text) is None, text


@pytest.mark.parametrize("text", THIRD_PARTY)
def test_a_third_partys_attempt_is_not_the_owners(text):
    assert to.failed_attempt(text) is None, text
    assert to.outcome_of(text) == "unclear", text


@pytest.mark.parametrize("text", HYPOTHETICAL)
def test_a_hypothetical_or_a_question_is_not_an_attempt(text):
    assert to.failed_attempt(text) is None, text
    assert to.outcome_of(text) == "unclear", text


def test_not_helped_is_never_worked_and_did_not_help_is_failed():
    assert to.outcome_of("not helped") == "failed"
    assert to.outcome_of("it never worked") == "failed"
    assert to.outcome_of("did not help") == "failed"
    assert to.outcome_of("the ads helped a lot") == "worked"
    assert to.outcome_of("the ads never helped") == "failed"


def test_the_owner_who_also_did_it_is_kept_with_a_third_party():
    text = "we tried what my competitor did, it did not work"
    assert to.outcome_of(text) == "failed"


def test_the_arabic_wa_failed_gives_what_was_tried():
    found = to.failed_attempt("جربت الاعلانات وفشل")
    assert found is not None and found.what == "الاعلانات"


def test_a_weak_cue_before_the_attempt_word_does_not_fire():
    assert to.failed_attempt("useless, but we tried") is None
