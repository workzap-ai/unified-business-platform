"""L2-3 hardening: the rules never raise, evidence is checked against the owner's own messages,
and the cases an independent audit found. Pure, no model, no database."""

import random

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import problem_fields as pf

P = {"P1", "P2"}
OWNER_MSGS = {
    "m1": "Honestly we never count stock at night",
    "m2": "the evening count is skipped",
}


def ev(msg="m1", words=("count", "stock"), **over):
    return bm.Evidence(msg, tuple(words), **over)


def good_ev(msg="m1", words=("count", "stock")):
    return bm.Evidence(msg, tuple(words), verified=True, seal=bm.SEAL)


def option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (good_ev(),),
    }
    base.update(over)
    return bm.Option(**base)


def codes(issues):
    return [i.code for i in issues]


def ids(options):
    return [o.id for o in options]


# --- evidence is checked against the owner's own messages ---


def test_evidence_must_name_an_owner_message_and_its_words():
    ok = option(evidence=(ev("m1", ("count", "stock")),))
    assert "OPT-EVIDENCE" not in codes(br.option_issues(ok, P, owner_messages=OWNER_MSGS))
    bad = (
        ev("assistant-5", ("count", "stock")),  # not one of the owner's messages
        ev("m2", ("never", "stock")),  # words from another message
        ev("m1", ("count",), role="assistant"),  # not the owner's
        ev("m1", ()),  # no words
        ev("", ("count",)),  # no message id
    )
    for ref in bad:
        issues = br.option_issues(option(evidence=(ref,)), P, owner_messages=OWNER_MSGS)
        assert "OPT-EVIDENCE" in codes(issues), ref


def test_the_corpus_check_also_needs_a_message_id_and_the_owner_role():
    owner = "Honestly we never count stock at night"
    for ref in (ev("", ("count",)), ev("m1", ("count",), role="assistant")):
        issues = br.option_issues(option(evidence=(ref,)), P, owner_text=owner)
        assert "OPT-EVIDENCE" in codes(issues), ref


def test_verify_option_marks_only_what_the_owner_said_and_ignores_a_forged_flag():
    forged = bm.Evidence("m9", ("zzzz",), verified=True)
    honest = ev("m1", ("count", "stock"))
    checked = br.verify_option(option(evidence=(forged, honest)), OWNER_MSGS)
    assert [e.verified for e in checked.evidence] == [False, True]
    assert checked.evidence_strength == 1


def test_an_unverified_claim_counts_for_nothing_in_every_function():
    claim = option(evidence=(ev("m9", ("zzzz",)),))
    assert claim.evidence_strength == 0
    assert br.strength(claim) == 0
    assert not br.recommendable(claim)
    assert br.evidence_thin([claim])
    # even a hand-set flag does not count when the owner's messages are given
    forged = option(evidence=(bm.Evidence("m9", ("zzzz",), verified=True),))
    assert br.strength(forged, OWNER_MSGS) == 0
    assert not br.recommendable(forged, OWNER_MSGS)
    assert br.evidence_thin([forged], OWNER_MSGS)


def test_evidence_the_owner_backs_makes_an_option_recommendable_and_not_thin():
    backed = option(evidence=(ev("m1", ("count", "stock")),))
    assert not br.recommendable(backed)  # nothing verified it yet
    assert br.recommendable(backed, OWNER_MSGS)
    assert br.strength(backed, OWNER_MSGS) == 1
    assert not br.evidence_thin([backed], OWNER_MSGS)


def test_ranking_puts_an_option_the_owner_backs_before_one_they_do_not():
    unbacked = option(id="a", evidence=(ev("m9", ("zzzz",)),))
    backed = option(id="b", evidence=(ev("m1", ("count", "stock")),))
    assert ids(br.rank_options((unbacked, backed), OWNER_MSGS)) == ["b", "a"]


def test_a_recommended_option_with_unverified_evidence_is_refused():
    claim = option(status="recommended", evidence=(ev("m9", ("zzzz",)),))
    issues = br.option_issues(claim, P, owner_messages=OWNER_MSGS)
    assert "OPT-RECOMMEND" in codes(issues)


def test_a_cause_proof_must_name_an_owner_message():
    proof = (ev("m1", ("never", "count")),)
    said = bm.RootCause("we never count", status=pf.OWNER_SAID, evidence_for=proof)
    assert br.cause_issues(said, "", OWNER_MSGS) == []
    stray = bm.RootCause("x", status=pf.OWNER_SAID, evidence_for=(ev("assistant-5", ("never",)),))
    assert "CAUSE-UNSUPPORTED" in codes(br.cause_issues(stray, "", OWNER_MSGS))
    assert br.may_state_as_fact(said, "", OWNER_MSGS)
    assert not br.may_state_as_fact(stray, "", OWNER_MSGS)


# --- a status is raised only by an owner event ---


def test_a_status_needs_an_owner_message_id_not_a_bare_boolean():
    assert br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg="m1") == pf.OWNER_SAID
    for marker in (None, "", "  ", True, 1, ["m1"]):
        assert br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg=marker) == pf.PI_INFERRED


def test_the_owner_message_must_be_one_of_the_owners_when_they_are_known():
    got = br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg="m1", owner_msgs={"m2"})
    assert got == pf.PI_INFERRED
    got = br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg="m2", owner_msgs={"m2"})
    assert got == pf.OWNER_SAID


def test_an_unknown_current_status_reads_as_pi_inferred_not_as_an_owner_status():
    assert br.advance_status("bogus", pf.CONFIRMED, owner_msg="m1") == pf.PI_INFERRED
    assert br.advance_status(None, pf.CONFIRMED, owner_msg="m1") == pf.PI_INFERRED  # type: ignore[arg-type]
    assert br.advance_status([], "confirmed", owner_msg="m1") == pf.PI_INFERRED  # type: ignore[arg-type]


# --- the set rules ---


def test_option_ids_are_unique():
    dup = bm.OptionSet(options=(option(), option(what="Another checklist would be agreed")))
    assert "SET-DUPLICATE-ID" in codes(br.set_issues(dup, P))
    fine = bm.OptionSet(options=(option(), option(id="O2")))
    assert "SET-DUPLICATE-ID" not in codes(br.set_issues(fine, P))


def test_a_set_that_could_recommend_but_does_not_needs_its_reason():
    none = bm.OptionSet(options=(option(), option(id="O2")))
    assert "SET-NO-RECOMMENDATION" in codes(br.set_issues(none, P))
    reasoned = bm.OptionSet(
        options=(option(), option(id="O2")), no_recommendation_reason="the owner chooses"
    )
    assert "SET-NO-RECOMMENDATION" not in codes(br.set_issues(reasoned, P))
    chosen = bm.OptionSet(options=(option(), option(id="O2", effort="medium")), recommended_id="O1")
    assert "SET-NO-RECOMMENDATION" not in codes(br.set_issues(chosen, P))
    nothing_to_recommend = bm.OptionSet(options=(option(evidence=()), option(id="O2", evidence=())))
    assert "SET-NO-RECOMMENDATION" not in codes(br.set_issues(nothing_to_recommend, P))


# --- cases an audit found surviving ---


def test_a_rejected_option_is_not_recommendable():
    rejected = option(status="rejected", rejected_because="breaks the old till")
    assert not br.recommendable(rejected)


def test_a_violating_option_is_not_evidence_that_the_evidence_is_thick():
    violating = option(constraint_checks=(bm.ConstraintCheck("budget", "violates"),))
    assert br.evidence_thin([violating])
    assert not br.evidence_thin([violating, option(id="O2")])


def test_a_blocked_option_ranks_before_one_that_violates_a_constraint():
    # the violating option has strong evidence: no score rescues a violation
    strong = (good_ev("m1"), good_ev("m2", ("count",)))
    violates = option(
        id="a",
        effort="none",
        evidence=strong,
        constraint_checks=(bm.ConstraintCheck("b", "violates"),),
    )
    blocked = option(id="b", effort="none", dependencies=(bm.Dependency("data", "x", True),))
    assert ids(br.rank_options((violates, blocked))) == ["b", "a"]
    assert ids(br.rank_options((blocked, violates))) == ["b", "a"]


def test_equal_rank_keys_order_by_id_whatever_the_input_order():
    one, two = option(id="b"), option(id="a")
    assert ids(br.rank_options((one, two))) == ["a", "b"]
    assert ids(br.rank_options((two, one))) == ["a", "b"]


def test_duplicate_ids_still_rank_the_same_way_every_time():
    first = option(id="D", what="first checklist would be agreed")
    second = option(id="D", what="second checklist would be agreed")
    a = [o.what for o in br.rank_options((first, second))]
    b = [o.what for o in br.rank_options((second, first))]
    assert a == b


def test_an_evidence_ref_with_no_words_does_not_make_the_evidence_thick():
    assert br.evidence_thin([option(evidence=(good_ev("m1", ()),))])


# --- the rules never raise ---

MALFORMED = {
    "what int": {"what": 5},
    "what None": {"what": None},
    "benefit list": {"benefit": ["x"]},
    "addresses None": {"addresses": None},
    "addresses str": {"addresses": "P1"},
    "evidence None": {"evidence": None},
    "evidence str": {"evidence": "abc"},
    "evidence words None": {"evidence": (bm.Evidence("m", None),)},  # type: ignore[arg-type]
    "evidence word int": {"evidence": (bm.Evidence("m", (5,)),)},  # type: ignore[arg-type]
    "rejected_because None": {"rejected_because": None},
    "status None": {"status": None},
    "kind None": {"kind": None},
    "effort list": {"effort": ["x"]},
    "id None": {"id": None},
    "id int": {"id": 3},
    "cost None": {"cost": None},
    "fit None": {"fit": None},
    "dependencies str": {"dependencies": "x"},
    "risks list of str": {"risks": ["x"]},
    "checks None": {"constraint_checks": None},
    "limits int": {"limits": (1,)},
    "text too long": {"what": "x " * 600},
}


@pytest.mark.parametrize("name", list(MALFORMED))
def test_a_wrong_type_is_reported_as_malformed_not_raised(name):
    issues = br.option_issues(option(**MALFORMED[name]), P)
    assert "MALFORMED" in codes(issues), name
    br.rank_options([option(**MALFORMED[name]), option(id="O2")])
    br.set_issues(bm.OptionSet(options=(option(**MALFORMED[name]), option(id="O2"))), P)


def test_malformed_inputs_to_the_checks_are_reported():
    assert "MALFORMED" in codes(br.option_issues(option(), None))
    assert "MALFORMED" in codes(br.option_issues(option(), [1, 2]))
    assert "MALFORMED" in codes(br.option_issues(option(), P, owner_text=5))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.option_issues(option(), P, owner_messages={"m": 1}))  # type: ignore[dict-item]
    assert "MALFORMED" in codes(br.option_issues(option(), P, view="x"))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.option_issues(option(), P, cause=bm.RootCause(None)))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.option_issues(None, P))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.set_issues(None, P))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.set_issues(bm.OptionSet(None), P))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.cause_issues(bm.RootCause(None), "x"))  # type: ignore[arg-type]
    assert "MALFORMED" in codes(br.cause_issues(None, "x"))  # type: ignore[arg-type]


def test_a_malformed_option_does_not_hide_the_problems_of_the_others():
    broken = option(id="B", what=5)
    bad_link = option(id="C", addresses=("P9",))
    result = br.set_issues(bm.OptionSet(options=(broken, bad_link)), P)
    assert ("MALFORMED", "B") in [(i.code, i.option_id) for i in result]
    assert ("OPT-ADDR", "C") in [(i.code, i.option_id) for i in result]


def test_ranking_survives_missing_or_mixed_input():
    assert br.rank_options(None) == ()
    assert br.rank_options(5) == ()  # type: ignore[arg-type]
    assert br.rank_options([None, "x", 3]) == ()  # type: ignore[list-item]
    assert len(br.rank_options([option(id=None), option(id="O2")])) == 2
    assert len(br.rank_options([option(id=1), option(id="O2")])) == 2
    assert len(br.rank_options([option(evidence=None), option(id="O2")])) == 2
    assert len(br.rank_options(option(id=str(i)) for i in range(3))) == 3  # a generator


JUNK = [
    None,
    0,
    7,
    3.5,
    True,
    "",
    "x",
    [],
    ["x"],
    ("x", 1),
    {},
    {"a": 1},
    object(),
    b"b",
    float("nan"),
]
FIELDS = (
    "id",
    "kind",
    "what",
    "addresses",
    "benefit",
    "effort",
    "reversibility",
    "status",
    "works_on",
    "catalogue_key",
    "fit",
    "limits",
    "trade_offs",
    "dependencies",
    "risks",
    "constraint_checks",
    "expected_outcome",
    "evidence",
    "rejected_because",
    "cost",
)


def random_option(rng: random.Random, n: int) -> bm.Option:
    base = option(id=f"O{n}")
    changes = {f: rng.choice(JUNK) for f in FIELDS if rng.random() < 0.15}
    if rng.random() < 0.2:
        changes["evidence"] = (bm.Evidence(rng.choice(JUNK), rng.choice(JUNK)),)  # type: ignore[arg-type]
    if rng.random() < 0.2:
        changes["dependencies"] = (bm.Dependency(rng.choice(JUNK), rng.choice(JUNK)),)  # type: ignore[arg-type]
    if rng.random() < 0.2:
        changes["constraint_checks"] = (bm.ConstraintCheck(rng.choice(JUNK), rng.choice(JUNK)),)  # type: ignore[arg-type]
    return bm.Option(**{**base.__dict__, **changes})


def test_a_500_record_fuzz_never_raises():
    rng = random.Random(20261031)
    for n in range(500):
        picked = [random_option(rng, i) for i in range(3)]
        oset = bm.OptionSet(
            options=rng.choice([tuple(picked), list(picked), rng.choice(JUNK)]),  # type: ignore[arg-type]
            recommended_id=rng.choice([None, "O0", "zz", 5]),  # type: ignore[arg-type]
        )
        cause = bm.RootCause(rng.choice(JUNK + ["staff skip"]), rng.choice(JUNK + ["owner_said"]))  # type: ignore[arg-type]
        view = rng.choice([None, bm.ConstraintsView(budget="x"), "bad"])
        owner = rng.choice([None, "never count stock", 5])
        msgs = rng.choice([None, OWNER_MSGS, {"m": 1}])
        ids_in = rng.choice([P, None, [1], "P1", ["P1"]])
        kwargs = {"owner_text": owner, "owner_messages": msgs, "view": view, "cause": cause}
        for one in picked:
            result = br.option_issues(one, ids_in, **kwargs)  # type: ignore[arg-type]
            assert isinstance(result, list), n
            br.recommendable(one, msgs)  # type: ignore[arg-type]
            br.strength(one, msgs)  # type: ignore[arg-type]
        assert isinstance(br.set_issues(oset, ids_in, **kwargs), list), n  # type: ignore[arg-type]
        assert isinstance(br.rank_options(picked, msgs), tuple), n  # type: ignore[arg-type]
        br.evidence_thin(picked, msgs)  # type: ignore[arg-type]
        br.cause_issues(cause, owner, msgs)  # type: ignore[arg-type]
        br.may_state_as_fact(cause, owner, msgs)  # type: ignore[arg-type]
        br.advance_status(
            rng.choice(JUNK + ["pi_inferred"]),
            rng.choice(JUNK + ["confirmed"]),
            owner_msg=rng.choice(JUNK + ["m1"]),
        )  # type: ignore[arg-type]
        bm.RootCause.from_b2a(rng.choice(JUNK + [{"text": "x", "evidence": rng.choice(JUNK)}]))
        bm.ConstraintsView.from_b2a(rng.choice(JUNK), rng.choice(JUNK), rng.choice(JUNK))


def test_the_corpus_check_refuses_an_id_that_names_another_speaker():
    owner = "Honestly we never count stock at night"
    for msg in ("assistant-5", "pi:3", "System_1"):
        issues = br.option_issues(
            option(evidence=(ev(msg, ("count", "stock")),)), P, owner_text=owner
        )
        assert "OPT-EVIDENCE" in codes(issues), msg
    ok = br.option_issues(option(evidence=(ev("m1", ("count",)),)), P, owner_text=owner)
    assert "OPT-EVIDENCE" not in codes(ok)
