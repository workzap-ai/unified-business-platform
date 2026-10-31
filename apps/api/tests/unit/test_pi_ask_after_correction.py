"""PS-flow finding: an Urdu or Arabic message that corrects a figure and then asks what to do was
read as a refusal (the correction's "not" / "ليس" / "نہیں"), so no ideas were offered."""

import pytest

from app.modules.pi import solution_ask as sa

ASKS = [
    "معذرت، 20 نہیں 200 پارسل ہر مہینے واپس آتے ہیں۔ اب ہم کیا کریں؟",
    "عذرا، ليس 20 بل 200 طرد يعود كل شهر. ماذا نفعل الآن؟",
    "آسف، ليس 6 بل 60 زبوناً في اليوم. ماذا نستطيع أن نفعل؟",
    "معذرت، 5 نہیں 50 ڈبل بکنگ ہر مہینے ہوتی ہیں۔ اب ہم کیا کر سکتے ہیں؟",
]
NOT_ASKS = [
    "پتا نہیں کیا کریں",
    "لا أعرف ماذا نفعل",
    "20 نہیں 200 پارسل ہر مہینے واپس آتے ہیں۔",
]


@pytest.mark.parametrize("text", ASKS)
def test_correction_then_ask_is_an_ask(text):
    assert sa.asked_for_ideas(text)


@pytest.mark.parametrize("text", NOT_ASKS)
def test_a_refusal_or_a_bare_correction_is_not(text):
    assert not sa.asked_for_ideas(text)
