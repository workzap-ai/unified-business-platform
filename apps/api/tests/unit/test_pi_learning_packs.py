"""Drafting industry packs for unknown trades: clustering, checks, matching (spec 8.5, 8.6)."""

from types import SimpleNamespace as Row

from app.modules.pi import learning_packs as packs


def test_five_different_businesses_make_a_cluster_and_four_do_not():
    rows = [(f"c{i}", "falconry") for i in range(5)]
    assert list(packs.clusters(rows)) != []
    assert packs.clusters(rows[:4]) == {}


def test_one_customer_counted_five_times_is_not_five_businesses():
    assert packs.clusters([("c1", "falconry")] * 6) == {}


def test_labels_with_numbers_links_or_names_are_not_learned_from():
    assert packs.clean_text("falconry equipment") == "falconry equipment"
    assert packs.clean_text("call 0300 1234567") is None
    assert packs.clean_text("see www.example.com") is None
    assert packs.clean_text("my email is a@b.com") is None


def test_a_question_must_be_one_plain_question_without_prices_or_cards():
    assert packs.one_question("Which birds take most of your time?") is not None
    assert packs.one_question("Which birds? And how many?") is None
    assert packs.one_question("What is your card number?") is None
    assert packs.one_question("What do you charge, what is the price?") is None
    assert packs.one_question("Tell me about your birds") is None


def draft(**over):
    base = {
        "name": "Falconry equipment suppliers",
        "signals": ["hood", "jess", "mews", "lure", "telemetry", "bird feed"],
        "vocabulary": {"Mews": "where the birds are housed"},
        "questions": {"stock": ["Which items run out first?"]},
        "problems": [
            {"category": "stock_inventory", "subtype": "stockout", "phrase": "feed runs out"},
            {"category": "not_a_category", "subtype": "", "phrase": "dropped"},
        ],
        "shape_facts": ["Number of birds served"],
        "care": ["Never give animal welfare advice"],
        "scope_rule": "pi notes how the shop runs and refuses welfare advice.",
    }
    return packs.PackDraft(**{**base, **over})


def test_a_good_draft_is_kept_and_unknown_categories_are_dropped():
    content = packs.validated(draft())
    assert content is not None and content["key"] == "falconry_equipment_suppliers"
    assert [p["category"] for p in content["problems"]] == ["stock_inventory"]


def test_a_draft_with_too_few_signals_or_no_questions_is_refused():
    assert packs.validated(draft(signals=["hood"])) is None
    assert packs.validated(draft(questions={"stock": ["Tell me more"]})) is None


def test_a_draft_with_personal_data_loses_those_lines():
    content = packs.validated(
        draft(signals=["hood", "jess", "mews", "lure", "telemetry", "call 03001234567"])
    )
    assert content is not None and "call 03001234567" not in content["signals"]


def test_a_pack_matches_when_two_of_its_signals_appear():
    pack = Row(content=packs.validated(draft()))
    assert packs.matches(pack, "I sell hoods and jesses and the mews are full")
    assert not packs.matches(pack, "I sell shoes")
    assert not packs.matches(pack, "only a hood here")
