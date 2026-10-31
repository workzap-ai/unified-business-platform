"""L2-3: the pure validators and the ranking of an options record. Each rule has a test that fails
when the rule is removed (see the mutation check described in the commit report). No model, no
database."""

import pytest

from app.modules.pi import blueprint_models as bm
from app.modules.pi import blueprint_rules as br
from app.modules.pi import brain_docs, constitution
from app.modules.pi import problem_fields as pf

PROBLEMS = {"P1", "P2"}
OWNER = "Honestly we never count stock at night and the evening count is skipped"


def option(**over) -> bm.Option:
    base = {
        "id": "O1",
        "kind": "process_change",
        "what": "A short checklist would be agreed for the evening count",
        "addresses": ("P1",),
        "benefit": "The owner would see the same numbers every morning",
        "effort": "small",
        "reversibility": "reversible",
        "evidence": (verified("m1", ("count", "stock")),),
    }
    base.update(over)
    return bm.Option(**base)


def verified(msg, words=()):
    """An evidence ref that `verify_option` has already marked verified."""
    return bm.mark_verified(bm.Evidence(msg, tuple(words)))


def ev(msg, words=()):
    return verified(msg, words)


def codes(issues) -> list[str]:
    return [i.code for i in issues]


def ids(options) -> list[str]:
    return [o.id for o in options]


# --- the rules the design names, one test each ---


def test_a_clean_option_has_no_issue():
    assert br.option_issues(option(), PROBLEMS) == []


def test_every_option_links_to_a_stated_problem():
    assert "OPT-ADDR" in codes(br.option_issues(option(addresses=()), PROBLEMS))
    assert "OPT-ADDR" in codes(br.option_issues(option(addresses=("P9",)), PROBLEMS))
    assert "OPT-ADDR" in codes(br.option_issues(option(addresses=("P1", "P9")), PROBLEMS))
    assert "OPT-ADDR" not in codes(br.option_issues(option(addresses=("P1", "P2")), PROBLEMS))


@pytest.mark.parametrize(
    "text",
    [
        "It would cost Rs 450,000 to build",
        "About 40k for the first phase",
        "A fee of 5000 applies",
        "The price would be AED 900",
    ],
)
def test_no_money_in_any_text_field(text):
    for field in ("what", "benefit"):
        assert "OPT-MONEY" in codes(br.option_issues(option(**{field: text}), PROBLEMS))
    assert "OPT-MONEY" in codes(br.option_issues(option(limits=(text,)), PROBLEMS))
    assert "OPT-MONEY" in codes(br.option_issues(option(trade_offs=(text,)), PROBLEMS))
    risk = bm.Risk(text, "low")
    assert "OPT-MONEY" in codes(br.option_issues(option(risks=(risk,)), PROBLEMS))
    dep = bm.Dependency("data", text)
    assert "OPT-MONEY" in codes(br.option_issues(option(dependencies=(dep,)), PROBLEMS))


def test_a_year_or_a_count_is_not_money():
    assert br.option_issues(option(what="It would cover 4 shops since 2024"), PROBLEMS) == []


def test_the_cost_amount_is_never_filled_by_pi():
    paid = option(cost=bm.Cost("staff", "500"))  # type: ignore[arg-type]
    assert "OPT-COST" in codes(br.option_issues(paid, PROBLEMS))
    assert "OPT-COST" in codes(br.option_issues(option(cost=bm.Cost("pi", None)), PROBLEMS))
    assert "OPT-COST" not in codes(br.option_issues(option(cost=bm.Cost()), PROBLEMS))


@pytest.mark.parametrize(
    "text",
    [
        "This will fix the stock problem",
        "We guarantee the count is right",
        "It is risk-free and always works",
        "Sales will definitely increase",
    ],
)
def test_no_option_promises_a_result(text):
    assert "OPT-PROMISE" in codes(br.option_issues(option(benefit=text), PROBLEMS))
    assert "OPT-PROMISE" in codes(br.option_issues(option(what=text), PROBLEMS))
    assert "OPT-PROMISE" in codes(br.option_issues(option(trade_offs=(text,)), PROBLEMS))


def test_would_is_allowed_and_will_is_not():
    assert br.option_issues(option(benefit="It would help the morning check"), PROBLEMS) == []
    will = option(benefit="It will help the morning")
    assert "OPT-PROMISE" in codes(br.option_issues(will, PROBLEMS))
    assert br.option_issues(option(benefit="It will not replace the till"), PROBLEMS) == []


def test_the_owners_own_expected_outcome_is_their_words_not_pis_claim():
    words = "I want to double my sales, budget 500k"
    assert br.option_issues(option(expected_outcome=words), PROBLEMS) == []


def test_a_build_needs_a_catalogue_key():
    for kind in ("workzap_build", "custom_automation"):
        assert "OPT-CATALOGUE" in codes(br.option_issues(option(kind=kind), PROBLEMS))
        keyed = option(kind=kind, catalogue_key="stock_alerts")
        assert "OPT-CATALOGUE" not in codes(br.option_issues(keyed, PROBLEMS))
    assert "OPT-CATALOGUE" not in codes(br.option_issues(option(kind="owner_action"), PROBLEMS))


def test_a_kind_effort_status_or_reversibility_outside_the_lists_is_refused():
    for field, value in (
        ("kind", "magic"),
        ("effort", "huge"),
        ("reversibility", "maybe"),
        ("status", "winner"),
    ):
        assert "OPT-ENUM" in codes(br.option_issues(option(**{field: value}), PROBLEMS))


def test_a_rejected_option_names_its_reason():
    assert "OPT-REJECT" in codes(br.option_issues(option(status="rejected"), PROBLEMS))
    named = option(status="rejected", rejected_because="breaks the old till")
    assert "OPT-REJECT" not in codes(br.option_issues(named, PROBLEMS))
    assert "OPT-REJECT" in codes(br.option_issues(option(rejected_because="x reason"), PROBLEMS))


def test_a_violating_or_blocked_option_cannot_be_recommended():
    broken = bm.ConstraintCheck("cannot_change#1", "violates", "touches the till")
    blocked = bm.Dependency("access", "a login that is absent", blocking=True)
    violating = option(status="recommended", constraint_checks=(broken,))
    assert "OPT-RECOMMEND" in codes(br.option_issues(violating, PROBLEMS))
    waiting = option(status="recommended", dependencies=(blocked,))
    assert "OPT-RECOMMEND" in codes(br.option_issues(waiting, PROBLEMS))
    assert "OPT-RECOMMEND" not in codes(br.option_issues(option(status="alternative"), PROBLEMS))


def test_a_recommended_option_needs_evidence_unless_it_is_learn_first():
    bare = option(status="recommended", evidence=())
    assert "OPT-RECOMMEND" in codes(br.option_issues(bare, PROBLEMS))
    ask = option(status="recommended", kind="learn_first", evidence=())
    assert "OPT-RECOMMEND" not in codes(br.option_issues(ask, PROBLEMS))


def test_every_stated_constraint_has_a_check_even_if_unknown():
    view = bm.ConstraintsView(budget="ready", cannot_change=("keep the till",))
    issues = br.option_issues(option(), PROBLEMS, view=view)
    assert [i.detail for i in issues if i.code == "OPT-CHECKS"] == ["budget", "cannot_change#1"]
    checks = (bm.ConstraintCheck("budget", "ok"), bm.ConstraintCheck("cannot_change#1", "unknown"))
    checked = option(constraint_checks=checks)
    assert "OPT-CHECKS" not in codes(br.option_issues(checked, PROBLEMS, view=view))
    assert "OPT-CHECKS" not in codes(br.option_issues(option(), PROBLEMS))


def test_an_unconfirmed_cause_is_never_rendered_as_a_fact():
    cause = bm.RootCause("nobody owns the evening count")
    said = option(benefit="Because nobody owns the evening count, a checklist would help")
    hedged = option(benefit="If nobody owns the evening count, a checklist may help")
    assert "OPT-CAUSE-FACT" in codes(br.option_issues(said, PROBLEMS, cause=cause))
    assert "OPT-CAUSE-FACT" not in codes(br.option_issues(hedged, PROBLEMS, cause=cause))
    owner = bm.RootCause("nobody owns the evening count", status=pf.OWNER_SAID)
    assert "OPT-CAUSE-FACT" not in codes(br.option_issues(said, PROBLEMS, cause=owner))


def test_evidence_words_must_be_in_the_owners_own_message():
    assert "OPT-EVIDENCE" not in codes(br.option_issues(option(), PROBLEMS, owner_text=OWNER))
    bad = option(evidence=(verified("m1", ("refund", "policy")),))
    assert "OPT-EVIDENCE" in codes(br.option_issues(bad, PROBLEMS, owner_text=OWNER))
    empty = option(evidence=(verified("m1", ()),))
    assert "OPT-EVIDENCE" in codes(br.option_issues(empty, PROBLEMS, owner_text=OWNER))
    assert "OPT-EVIDENCE" in codes(br.option_issues(bad, PROBLEMS, owner_text=""))


# --- the set rules ---


def test_two_options_are_compared_unless_the_evidence_supports_only_one():
    one = bm.OptionSet(options=(option(),))
    assert "SET-COUNT" in codes(br.set_issues(one, PROBLEMS))
    flagged = bm.OptionSet(options=(option(),), single_option=True, single_reason="only this fits")
    assert "SET-COUNT" not in codes(br.set_issues(flagged, PROBLEMS))
    two = bm.OptionSet(options=(option(), option(id="O2")))
    assert "SET-COUNT" not in codes(br.set_issues(two, PROBLEMS))


def test_a_rejected_option_with_a_reason_counts_as_compared():
    rejected = option(id="O2", status="rejected", rejected_because="breaks the old till")
    both = bm.OptionSet(options=(option(), rejected))
    assert "SET-COUNT" not in codes(br.set_issues(both, PROBLEMS))


def test_the_single_option_flag_must_be_honest():
    lying = bm.OptionSet(
        options=(option(), option(id="O2")), single_option=True, single_reason="only one"
    )
    assert "SET-SINGLE" in codes(br.set_issues(lying, PROBLEMS))
    no_reason = bm.OptionSet(options=(option(),), single_option=True)
    assert "SET-SINGLE" in codes(br.set_issues(no_reason, PROBLEMS))


def test_an_empty_set_needs_a_reason():
    assert "SET-EMPTY" in codes(br.set_issues(bm.OptionSet(options=()), PROBLEMS))
    reasoned = bm.OptionSet(options=(), none_reason="nothing fits the stated limits")
    assert br.set_issues(reasoned, PROBLEMS) == []


def test_the_recommendation_is_the_first_of_the_ranking_and_only_one():
    a = option(id="O1", effort="medium", status="alternative")
    b = option(id="O2", effort="small", status="recommended")
    good = bm.OptionSet(options=(a, b), recommended_id="O2")
    assert "SET-RECOMMENDED" not in codes(br.set_issues(good, PROBLEMS))
    wrong = bm.OptionSet(options=(a, option(id="O2", effort="small")), recommended_id="O1")
    assert "SET-RECOMMENDED" in codes(br.set_issues(wrong, PROBLEMS))
    two = bm.OptionSet(
        options=(option(id="O1", status="recommended"), option(id="O2", status="recommended")),
        recommended_id="O1",
    )
    assert "SET-RECOMMENDED" in codes(br.set_issues(two, PROBLEMS))
    missing = bm.OptionSet(options=(a, b), recommended_id="O7")
    assert "SET-RECOMMENDED" in codes(br.set_issues(missing, PROBLEMS))


def test_thin_evidence_without_a_learn_first_option_is_flagged():
    thin = bm.OptionSet(options=(option(evidence=()), option(id="O2", evidence=())))
    assert "SET-THIN" in codes(br.set_issues(thin, PROBLEMS))
    ask = option(
        id="O3", kind="learn_first", effort="none", evidence=(), what="One question comes first"
    )
    with_ask = bm.OptionSet(options=(option(evidence=()), ask))
    assert "SET-THIN" not in codes(br.set_issues(with_ask, PROBLEMS))
    strong = bm.OptionSet(options=(option(), option(id="O2")))
    assert "SET-THIN" not in codes(br.set_issues(strong, PROBLEMS))


def test_set_issues_include_the_option_issues():
    bad = option(id="O2", addresses=("P9",))
    result = br.set_issues(bm.OptionSet(options=(option(), bad)), PROBLEMS)
    assert [(i.code, i.option_id) for i in result if i.code == "OPT-ADDR"] == [("OPT-ADDR", "O2")]


# --- ranking: smallest reliable first ---


def test_the_smallest_effort_comes_first():
    big = option(id="big", effort="large")
    mid = option(id="mid", effort="medium")
    small = option(id="small", effort="small")
    nothing = option(id="none", effort="none")
    assert ids(br.rank_options((big, mid, small, nothing))) == ["none", "small", "mid", "big"]


def test_reversible_comes_before_hard_at_the_same_effort():
    hard = option(id="hard", reversibility="hard")
    partly = option(id="partly", reversibility="partly")
    easy = option(id="easy", reversibility="reversible")
    assert ids(br.rank_options((hard, partly, easy))) == ["easy", "partly", "hard"]


def test_stronger_evidence_comes_first_at_the_same_effort_and_reversibility():
    weak = option(id="a", evidence=(verified("m1", ("count",)),))
    two = (verified("m1", ("count",)), verified("m2", ("night",)))
    strong = option(id="b", evidence=two)
    assert ids(br.rank_options((weak, strong))) == ["b", "a"]


def test_effort_outranks_reversibility_which_outranks_evidence():
    cheap_hard = option(id="cheap_hard", effort="small", reversibility="hard")
    dear_easy = option(id="dear_easy", effort="medium", reversibility="reversible")
    assert ids(br.rank_options((dear_easy, cheap_hard))) == ["cheap_hard", "dear_easy"]


def test_an_unknown_constraint_check_ranks_after_an_ok_one():
    unknown = option(
        id="unknown", effort="none", constraint_checks=(bm.ConstraintCheck("budget", "unknown"),)
    )
    ok = option(id="ok", effort="small", constraint_checks=(bm.ConstraintCheck("budget", "ok"),))
    assert ids(br.rank_options((unknown, ok))) == ["ok", "unknown"]


def test_a_violating_or_rejected_option_goes_last_whatever_its_score():
    violates = option(
        id="violates",
        effort="none",
        evidence=tuple(verified(f"m{i}", ("count",)) for i in range(5)),
        constraint_checks=(bm.ConstraintCheck("cannot_change#1", "violates"),),
    )
    rejected = option(id="rejected", effort="none", status="rejected", rejected_because="no")
    plain = option(id="plain", effort="large")
    assert ids(br.rank_options((violates, rejected, plain))) == ["plain", "violates", "rejected"]


def test_a_blocked_option_stays_visible_but_after_the_ready_ones():
    wait = (bm.Dependency("access", "login", True),)
    blocked = option(id="blocked", effort="none", dependencies=wait)
    ready = option(id="ready", effort="large")
    ranked = br.rank_options((blocked, ready))
    assert ids(ranked) == ["ready", "blocked"]
    assert not br.recommendable(blocked) and br.recommendable(ready)


def test_an_option_without_evidence_is_not_recommendable():
    assert not br.recommendable(option(evidence=()))
    assert br.recommendable(option(kind="learn_first", effort="none", evidence=()))


def test_a_build_without_a_catalogue_key_is_not_recommendable():
    assert not br.recommendable(option(kind="workzap_build"))
    assert br.recommendable(option(kind="workzap_build", catalogue_key="stock_alerts"))


def test_learn_first_leads_when_the_evidence_is_thin():
    ask = option(id="ask", kind="learn_first", effort="small", evidence=(), reversibility="hard")
    thin = option(id="thin", effort="none", evidence=())
    assert br.evidence_thin((ask, thin))
    assert ids(br.rank_options((thin, ask))) == ["ask", "thin"]


def test_learn_first_follows_the_reliable_options_when_the_evidence_is_strong():
    ask = option(id="ask", kind="learn_first", effort="none", evidence=())
    solid = option(id="solid", effort="medium")
    assert not br.evidence_thin((ask, solid))
    assert ids(br.rank_options((ask, solid))) == ["solid", "ask"]


def test_ranking_is_deterministic_and_does_not_mutate_its_input():
    a, b, c = option(id="a"), option(id="b"), option(id="c")
    first = br.rank_options((c, a, b))
    assert ids(first) == ["a", "b", "c"]
    assert ids(br.rank_options((b, c, a))) == ids(first)
    given = (c, a, b)
    br.rank_options(given)
    assert ids(given) == ["c", "a", "b"]


def test_the_ranking_order_is_documented():
    doc = br.rank_options.__doc__ or ""
    for word in ("effort", "reversib", "evidence", "learn_first", "unknown"):
        assert word in doc


# --- the root cause ---


def test_a_cause_the_owner_said_needs_the_owners_own_words():
    proof = (verified("m1", ("never", "count")),)
    said = bm.RootCause("we never count", status=pf.OWNER_SAID, evidence_for=proof)
    assert br.cause_issues(said, OWNER) == []
    bare = bm.RootCause("we never count", status=pf.OWNER_SAID)
    assert "CAUSE-UNSUPPORTED" in codes(br.cause_issues(bare, OWNER))
    wrong_proof = (verified("m1", ("refund",)),)
    wrong = bm.RootCause("x", status=pf.OWNER_SAID, evidence_for=wrong_proof)
    assert "CAUSE-UNSUPPORTED" in codes(br.cause_issues(wrong, OWNER))
    assert "CAUSE-UNSUPPORTED" in codes(br.cause_issues(said, ""))
    confirmed = bm.RootCause("x", status=pf.CONFIRMED)
    assert "CAUSE-UNSUPPORTED" in codes(br.cause_issues(confirmed, OWNER))


def test_a_pi_inferred_cause_needs_no_proof_but_is_never_stateable():
    guess = bm.RootCause("maybe nobody owns the count")
    assert br.cause_issues(guess, OWNER) == []
    assert not br.may_state_as_fact(guess, OWNER)


def test_a_cause_with_an_unknown_status_is_refused():
    assert "CAUSE-STATUS" in codes(br.cause_issues(bm.RootCause("x", status="certain"), OWNER))


def test_may_state_as_fact_needs_an_owner_status_and_proof():
    proof = (verified("m1", ("never", "count")),)
    assert br.may_state_as_fact(bm.RootCause("c", pf.OWNER_SAID, evidence_for=proof), OWNER)
    assert not br.may_state_as_fact(bm.RootCause("c", pf.OWNER_SAID), OWNER)
    assert not br.may_state_as_fact(bm.RootCause("c", pf.OWNER_SAID, evidence_for=proof), "")


def test_a_status_is_never_raised_without_the_owner_and_never_lowered():
    assert br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg=None) == pf.PI_INFERRED
    assert br.advance_status(pf.PI_INFERRED, pf.CONFIRMED, owner_msg="m1") == pf.OWNER_SAID
    assert br.advance_status(pf.PI_INFERRED, pf.OWNER_SAID, owner_msg="m1") == pf.OWNER_SAID
    assert br.advance_status(pf.OWNER_SAID, pf.CONFIRMED, owner_msg=None) == pf.OWNER_SAID
    assert br.advance_status(pf.OWNER_SAID, pf.CONFIRMED, owner_msg="m1") == pf.CONFIRMED
    assert br.advance_status(pf.OWNER_SAID, pf.PI_INFERRED, owner_msg=None) == pf.OWNER_SAID
    assert br.advance_status(pf.CONFIRMED, pf.PI_INFERRED, owner_msg="m1") == pf.CONFIRMED
    assert br.advance_status(pf.PI_INFERRED, "certain", owner_msg="m1") == pf.PI_INFERRED


# --- the patterns follow the production ones ---


def test_the_money_pattern_is_the_brain_docs_pattern():
    assert br.MONEY_IN_TEXT.pattern == brain_docs.MONEY_IN_TEXT.pattern
    assert br.MONEY_IN_TEXT.flags == brain_docs.MONEY_IN_TEXT.flags


def test_the_promise_pattern_is_the_constitutions():
    assert br.PROMISE is constitution.PROMISE


def test_every_rule_code_is_listed_and_unique():
    assert len(br.RULE_CODES) == len(set(br.RULE_CODES))
    for code in (
        "OPT-ADDR",
        "OPT-MONEY",
        "OPT-COST",
        "OPT-PROMISE",
        "OPT-CATALOGUE",
        "OPT-ENUM",
        "OPT-REJECT",
        "OPT-RECOMMEND",
        "OPT-CHECKS",
        "OPT-CAUSE-FACT",
        "OPT-EVIDENCE",
        "SET-COUNT",
        "SET-SINGLE",
        "SET-EMPTY",
        "SET-RECOMMENDED",
        "SET-THIN",
        "CAUSE-STATUS",
        "CAUSE-UNSUPPORTED",
    ):
        assert code in br.RULE_CODES
