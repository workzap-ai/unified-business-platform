import pytest

from app.modules.pi import taxonomy


@pytest.mark.parametrize(
    ("said", "verb", "category", "subtype"),
    [
        ("6 crore ka stock bechna hai", "sell_clear", "stock_inventory", "overstock_ageing"),
        ("I need to clear my old stock", "sell_clear", "stock_inventory", "overstock_ageing"),
        ("Stock ka hisaab nahi milta", "know_track", "stock_inventory", "no_visibility"),
        ("I cannot track my stock", "know_track", "stock_inventory", "no_visibility"),
        ("Maal kam ho jata hai", "avoid_running_out", "stock_inventory", "stockout"),
        ("we keep running out of stock", "avoid_running_out", "stock_inventory", "stockout"),
        ("Customers wapas nahi aate", "bring_back", "customers_retention", "repeat_low"),
        ("my customers don't come back", "bring_back", "customers_retention", "repeat_low"),
        ("Recovery nahi aati", "collect_cash", "cash_collections", "receivables_late"),
        ("I can't collect payments", "collect_cash", "cash_collections", "receivables_late"),
    ],
)
def test_goal_sort_examples(said: str, verb: str, category: str, subtype: str) -> None:
    sort = taxonomy.goal_sort(said)
    assert sort is not None
    assert (sort.goal_verb, sort.category, sort.subtype) == (verb, category, subtype)
    assert sort.goal_verb in taxonomy.GOAL_VERBS
    assert taxonomy.is_master_subtype(sort.category, sort.subtype)


def test_clearance_has_secondary_sort() -> None:
    sort = taxonomy.goal_sort("6 crore ka stock bechna hai")
    assert sort is not None
    assert sort.secondary == ("sales_revenue", "clearance")
    assert taxonomy.is_master_subtype("sales_revenue", "clearance")


def test_no_match_is_none() -> None:
    assert taxonomy.goal_sort("") is None
    assert taxonomy.goal_sort("the weather is nice") is None


def test_new_subtypes_and_links() -> None:
    assert taxonomy.is_master_subtype("stock_inventory", "overstock_ageing")
    assert taxonomy.is_master_subtype("stock_inventory", "overstock_dead_stock")
    for kept in ("same_root_suspected", "causes", "same_area", "blocks"):
        assert kept in taxonomy.LINK_TYPES
    for added in ("worsens", "competes", "same_root", "symptom_of"):
        assert added in taxonomy.LINK_TYPES
