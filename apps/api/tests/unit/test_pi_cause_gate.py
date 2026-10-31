"""L1-3: a cause the model wrote is pi's guess, never the owner's. Only words the owner said in
their own text make `owner_said`; main_cause_known counts nothing else."""

from app.modules.pi import box_signals
from app.modules.pi.problems import ProblemBook, ProblemNote

NOTE = ProblemNote(title="Sales are down", category="sales_leads", believes_cause="competitor")


def values(owner_text):
    return ProblemBook.requirement_values(NOTE, None, None, owner_text)[0]


def test_a_model_written_cause_the_owner_never_said_is_a_hypothesis():
    for owner_text in (None, "", "bikri kam hai bohat", "sales are down since march"):
        got = values(owner_text)
        assert got["cause"]["status"] == "pi_inferred", owner_text
        assert "person_believes_cause" not in got, owner_text  # the owner's column stays empty
        assert got["cause"]["evidence"]["words"] == []


def test_a_cause_in_the_owners_own_words_is_owner_said():
    got = values("mujhe lagta hai competitor ki wajah se bikri kam hai")
    assert got["cause"]["status"] == "owner_said"
    assert got["cause"]["evidence"]["words"] == ["competitor"]
    assert got["person_believes_cause"] == "competitor"


def test_a_word_inside_a_longer_word_is_not_evidence():
    assert values("competitors are everywhere")["cause"]["status"] == "pi_inferred"


def test_the_gate_counts_only_owner_said_or_confirmed_causes():
    def main(cause, status):
        noted = {"ref": "a", "cause": cause, "cause_status": status}
        return box_signals.main_cause_known({"noted_problems": [noted]})

    assert main("", "pi_inferred") is False  # noted_context hides a guess from `cause`
    assert main("competitor", "pi_inferred") is False  # and even if one slipped through
    assert main("competitor", "owner_said") is True
    assert main("competitor", "confirmed") is True
    assert main("competitor", None) is True  # a dict with no status: the text decides (old shape)
