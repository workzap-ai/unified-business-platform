"""B2a: the per-problem requirement fields. Pure, no database."""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.modules.pi import problem_fields as pf
from app.modules.pi.problem_models import PiProblem
from app.modules.pi.problems import ProblemBook, ProblemNote

API = Path(__file__).resolve().parents[2]
MSG = str(uuid4())
HEARD = "Honestly we never count stock at night"


def values(note, problem=None, said=None):
    return ProblemBook.requirement_values(note, problem, uuid4(), said)


def test_a_note_with_none_of_the_fields_writes_nothing():
    assert values(ProblemNote(title="x")) == ({}, False)


def test_constraints_budget_staff_deadline_and_cannot_change():
    note = ProblemNote(
        budget="ready, about 5 lakh",
        staff="2 people",
        deadline="before Eid",
        cannot_change=["keep the current POS", "keep the current POS", "same shop hours"],
    )
    got, _ = values(note)
    c = got["constraints"]
    assert c["budget"]["text"] == "ready, about 5 lakh" and c["staff"]["text"] == "2 people"
    assert c["deadline"]["text"] == "before Eid"
    assert [e["text"] for e in c["cannot_change"]] == ["keep the current POS", "same shop hours"]
    assert c["budget"]["msg"]  # audit: which message said it


def test_constraints_merge_keeps_other_keys_and_replaces_the_said_one():
    old = {"budget": {"text": "ready"}, "cannot_change": [{"text": "keep POS"}]}
    new, _ = pf.merge_constraints(old, "about 3 lakh", "", "", ["keep POS", "no new hires"], None)
    assert new["budget"]["text"] == "about 3 lakh"
    assert [e["text"] for e in new["cannot_change"]] == ["keep POS", "no new hires"]
    assert pf.merge_constraints(old, "", "", "", [], None)[0] is None  # nothing said


def test_caps_and_redaction_before_cutting():
    note = ProblemNote(budget="x" * 500, deadline="card 4111 1111 1111 1111 before Eid")
    got, changed = values(note)
    assert len(got["constraints"]["budget"]["text"]) == pf.TEXT_CAP
    assert "4111" not in got["constraints"]["deadline"]["text"] and changed
    many = [f"item {i}" for i in range(20)]
    new, _ = pf.merge_constraints(None, "", "", "", many, None)
    assert len(new["cannot_change"]) == pf.LIST_CAP


def test_a_third_party_name_is_taken_out_and_the_role_stays():
    got, _ = values(ProblemNote(cannot_change=["my brother Ahmed runs the stock"]))
    text = got["constraints"]["cannot_change"][0]["text"]
    assert "Ahmed" not in text and "brother" in text


def test_tried_adds_updates_the_outcome_and_caps():
    first, _ = pf.merge_tried(
        None, [{"what": "WhatsApp group", "outcome": "orders got lost"}], "m1"
    )
    assert first == [{"what": "WhatsApp group", "outcome": "orders got lost", "msg": "m1"}]
    again, _ = pf.merge_tried(first, [{"what": "whatsapp group", "outcome": "still messy"}], "m2")
    assert len(again) == 1 and again[0]["outcome"] == "still messy"
    assert pf.merge_tried(first, [{"what": "WhatsApp group"}], None)[0] is None
    assert pf.merge_tried(first, [{"what": ""}], None)[0] is None
    full, _ = pf.merge_tried(None, [{"what": f"w{i}", "outcome": "o"} for i in range(9)], None)
    assert len(full) == pf.LIST_CAP


def test_a_cause_the_owner_said_needs_their_words_otherwise_it_is_a_guess():
    said, _ = pf.merge_cause(None, "no stock count at night", True, ["we never count"], MSG, HEARD)
    assert said["status"] == pf.OWNER_SAID and said["evidence"]["words"] == ["we never count"]
    assert said["evidence"]["msgs"] == [MSG]
    no_words, _ = pf.merge_cause(None, "no stock count at night", True, [], MSG, HEARD)
    assert no_words["status"] == pf.PI_INFERRED
    guess, _ = pf.merge_cause(None, "staff steal", False, ["we never count"], MSG, HEARD)
    assert guess["status"] == pf.PI_INFERRED


def test_a_guess_never_lowers_or_replaces_what_the_owner_said():
    said = {
        "text": "no stock count",
        "status": "owner_said",
        "evidence": {"msgs": [], "words": ["never count"]},
    }
    assert pf.merge_cause(said, "bad suppliers", False, [], None)[0] is None
    confirmed = {**said, "status": "confirmed"}
    assert pf.merge_cause(confirmed, "bad suppliers", False, [], None)[0] is None
    assert (
        pf.merge_cause(confirmed, "No stock count", True, ["never count"], None, HEARD)[0] is None
    )  # same


def test_the_owner_changing_their_cause_replaces_it_and_resets_confirmed():
    confirmed = {"text": "no count", "status": "confirmed", "evidence": {"msgs": [], "words": []}}
    new, _ = pf.merge_cause(
        confirmed, "late supplier", True, ["supplier is late"], None, "the supplier is late"
    )
    assert new["status"] == pf.OWNER_SAID and new["text"] == "late supplier"


def test_a_guess_is_upgraded_when_the_owner_then_says_it():
    guess = {"text": "no count", "status": "pi_inferred", "evidence": {"msgs": [], "words": []}}
    new, _ = pf.merge_cause(guess, "no count", True, ["we never count"], "m9", HEARD)
    assert new["status"] == pf.OWNER_SAID


def test_confirmed_only_from_owner_said_never_from_a_guess():
    assert pf.confirmed_cause(None) is None
    assert pf.confirmed_cause({"text": "t", "status": "pi_inferred"}) is None
    assert pf.confirmed_cause({"text": "t", "status": "confirmed"}) is None
    assert pf.confirmed_cause({"text": "t", "status": "owner_said"})["status"] == "confirmed"


def test_a_reader_gets_only_a_cause_the_owner_said():
    assert pf.stated_cause(None) == ""
    assert pf.stated_cause({"text": "t", "status": "pi_inferred"}) == ""
    assert pf.stated_cause({"text": "t", "status": "owner_said"}) == "t"
    assert pf.stated_cause({"text": "t", "status": "confirmed"}) == "t"


def test_the_older_cause_column_gets_only_the_owners_cause_never_a_guess():
    said, _ = values(
        ProblemNote(cause_text="no count", cause_said=True, cause_words=["never count"]),
        None,
        HEARD,
    )
    assert said["person_believes_cause"] == "no count"
    guess, _ = values(ProblemNote(cause_text="staff steal"))
    assert guess["cause"]["status"] == "pi_inferred" and "person_believes_cause" not in guess


def test_the_cause_is_redacted():
    got, changed = values(
        ProblemNote(
            cause_text="card 4111 1111 1111 1111 was used", cause_said=True, cause_words=["x"]
        ),
        None,
        "x",
    )
    assert "4111" not in got["cause"]["text"] and changed


def test_expected_outcome_is_capped_and_not_rewritten_when_unchanged():
    got, _ = values(ProblemNote(expected_outcome="one list " * 100))
    assert len(got["expected_outcome"]) == pf.OUTCOME_CAP
    same = SimpleNamespace(
        constraints=None,
        tried=None,
        cause=None,
        expected_outcome="orders never lost",
        user_words=[],
    )
    note = ProblemNote(expected_outcome="orders never lost")
    assert "expected_outcome" not in values(note, same)[0]


def test_the_columns_are_nullable_with_no_default():
    for name in ("constraints", "tried", "cause", "expected_outcome"):
        column = PiProblem.__table__.c[name]
        assert column.nullable and column.server_default is None and column.default is None


def test_the_migration_is_additive_reversible_and_follows_0052():
    path = API / "migrations" / "versions" / "0053_pi_problem_requirements.py"
    spec = importlib.util.spec_from_file_location("m0053", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "0052_pi_open_items"
    source = path.read_text(encoding="utf-8")
    assert len(re.findall(r"op\.add_column", source)) == 4
    assert len(re.findall(r"op\.drop_column", source)) == 4
    forbidden = r"create_table|drop_table|alter_column|execute|create_index|server_default"
    assert not re.search(forbidden, source)
    assert source.count("nullable=True") == 4
    followers = [
        p.name
        for p in (API / "migrations" / "versions").glob("*.py")
        if 'down_revision = "0053_pi_problem_requirements"' in p.read_text(encoding="utf-8")
    ]
    # 0054 is the payment idempotency key (BL-05), not a pi migration; the chain stays linear
    assert followers == ["0054_payment_idempotency.py"]


def test_a_fabricated_evidence_word_makes_the_cause_a_guess():
    got, _ = pf.merge_cause(None, "no count", True, ["the owner never wrote this"], MSG, HEARD)
    assert got["status"] == pf.PI_INFERRED and got["evidence"]["words"] == []


def test_one_fabricated_word_in_a_list_makes_it_a_guess_and_only_real_words_are_kept():
    words = ["WE NEVER COUNT", "invented"]
    got, _ = pf.merge_cause(None, "no count", True, words, MSG, HEARD)
    assert got["status"] == pf.PI_INFERRED
    assert got["evidence"]["words"] == ["WE NEVER COUNT"]  # case-insensitive, real word only


def test_an_empty_evidence_list_or_no_owner_text_is_a_guess():
    assert pf.merge_cause(None, "no count", True, [], MSG, HEARD)[0]["status"] == pf.PI_INFERRED
    assert pf.merge_cause(None, "no count", True, [" "], MSG, HEARD)[0]["status"] == pf.PI_INFERRED
    assert (
        pf.merge_cause(None, "no count", True, ["we never"], MSG, "")[0]["status"] == pf.PI_INFERRED
    )
    assert (
        pf.merge_cause(None, "no count", True, ["we never"], MSG, HEARD)[0]["status"]
        == pf.OWNER_SAID
    )


def test_model_written_words_never_prove_a_cause_only_the_owners_text_does():
    """Fail closed: a note's user_words, the stored user_words and cause_words are model-written."""
    note = ProblemNote(
        cause_text="no count", cause_said=True, cause_words=["never count"], user_words=[HEARD]
    )
    assert values(note)[0]["cause"]["status"] == pf.PI_INFERRED  # no owner_text
    stored = SimpleNamespace(
        constraints=None, tried=None, cause=None, expected_outcome=None, user_words=[HEARD]
    )
    assert values(note, stored)[0]["cause"]["status"] == pf.PI_INFERRED
    assert values(note, None, None)[0]["cause"]["evidence"]["words"] == []  # none kept as owner's
    assert values(note, None, HEARD)[0]["cause"]["status"] == pf.OWNER_SAID


def test_evidence_words_are_whole_words_of_at_least_three_characters():
    ok = pf.merge_cause(None, "c", True, ["never count"], None, HEARD)[0]
    assert ok["status"] == pf.OWNER_SAID
    assert pf.merge_cause(None, "c", True, ["nev"], None, HEARD)[0]["status"] == pf.PI_INFERRED
    assert pf.merge_cause(None, "c", True, ["we"], None, HEARD)[0]["status"] == pf.PI_INFERRED
    assert pf.merge_cause(None, "c", True, ["a", "no"], None, "a no")[0]["status"] == pf.PI_INFERRED
    mixed = pf.merge_cause(None, "c", True, ["at", "never count"], None, HEARD)[0]
    assert mixed["status"] == pf.OWNER_SAID and mixed["evidence"]["words"] == ["never count"]


def test_an_unchanged_constraint_is_not_replaced():
    old = {"budget": {"text": "ready", "msg": "m1"}, "staff": {"text": "2 people"}}
    assert pf.merge_constraints(old, "READY", "", "", [], "m2")[0] is None
    new, _ = pf.merge_constraints(old, "ready", "3 people", "", [], "m2")
    assert new["budget"] == {"text": "ready", "msg": "m1"}  # untouched, no churn
    assert new["staff"]["text"] == "3 people"


def test_the_owner_can_remove_or_replace_a_cannot_change_entry():
    old = {"cannot_change": [{"text": "keep POS"}, {"text": "same hours"}, {"text": "no loans"}]}
    by_text, _ = pf.merge_constraints(old, "", "", "", [], None, ["Keep pos"])
    assert [e["text"] for e in by_text["cannot_change"]] == ["same hours", "no loans"]
    by_index, _ = pf.merge_constraints(old, "", "", "", [], None, ["#2"])
    assert [e["text"] for e in by_index["cannot_change"]] == ["keep POS", "no loans"]
    swapped, _ = pf.merge_constraints(old, "", "", "", ["use new POS"], None, ["keep POS"])
    assert [e["text"] for e in swapped["cannot_change"]] == [
        "same hours",
        "no loans",
        "use new POS",
    ]
    assert pf.merge_constraints(old, "", "", "", [], None, ["#9", "not there"])[0] is None
    emptied, _ = pf.merge_constraints(
        {"cannot_change": [{"text": "x"}]}, "", "", "", [], None, ["#1"]
    )
    assert "cannot_change" not in emptied


def test_a_sixth_entry_keeps_the_newest_and_logs_the_dropped_count(caplog):
    old = {"cannot_change": [{"text": f"c{i}"} for i in range(5)]}
    with caplog.at_level("WARNING"):
        new, _ = pf.merge_constraints(old, "", "", "", ["c5"], None)
    assert [e["text"] for e in new["cannot_change"]] == ["c1", "c2", "c3", "c4", "c5"]
    assert any(r.message == "pi_problem_field_over_cap" and r.dropped == 1 for r in caplog.records)


def test_third_party_names_inside_tried_and_cause_become_roles():
    tried, _ = pf.merge_tried(
        None, [{"what": "asked my brother Ahmed to count", "outcome": "Ahmed said no"}], None
    )
    assert "Ahmed" not in repr(tried) and "brother" in tried[0]["what"]
    cause, _ = pf.merge_cause(
        None, "my cashier Bilal forgets the count", True, ["forgets"], None, "he forgets"
    )
    assert "Bilal" not in cause["text"] and "cashier" in cause["text"]
