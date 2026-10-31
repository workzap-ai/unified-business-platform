"""L1 follow-ups: the owner takes a cause back (history kept, nothing downstream reads it) and an
Arabic evidence word matches with a clitic attached."""

import pytest

from app.modules.pi import box_signals
from app.modules.pi import problem_fields as pf

SAID = {
    "text": "the competitor is cheaper",
    "status": "owner_said",
    "evidence": {"msgs": ["m1"], "words": ["competitor"]},
}


@pytest.mark.parametrize(
    "text",
    [
        "I take that back",
        "that wasn't the cause",
        "maine galat kaha",
        "wo wajah nahi thi",
        "یہ وجہ نہیں تھی",
        "میں نے غلط کہا",
        "ليس هذا السبب",
        "यह वजह नहीं थी",
        "मैंने गलत कहा",
    ],
)
def test_a_withdrawal_is_read_in_five_languages(text):
    assert pf.withdrawal_said(text)


@pytest.mark.parametrize(
    "text", ["the competitor is cheaper", "wajah yeh hai ke rent zyada hai", ""]
)
def test_a_plain_cause_is_not_a_withdrawal(text):
    assert not pf.withdrawal_said(text)


def test_withdrawing_clears_the_cause_and_keeps_the_history():
    new = pf.withdraw_cause(SAID, "m9", "2026-10-31T10:00:00+00:00")
    assert new["text"] == "" and new["status"] == "withdrawn"
    (entry,) = new["history"]
    assert entry["text"] == "the competitor is cheaper" and entry["status"] == "owner_said"
    assert entry["withdrawn_msg"] == "m9" and entry["withdrawn_at"].startswith("2026-10-31")
    assert pf.stated_cause(new) == ""  # no reader may state it


def test_only_an_owner_cause_can_be_withdrawn():
    assert pf.withdraw_cause(None, "m", "t") is None
    assert pf.withdraw_cause({"text": "x", "status": "pi_inferred"}, "m", "t") is None


def test_a_later_guess_or_cause_keeps_the_history():
    withdrawn = pf.withdraw_cause(SAID, "m9", "t")
    guess, _ = pf.merge_cause(withdrawn, "rent is high", True, ["rent"], "m10", "bikri kam hai")
    assert guess["status"] == "pi_inferred" and len(guess["history"]) == 1
    owner, _ = pf.merge_cause(withdrawn, "rent is high", True, ["rent"], "m10", "rent is high")
    assert owner["status"] == "owner_said" and len(owner["history"]) == 1


def test_a_withdrawn_cause_does_not_open_the_offer_gate():
    noted = [{"cause": "", "cause_status": "withdrawn"}]
    assert box_signals.main_cause_known({"noted_problems": noted}) is False


def test_an_arabic_word_with_an_attached_conjunction_is_the_owners_word():
    corpus = "نخسر العملاء بسبب والمصففين الجدد"
    assert pf.said_by_owner(["المصففين"], corpus)  # bare word, said with a glued "wa"
    assert pf.said_by_owner(["والمصففين"], "المصففين الجدد لا يكفون")  # the other way round
    assert pf.said_by_owner(["بالمصففين"], corpus)  # a different clitic, same word
    assert not pf.said_by_owner(["المنافسين"], corpus)  # a different word never matches


def test_an_arabic_cause_the_owner_said_becomes_owner_said():
    cause, _ = pf.merge_cause(
        None, "المصففين الجدد", True, ["المصففين"], "m1", "المشكلة هي والمصففين الجدد"
    )
    assert cause["status"] == "owner_said"


def test_a_note_cannot_bring_back_a_cause_the_owner_took_back():
    withdrawn = pf.withdraw_cause(SAID, "m9", "t")
    again, _ = pf.merge_cause(
        withdrawn, "the competitor is cheaper", True, ["competitor"], "m10", SAID["text"]
    )
    assert again is None  # unchanged: the withdrawn record stands
