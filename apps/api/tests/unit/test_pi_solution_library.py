# ruff: noqa: E501
"""The generic Solution Library: two ideas when no industry entry has any (platform spec Book 2 7.4)."""

from types import SimpleNamespace

from app.modules.pi import solution_context, solution_library


def _chat(brief: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(service_brief=brief or {}, flow_state="S3_NOTED", language="en")


def test_the_library_is_parsed_and_every_idea_passes_the_idea_guard() -> None:
    from app.modules.pi import solution_rules

    library = solution_library.load()
    assert len(library) == 18
    for key, entry in library.items():
        for idea in entry["ideas"]:
            verdict = solution_rules.check_idea(idea)
            assert not verdict.reject and not verdict.review, (key, idea)


def test_a_category_with_no_idea_that_passes_the_guard_has_none() -> None:
    assert len(solution_library.ideas_for("margin_cost")) == 2  # the owner rewrote its three ideas
    assert solution_library.ideas_for("no_such_category") == []


def test_two_ideas_not_yet_given_and_never_a_repeat() -> None:
    first = solution_library.ideas_for("people_staff")
    assert len(first) == 2
    second = solution_library.ideas_for("people_staff", first)
    assert len(second) == 2 and not set(first) & set(second)
    given = first + second
    while more := solution_library.ideas_for("people_staff", given):
        assert not set(more) & set(given)  # never a repeat, until the category has none left
        given += more
    assert len(given) >= 4 and solution_library.ideas_for("people_staff", given) == []


def test_an_unknown_industry_with_a_noted_problem_gets_two_ideas_and_the_build_line() -> None:
    chat = _chat()
    noted = [{"group": "people_staff", "title": "Staff late", "subtype": "attendance_lateness"}]
    out = solution_context._from_library(chat, noted, "en")
    assert out is not None and len(out["solution_ideas"]) == 2 and out["solution_asked"] is True
    assert out["solution_build"]["says"]  # said only from the catalogue
    assert chat.service_brief["ideas_given"] == 2
    again = solution_context._from_library(chat, noted, "en")
    assert again is not None and not set(out["solution_ideas"]) & set(again["solution_ideas"])
    for _ in range(4):  # the budget is eight (Book 5 decision 5), two per message
        if solution_context._from_library(chat, noted, "en") is None:
            break
    spent = solution_context._from_library(chat, noted, "en")
    assert spent is None  # the budget or the library is used up: the honest line follows
    assert 4 <= chat.service_brief["ideas_given"] <= 8


def test_a_category_without_library_ideas_degrades_to_the_honest_line() -> None:
    chat = _chat()
    noted = [{"group": "no_such_category", "title": "Something odd happens"}]
    assert solution_context._from_library(chat, noted, "en") is None


def test_nothing_noted_means_no_library_ideas() -> None:
    assert solution_context._from_library(_chat(), [], "en") is None


def test_the_latest_problem_with_library_ideas_is_used() -> None:
    chat = _chat()
    noted = [
        {"group": "people_staff", "title": "Staff late"},
        {"group": "no_such_category", "title": "Something odd happens"},
    ]
    out = solution_context._from_library(chat, noted, "en")
    assert out is not None and chat.service_brief["solution_last_problem"] == "library:people_staff"


def _builder():  # noqa: ANN202
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "build_generic_library.py"
    spec = importlib.util.spec_from_file_location("build_generic_library", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_every_library_idea_is_what_to_do_so_the_benefit_in_one_short_plain_sentence() -> None:
    import re

    from app.modules.pi import constitution

    time_words = re.compile(
        r"\b(?:today|tomorrow|tonight|daily|weekly|monthly|this week|next week|every "
        r"(?:day|week|monday|month)|each week|per week|within a day|an hour|overnight)\b",
        re.IGNORECASE,
    )
    for key, entry in solution_library.load().items():
        for idea in entry["ideas"]:
            assert ", so " in idea and len(idea.split()) <= 28, (key, idea)
            assert not time_words.search(idea), (key, idea)
            assert not constitution.TIMELINE_STRONG.search(idea.lower()), (key, idea)


def test_the_owner_rewrites_survive_a_rebuild_from_the_spec_text() -> None:
    builder = _builder()
    spec_text = (
        "Library by category\n"
        "Paperwork (compliance_admin)\n"
        "Quick ideas: keep a calendar of every licence, renewal and filing date · keep documents in one "
        "folder by month.\n"
        "Workzap would build: workflow_automation (reminders, document checklists).\n"
        "Never say: what the law requires.\n"
        "Part 8 Deep playbook\n"
    )
    rebuilt = builder.build(spec_text)["categories"]["compliance_admin"]["ideas"]  # type: ignore[index]
    assert rebuilt == [
        "Keep documents in one shared folder by month on your phone, so nothing is hunted for later."
    ]
    assert "owner" in builder.build(spec_text)["source"]  # type: ignore[operator]


def test_the_overlay_names_the_deviation_from_the_spec() -> None:
    import json
    from pathlib import Path

    data = json.loads(
        (Path(solution_library.LIBRARY).parent / "owner_rewrites.json").read_text(encoding="utf-8")
    )
    assert "not verbatim" in data["note"] and len(data["rewrites"]) == 54


def test_the_owner_added_fashion_entry_is_loaded_and_is_not_in_the_pdf_pack() -> None:
    import json

    from app.modules.pi import solution_ideas, solutions

    pack = solutions.SOLUTIONS_DIR / "fashion_and_apparel_brands.json"
    from_pdf = {p["id"] for p in json.loads(pack.read_text(encoding="utf-8"))["problems"]}
    assert "x1_price_asked_then_silence" not in from_pdf  # a rebuild of the packs cannot erase it
    loaded = {p["id"]: p for p in solutions.load("fashion_and_apparel_brands")["problems"]}  # type: ignore[index]
    entry = loaded["x1_price_asked_then_silence"]
    overlay = json.loads(
        (solutions.OVERLAY_DIR / "fashion_and_apparel_brands.json").read_text(encoding="utf-8")
    )
    assert "NOT from the PDF" in overlay["note"]
    found = solution_ideas.match_problem(
        list(loaded.values()),
        "sales_revenue",
        "conversion_low",
        "roz 30-40 log price poochte hain DM mein, price bata deta hoon to reply hi nahi aata",
    )
    assert found is not None and found["id"] == entry["id"]


def test_every_idea_of_the_owner_added_entry_passes_the_guard_and_is_an_owner_action() -> None:
    from app.modules.pi import solution_rules, solutions

    entry = {p["id"]: p for p in solutions.load("fashion_and_apparel_brands")["problems"]}[  # type: ignore[index]
        "x1_price_asked_then_silence"
    ]
    ideas = [*entry["quick_ideas"], *[e["text"] for e in entry["extra_ideas"]]]
    assert len(ideas) == 4
    for idea in ideas:
        verdict = solution_rules.check_idea(idea)
        assert not verdict.reject and not verdict.review, idea
        assert solution_rules.is_owner_action(idea), idea


def test_a_free_idea_may_talk_about_a_price_but_not_set_one() -> None:
    from app.modules.pi import solution_free

    talk = "Send a clear photo and the size chart with the price, so they need not ask again."
    setting = "Lower your prices a little on slow items, so they sell."
    assert solution_free.vetted([talk], "price asked in DM", []) == [talk]
    assert solution_free.vetted([setting], "price asked in DM", []) == []
