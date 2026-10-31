"""L2-3: the typed options record, the root-cause record and the constraint view. Pure, no model,
no database. Language-neutral structures; owner-facing text is not built here."""

import dataclasses

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import problem_fields as pf


def make_option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
    }
    base.update(over)
    return bm.Option(**base)


def test_an_option_holds_every_field_the_design_names():
    option = make_option(
        works_on=("h1",),
        catalogue_key=None,
        fit=bm.Fit(problem_link=("P1",), facts_reused=("m1",), generic=False),
        limits=("It does not change how stock is ordered",),
        trade_offs=("Someone has to do it daily",),
        dependencies=(bm.Dependency("owner_input", "Which shelf first", blocking=False),),
        risks=(bm.Risk("It may be skipped on busy days", "medium"),),
        constraint_checks=(bm.ConstraintCheck("budget", "ok", "no spend"),),
        expected_outcome="I want fewer surprises",
        evidence=(bm.Evidence("m1", ("count", "stock")),),
    )
    assert option.status == "alternative" and option.rejected_because == ""
    assert option.fit.problem_link == ("P1",) and option.fit.generic is False
    assert option.dependencies[0].kind == "owner_input" and not option.dependencies[0].blocking
    assert option.risks[0].level == "medium"
    assert option.constraint_checks[0].result == "ok"
    assert option.evidence[0].words == ("count", "stock")


def test_records_are_frozen():
    option = make_option()
    with pytest.raises(dataclasses.FrozenInstanceError):
        option.what = "changed"  # type: ignore[misc]


def test_the_cost_is_always_the_staffs_and_never_filled_by_pi():
    cost = bm.Cost()
    assert cost.source == "staff" and cost.amount is None
    assert make_option().cost == bm.Cost()


def test_derived_properties_come_from_the_record_not_from_a_score():
    option = make_option(
        dependencies=(
            bm.Dependency("data", "last year's sheet", blocking=True),
            bm.Dependency("person", "a helper", blocking=False),
        ),
        constraint_checks=(
            bm.ConstraintCheck("budget", "ok"),
            bm.ConstraintCheck("staff", "unknown", "cannot parse"),
            bm.ConstraintCheck("cannot_change#1", "violates", "touches the till"),
        ),
    )
    assert [d.text for d in option.blocking_dependencies] == ["last year's sheet"]
    assert [c.constraint for c in option.violated] == ["cannot_change#1"]
    assert [c.constraint for c in option.unknown_checks] == ["staff"]


def verified(msg, words=(), **over):
    return bm.mark_verified(bm.Evidence(msg, tuple(words), **over))


def test_a_ref_with_no_words_counts_for_nothing():
    refs = (verified("m1", ("count",)), verified("m2"))
    assert make_option(evidence=refs).evidence_strength == 1
    assert make_option(evidence=(verified("m2"),)).evidence_strength == 0


def test_a_ref_with_no_message_id_counts_for_nothing():
    assert make_option(evidence=(verified("", ("count",)),)).evidence_strength == 0
    assert make_option(evidence=(verified("  ", ("count",)),)).evidence_strength == 0


def test_only_a_verified_owner_ref_counts():
    unverified = bm.Evidence("m1", ("count",))
    assert make_option(evidence=(unverified,)).evidence_strength == 0
    assert make_option(evidence=(verified("m1", ("count",)),)).evidence_strength == 1
    assistant = verified("m1", ("count",), role="assistant")
    assert make_option(evidence=(assistant,)).evidence_strength == 0


def test_each_message_counts_once_and_reused_facts_add_nothing():
    refs = (verified("m1", ("count",)), verified("m1", ("stock",)))
    assert make_option(evidence=refs).evidence_strength == 1
    reused = make_option(evidence=refs, fit=bm.Fit(facts_reused=("m1", "m1", "m2")))
    assert reused.evidence_strength == 1
    assert make_option(fit=bm.Fit(facts_reused=("m1",))).evidence_strength == 0


def test_evidence_strength_is_capped():
    refs = tuple(verified(f"m{i}", ("word",)) for i in range(9))
    assert make_option(evidence=refs).evidence_strength == bm.EVIDENCE_CAP


def test_a_stored_owner_cause_without_evidence_reads_as_pi_inferred():
    bare = {"text": "no owner", "status": "owner_said", "evidence": {"msgs": [], "words": []}}
    assert bm.RootCause.from_b2a(bare).status == "pi_inferred"
    proven = {
        "text": "no owner",
        "status": "owner_said",
        "evidence": {"msgs": ["m1"], "words": ["owner"]},
    }
    assert bm.RootCause.from_b2a(proven).status == "owner_said"
    confirmed = {"text": "x cause", "status": "confirmed", "evidence": {}}
    assert bm.RootCause.from_b2a(confirmed).status == "pi_inferred"


def test_the_readers_tolerate_the_wrong_type():
    for stored in (
        "abc",
        5,
        ["x"],
        {"text": "x", "evidence": "abc"},
        {"text": "x", "evidence": {"msgs": 5}},
    ):
        bm.RootCause.from_b2a(stored)
    for budget in ("5000", 5, ["x"]):
        bm.ConstraintsView.from_b2a(
            {"budget": budget, "cannot_change": ["a", 5, None]}, ["t", {"what": 3}], 7
        )
    assert bm.seq(None) == () and bm.seq("abc") == () and bm.seq([1]) == (1,)


def test_the_option_set_flags_a_single_option_honestly():
    one = bm.OptionSet(options=(make_option(),), single_option=True, single_reason="only one fits")
    assert one.single_option and one.single_reason == "only one fits"
    assert bm.OptionSet(options=()).options == ()


def test_option_to_dict_is_plain_and_language_neutral():
    option = make_option(evidence=(bm.Evidence("m1", ("count",)),))
    data = option.to_dict()
    assert data["id"] == "O1" and data["kind"] == "process_change"
    assert data["cost"] == {"source": "staff", "amount": None}
    assert data["evidence"] == [
        {"msg": "m1", "words": ["count"], "role": "owner", "verified": False}
    ]
    assert data["addresses"] == ["P1"]


def test_a_root_cause_starts_as_pi_inferred_and_is_not_stateable():
    cause = bm.RootCause(text="Nobody owns the evening count")
    assert cause.status == pf.PI_INFERRED
    assert not cause.stateable
    assert cause.evidence_for == () and cause.evidence_against == ()


def test_only_an_owner_status_is_stateable():
    assert bm.RootCause("c", status=pf.OWNER_SAID).stateable
    assert bm.RootCause("c", status=pf.CONFIRMED).stateable
    assert not bm.RootCause("c", status=pf.PI_INFERRED).stateable


def test_a_root_cause_reads_the_b2a_shape():
    stored = {
        "text": "We never count stock at night",
        "status": "owner_said",
        "evidence": {"msgs": ["m9"], "words": ["never", "count"]},
    }
    cause = bm.RootCause.from_b2a(stored)
    assert cause is not None
    assert cause.text == stored["text"] and cause.status == "owner_said"
    assert cause.evidence_for == (bm.Evidence("m9", ("never", "count")),)
    assert bm.RootCause.from_b2a(None) is None
    assert bm.RootCause.from_b2a({}) is None


def test_an_unknown_status_in_storage_reads_as_pi_inferred():
    stored = {"text": "x cause", "status": "certain", "evidence": {"msgs": [], "words": []}}
    cause = bm.RootCause.from_b2a(stored)
    assert cause is not None and cause.status == pf.PI_INFERRED


def test_the_constraint_view_matches_the_b2a_json_shapes():
    constraints = {
        "budget": {"text": "ready to spend", "msg": "m1"},
        "staff": {"text": "two people", "msg": "m1"},
        "deadline": {"text": "before Eid", "msg": "m2"},
        "cannot_change": [{"text": "keep the old till", "msg": "m3"}, {"text": "no new app"}],
    }
    tried = [
        {"what": "a WhatsApp group", "outcome": "nobody replied", "msg": "m4"},
        {"what": "a paper log"},
    ]
    cause = {
        "text": "no owner",
        "status": "owner_said",
        "evidence": {"msgs": ["m5"], "words": ["owner"]},
    }
    view = bm.ConstraintsView.from_b2a(constraints, tried, cause)
    assert (view.budget, view.staff, view.deadline) == (
        "ready to spend",
        "two people",
        "before Eid",
    )
    assert view.cannot_change == ("keep the old till", "no new app")
    assert view.tried == (
        bm.Tried("a WhatsApp group", "nobody replied"),
        bm.Tried("a paper log", ""),
    )
    assert view.cause is not None and view.cause.text == "no owner"
    assert view.labels() == (
        "budget",
        "staff",
        "deadline",
        "cannot_change#1",
        "cannot_change#2",
        "tried#1",
        "tried#2",
    )


def test_an_empty_or_missing_b2a_value_reads_as_an_empty_view():
    for args in ((None, None, None), ({}, [], {})):
        view = bm.ConstraintsView.from_b2a(*args)
        assert view == bm.ConstraintsView()
        assert view.labels() == ()


def test_the_view_ignores_keys_it_does_not_know():
    view = bm.ConstraintsView.from_b2a(
        {"budget": {"text": "ok"}, "mood": {"text": "x"}}, None, None
    )
    assert view.labels() == ("budget",)
