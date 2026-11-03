"""The evaluation kit must catch real faults (negative controls), split stably, and refuse to call a
thin group "passing"."""

from app.modules.pi.evalkit import replay, report, scorers, splits

CASE = {
    "id": "t1",
    "industry": "x",
    "language": "en",
    "messages": ["Stock is about 10 crore on paper. Cash in and out do not match."],
    "expected": {
        "problems": [
            {"id": "p1", "any": ["stock", "paper"], "figures": ["10 crore"]},
            {"id": "p2", "any": ["cash", "match"], "figures": []},
        ],
        "corrections": [],
        "hypothesis_only": ["stock and cash are one problem"],
    },
}
GOOD = [
    {"title": "Stock of 10 crore on paper", "user_words": ["Stock is about 10 crore on paper"]},
    {"title": "Cash does not match", "user_words": ["Cash in and out do not match"]},
]


def test_a_complete_answer_scores_full() -> None:
    s = scorers.score_case(CASE, GOOD)
    assert s["recall"] == s["precision"] == 1.0 and s["figures_kept"] == s["figures"] == 1


def test_a_dropped_problem_lowers_recall() -> None:
    assert scorers.score_case(CASE, GOOD[:1])["recall"] == 0.5


def test_an_invented_problem_lowers_precision() -> None:
    extra = [*GOOD, {"title": "Customers are unhappy", "user_words": ["unhappy customers"]}]
    s = scorers.score_case(CASE, extra)
    assert s["extra"] == 1 and s["precision"] < 1.0


def test_a_lost_figure_is_caught() -> None:
    lost = [{"title": "Stock kept on paper", "user_words": ["stock on paper"]}, GOOD[1]]
    s = scorers.score_case(CASE, lost)
    assert s["figures"] == 1 and s["figures_kept"] == 0


def test_a_confirmed_cause_the_owner_never_said_is_flagged() -> None:
    bad = [
        {**GOOD[0], "cause": "stock and cash are one problem", "cause_status": "confirmed"},
        GOOD[1],
    ]
    assert scorers.score_case(CASE, bad)["unsupported_causes"]
    hypothesis = [
        {**GOOD[0], "cause": "stock and cash are one problem", "cause_status": "hypothesis"},
        GOOD[1],
    ]
    assert not scorers.score_case(CASE, hypothesis)["unsupported_causes"]


def test_a_correction_must_replace_the_old_value() -> None:
    case = {
        **CASE,
        "expected": {
            "problems": [{"id": "p1", "any": ["client"]}],
            "corrections": [{"wrong": "10", "right": "100", "problem": "p1"}],
        },
        "messages": ["lost 10 clients", "not 10, 100"],
    }
    right = [{"title": "Lost 100 clients", "user_words": ["lost 100 clients"]}]
    wrong = [{"title": "Lost 10 clients", "user_words": ["lost 10 clients"]}]
    both = [{"title": "Lost clients", "user_words": ["lost 10 then 100 clients"]}]
    assert scorers.score_case(case, right)["corrections_applied"] == 1
    assert scorers.score_case(case, wrong)["corrections_applied"] == 0
    assert scorers.score_case(case, both)["corrections_applied"] == 0


def test_the_split_is_stable_and_regression_cases_stay_regression() -> None:
    assert splits.split_of({"id": "abc"}) == splits.split_of({"id": "abc"})
    assert splits.split_of({"id": "abc", "regression": True}) == splits.REGRESSION
    shares = [splits.split_of({"id": f"case-{i}"}) for i in range(400)]
    held = shares.count(splits.HELD_OUT) / 400
    assert 0.15 < held < 0.35


def test_a_thin_group_is_not_measured() -> None:
    one = [scorers.score_case(CASE, GOOD)]
    assert scorers.aggregate(one)["measured"] is False
    assert scorers.aggregate(one * scorers.MIN_CASES)["measured"] is True


def test_the_shipped_cases_replay_without_a_model_and_every_group_is_labelled() -> None:
    cases = replay.load_cases(str(report.CASES))
    assert len(cases) >= 30 and {c["id"] for c in cases} >= {"reg_audit5_four_lines"}
    text, totals = report.build(cases)
    assert "not yet measured" in text  # groups under three cases are never called passing
    assert totals["split:development"]["recall"] >= 0.95


def test_the_dataset_keeps_twenty_industries_with_three_cases_and_a_stable_split() -> None:
    cases = replay.load_cases(str(report.CASES))
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)) and len(cases) >= 60
    by_industry: dict[str, int] = {}
    for c in cases:
        by_industry[c["industry"]] = by_industry.get(c["industry"], 0) + 1
    real = {k: v for k, v in by_industry.items() if k != "unknown_business_owner"}
    # The first round put three cases through each of 20 industries; the Held-out expansion added
    # one case for each of many more industries, so only the original 20 are asked to have three.
    assert len([k for k, v in real.items() if v >= 3]) >= 20
    sets = {c["id"]: splits.split_of(c) for c in cases}
    assert {s for s in sets.values()} == {splits.DEVELOPMENT, splits.REGRESSION, splits.HELD_OUT}
    assert all(sets[c["id"]] == splits.REGRESSION for c in cases if c.get("regression"))
    assert any(
        c["id"] == "reg_correction_figure" for c in cases
    )  # the 10 -> 100 fault stays guarded
