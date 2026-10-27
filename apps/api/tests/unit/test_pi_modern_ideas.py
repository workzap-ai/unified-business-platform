"""The owner's 30 modern ideas (docs/pi-saas/pi-modern-ideas.md) are in the generic library by
category with stable ids, pass the reply rules, come first when they fit as well as an older idea,
and never hide the spec's own ideas."""

import json

from app.modules.pi import solution_free, solution_library, solution_lint


def test_all_thirty_ideas_are_loaded_and_pass_the_reply_rules() -> None:
    items = [i for v in solution_library.modern().values() for i in v]
    assert len(items) == 30
    assert len({i["id"] for i in items}) == 30
    for item in items:
        assert solution_lint.passes(item["text"]), item["id"]
        assert item["category"] in solution_library.load(), item["id"]


def test_a_modern_idea_is_chosen_for_the_problem_it_fits() -> None:
    got = solution_library.ideas_for("loss_security", [], 2, "raat ko stock kam nikalta hai chori")
    modern = [i["text"] for i in solution_library.modern()["loss_security"]]
    assert got[0] in modern and got[1] in modern
    rate = solution_library.ideas_for(
        "sales_revenue", [], 2, "price asked in DM then silence raqam"
    )
    assert any("rate" in idea for idea in rate)


def test_the_specs_own_ideas_are_still_served_when_the_modern_ones_are_given() -> None:
    modern = [i["text"] for i in solution_library.modern()["loss_security"]]
    rest = solution_library.ideas_for("loss_security", modern, 2)
    spec = (solution_library.load()["loss_security"]).get("ideas") or []
    assert rest and all(idea in spec for idea in rest)


def test_a_modern_idea_has_a_stable_id_learning_can_score() -> None:
    first = solution_library.modern()["sales_revenue"][0]
    assert solution_library.idea_id("sales_revenue", first["text"]) == first["id"]
    spec = (solution_library.load()["stock_inventory"]).get("ideas")[0]
    assert solution_library.idea_id("stock_inventory", spec) == "library:stock_inventory:1"


def test_the_file_is_what_the_builder_reads_from_the_owners_document() -> None:
    data = json.loads(solution_library.MODERN.read_text(encoding="utf-8"))
    assert len(data["ideas"]) == 30


def test_the_free_idea_prompt_is_modern_without_assuming_what_the_owner_never_said() -> None:
    rules = solution_free.RULES
    # a channel is used only when the owner named it; the modern angle is a check or a question
    assert "use their word" in rules and "ASSUMES ONLY" in rules.upper()
    assert "how they first heard" in rules and "search for it nearby" in rules
    assert "short video caption" not in rules  # the old example was copied into a showroom chat
