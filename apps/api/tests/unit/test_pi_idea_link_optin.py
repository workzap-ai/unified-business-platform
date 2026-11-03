"""G12 (spec v1.5, 18.4) is opt-in: `with_idea_link` turns it on, and the live path calls it
only for a workspace that sets `response_rules.brain.idea_link` to exactly true."""

import inspect

from app.modules.pi import idea_filter, service_conversation

IDEA = "Ask three parents who paid late last month what made them late."
SAID = "fees come in late from many parents"
NODE = {"title": "Late fees", "user_words": ["fees come in late"], "group": "cash_collections"}


def test_without_the_switch_an_idea_with_no_problem_is_not_stopped() -> None:
    assert "G12" not in idea_filter.failures(IDEA, SAID, None)
    assert "G12" not in idea_filter.failures(IDEA, SAID, idea_filter.IdeaContext())


def test_with_the_switch_an_idea_with_no_problem_fails_g12() -> None:
    ctx = idea_filter.with_idea_link(None)
    assert ctx is not None and ctx.needs_problem
    assert "G12" in idea_filter.failures(IDEA, SAID, ctx)


def test_with_the_switch_an_idea_passes_once_a_problem_is_on_the_map() -> None:
    base = idea_filter.context_from([NODE], SAID, [], [], [])
    ctx = idea_filter.with_idea_link(base)
    assert ctx is not None and ctx.nodes
    assert "G12" not in idea_filter.failures(IDEA, SAID, ctx)


def test_the_switch_keeps_the_rest_of_the_context() -> None:
    base = idea_filter.IdeaContext(industries=("school",), resources="two teachers")
    ctx = idea_filter.with_idea_link(base)
    assert ctx is not None
    assert ctx.industries == ("school",) and ctx.resources == "two teachers"


def test_the_live_path_reads_only_exactly_true() -> None:
    source = inspect.getsource(service_conversation)
    assert '.get("idea_link") is True' in source  # not truthiness: "true" or 1 stay off
