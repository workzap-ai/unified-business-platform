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
    assert solution_library.ideas_for("margin_cost") == []  # every spec idea there fails the guard
    assert solution_library.ideas_for("no_such_category") == []


def test_two_ideas_not_yet_given_and_never_a_repeat() -> None:
    first = solution_library.ideas_for("people_staff")
    assert len(first) == 2
    second = solution_library.ideas_for("people_staff", first)
    assert len(second) == 2 and not set(first) & set(second)
    assert solution_library.ideas_for("people_staff", first + second) == []


def test_an_unknown_industry_with_a_noted_problem_gets_two_ideas_and_the_build_line() -> None:
    chat = _chat()
    noted = [{"group": "people_staff", "title": "Staff late", "subtype": "attendance_lateness"}]
    out = solution_context._from_library(chat, noted, "en")
    assert out is not None and len(out["solution_ideas"]) == 2 and out["solution_asked"] is True
    assert out["solution_build"]["says"]  # said only from the catalogue
    assert chat.service_brief["ideas_given"] == 2
    again = solution_context._from_library(chat, noted, "en")
    assert again is not None and not set(out["solution_ideas"]) & set(again["solution_ideas"])
    spent = solution_context._from_library(chat, noted, "en")
    assert spent is None  # the chat's idea budget is used up: the honest line follows


def test_a_category_without_library_ideas_degrades_to_the_honest_line() -> None:
    chat = _chat()
    noted = [{"group": "margin_cost", "title": "Margin unknown"}]
    assert solution_context._from_library(chat, noted, "en") is None


def test_nothing_noted_means_no_library_ideas() -> None:
    assert solution_context._from_library(_chat(), [], "en") is None


def test_the_latest_problem_with_library_ideas_is_used() -> None:
    chat = _chat()
    noted = [
        {"group": "people_staff", "title": "Staff late"},
        {"group": "margin_cost", "title": "Margin unknown"},
    ]
    out = solution_context._from_library(chat, noted, "en")
    assert out is not None and chat.service_brief["solution_last_problem"] == "library:people_staff"
