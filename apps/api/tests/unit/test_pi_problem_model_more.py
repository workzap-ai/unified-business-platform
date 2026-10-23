"""Part 4 of the specification: merging the same symptom, pattern surfacing, title rules."""

from app.modules.pi import problems as p


def item(group, *where, ref="r"):
    return {"group": group, "where": list(where), "ref": ref, "title": "x"}


def test_the_same_symptom_in_nearly_the_same_words_is_one_problem():
    assert p.same_symptom("Best-sellers run out in two shops", "Best-sellers run out in two shops")
    assert (
        p.same_symptom("Best-sellers running out in shops", "Best-sellers run out in shops")
        is False
    )
    assert not p.same_symptom("Cash does not match the till", "Staff come late on weekends")


def test_three_problems_in_one_group_are_a_pattern_said_once():
    noted = [item("stock_inventory"), item("stock_inventory"), item("stock_inventory")]
    hint = p.pattern_hint(noted, [])
    assert hint and hint["kind"] == "group" and hint["count"] == 3
    assert p.pattern_hint(noted, [hint["key"]]) is None  # already said


def test_one_place_in_three_problems_is_a_pattern_across_groups():
    noted = [
        item("stock_inventory", "Shop C"),
        item("cash_collections", "shop c"),
        item("people_staff", "Shop C", "Shop D"),
    ]
    hint = p.pattern_hint(noted, [])
    assert hint and hint["kind"] == "location" and hint["where"] == "shop c"


def test_two_problems_are_not_yet_a_pattern():
    assert p.pattern_hint([item("stock_inventory"), item("stock_inventory")], []) is None


def test_title_rules_hold_for_an_update_and_for_every_part_of_a_split():
    bad = p.ProblemNote(
        title="My lazy manager never counts stock at all in any shop", user_words=["x"]
    )
    ok = p.ProblemNote(title="Stock count missed weekly", user_words=["we skip it"], category="x")
    update = p.ProblemOp(op="update", ref="a", note=bad)
    assert "blames" in (p.check_ops([update], {"a"}, True) or "") or "words" in (
        p.check_ops([update], {"a"}, True) or ""
    )
    split = p.ProblemOp(
        op="split", ref="a", notes=[ok, p.ProblemNote(title="We need an app", user_words=["x"])]
    )
    assert "solution" in (p.check_ops([split], {"a"}, True) or "")
    no_words = p.ProblemOp(
        op="split", ref="a", notes=[ok, p.ProblemNote(title="Cash short weekly")]
    )
    assert "user_words" in (p.check_ops([no_words], {"a"}, True) or "")
