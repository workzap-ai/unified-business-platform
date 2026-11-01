"""L1 audit G (a corrected cause, tried outcome or constraint keeps the old value in the record's
own history), H (withdrawal is not fired by refusals, questions and quoted words) and I (Arabic
clitics both ways without false matches)."""

import pytest

from app.modules.pi import problem_fields as pf


# ------------------------------------------------------------------ G: history
def test_a_corrected_cause_keeps_the_old_one():
    first, _ = pf.merge_cause(None, "rent", True, ["rent"], "m1", "I think the rent is high", "t1")
    second, _ = pf.merge_cause(
        first, "supplier", True, ["supplier"], "m2", "I think the supplier is late", "t2"
    )
    assert second["text"] == "supplier" and second["status"] == "owner_said"
    (old,) = second["history"]
    assert old["text"] == "rent" and old["status"] == "owner_said"
    assert old["replaced_msg"] == "m2" and old["replaced_at"] == "t2"
    assert old["evidence"]["words"] == ["rent"]


def test_history_survives_a_third_correction():
    a, _ = pf.merge_cause(None, "rent", True, ["rent"], "m1", "I think the rent", "t1")
    b, _ = pf.merge_cause(a, "supplier", True, ["supplier"], "m2", "I think the supplier", "t2")
    c, _ = pf.merge_cause(b, "staff", True, ["staff"], "m3", "I think the staff", "t3")
    assert [h["text"] for h in c["history"]] == ["rent", "supplier"]


def test_a_changed_tried_outcome_keeps_the_old_outcome():
    old = [{"what": "ads", "outcome": "some leads", "msg": "m1"}]
    new, _ = pf.merge_tried(old, [{"what": "ads", "outcome": "failed"}], "m2")
    (entry,) = new
    assert entry["outcome"] == "failed"
    assert entry["history"] == [{"outcome": "some leads", "msg": "m1"}]


def test_the_same_tried_outcome_changes_nothing():
    old = [{"what": "ads", "outcome": "failed", "msg": "m1"}]
    assert pf.merge_tried(old, [{"what": "ads", "outcome": "failed"}], "m2")[0] is None


def test_history_on_a_tried_entry_is_carried_through_a_later_unrelated_save():
    old = [{"what": "ads", "outcome": "failed", "msg": "m1", "history": [{"outcome": "x"}]}]
    new, _ = pf.merge_tried(old, [{"what": "flyers", "outcome": ""}], "m2")
    assert new[0]["history"] == [{"outcome": "x"}]


def test_a_corrected_budget_keeps_the_old_one():
    first, _ = pf.merge_constraints(None, "50000 rupees", "", "", [], "m1")
    second, _ = pf.merge_constraints(first, "80000 rupees", "", "", [], "m2")
    assert second["budget"]["text"] == "80000 rupees"
    (old,) = second["history"]
    assert old["key"] == "budget" and old["text"] == "50000 rupees"
    assert old["replaced_msg"] == "m2"


def test_a_removed_cannot_change_entry_stays_in_the_history():
    first, _ = pf.merge_constraints(None, "", "", "", ["close the shop", "fire anyone"], "m1")
    second, _ = pf.merge_constraints(first, "", "", "", [], "m2", ["close the shop"])
    assert [e["text"] for e in second["cannot_change"]] == ["fire anyone"]
    assert second["history"][0]["text"] == "close the shop"
    third, _ = pf.merge_constraints(second, "", "", "", [], "m3", ["#1"])
    assert "cannot_change" not in third
    assert [h["text"] for h in third["history"]] == ["close the shop", "fire anyone"]


def test_the_same_budget_again_adds_no_history():
    first, _ = pf.merge_constraints(None, "50000 rupees", "", "", [], "m1")
    assert pf.merge_constraints(first, "50000 rupees", "", "", [], "m2")[0] is None


# ------------------------------------------------------------------ H: withdrawal
@pytest.mark.parametrize(
    "text",
    [
        "I take that back",
        "i take it back",
        "that wasn't the cause",
        "that was not the reason",
        "maine galat kaha",
        "wo wajah nahi thi",
        "yeh wajah nahi hai",
        "یہ وجہ نہیں تھی",
        "میں نے غلط کہا",
        "ليس هذا السبب",
        "لم يكن هذا هو السبب",
        "यह वजह नहीं थी",
        "मैंने गलत कहा",
        "sorry. I take that back, the rent is fine",
    ],
)
def test_a_real_withdrawal_is_read(text):
    assert pf.withdrawal_said(text), text


@pytest.mark.parametrize(
    "text",
    [
        "I do not take that back",
        "I won't take that back",
        "don't take that back",
        "I will never take that back",
        "you said that wasn't the cause but it is",
        "you told me that was not the reason, I disagree",
        "kya wo wajah nahi thi?",
        "wo wajah nahi thi kya?",
        "aap ne kaha wo wajah nahi thi lekin hai",
        "کیا یہ وجہ نہیں تھی؟",
        "هل ليس هذا السبب؟",
        "क्या यह वजह नहीं थी?",
        "the rent is high",
        "",
    ],
)
def test_a_refusal_a_question_or_quoted_words_is_not_a_withdrawal(text):
    assert not pf.withdrawal_said(text), text


# ------------------------------------------------------------------ I: Arabic clitics
@pytest.mark.parametrize(
    "word,corpus",
    [
        ("الكتاب", "اشتريت كتاب جديد"),
        ("كتاب", "اشتريت الكتاب جديد"),
        ("للسعر", "ارتفع السعر كثيرا"),
        ("السعر", "نظرنا للسعر كثيرا"),
        ("بيت", "ذهبنا الى فبيت جدي"),
        ("فبيت", "ذهبنا الى بيت جدي"),
        ("المصففين", "نخسر بسبب والمصففين الجدد"),
        ("والمصففين", "المصففين الجدد لا يكفون"),
        ("بالمصففين", "المصففين الجدد"),
        ("الاعلانات", "جربنا والاعلانات"),
    ],
)
def test_an_arabic_word_matches_with_a_clitic_attached_or_removed(word, corpus):
    assert pf._heard(word, corpus), (word, corpus)


@pytest.mark.parametrize(
    "word,corpus",
    [
        ("لبن", "سافرنا الى لبنان"),
        ("لبنان", "اشتريت لبن طازج"),
        ("كلب", "رأيت كلبي في الحديقة"),
        ("كلبي", "رأيت كلب كبير"),
        ("سعر", "ارتفع الاجر"),
        ("المنافس", "ارتفع الاجر"),
    ],
)
def test_arabic_words_that_only_look_alike_do_not_match(word, corpus):
    assert not pf._heard(word, corpus), (word, corpus)
