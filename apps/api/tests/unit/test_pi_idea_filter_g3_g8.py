# ruff: noqa: E501
"""Idea filter G3 (sub-type), G4 (cause-fit), G7 (new), G8 (on the map), platform spec Book 5, 7.1,
and retrieval by (industry, sub-type, goal verb, known cause), 7.3. Examples are the spec's chat 3."""

from types import SimpleNamespace
from typing import Any

from app.modules.pi import idea_filter, idea_retrieval, solution_free

STOCK = "mera clothing brand hai mere baby and male cloths hain 6crore ka stock wo bechna hai"
CLEARING = {
    "title": "Stock to clear",
    "title_local": "6 crore ka stock bechna hai",
    "user_words": ["6crore ka stock wo bechna hai"],
    "group": "stock_inventory",
    "subtype": "overstock_ageing",
    "goal_verb": "sell_clear",
    "cause": "",
}
AGE_IDEA = "Count the whole stock by age and speed of sale, so the oldest part leaves first."
OLD_CUSTOMERS = "Tell earlier customers about the sale first, so they hear before anyone new does."


def ctx(**kw: Any) -> idea_filter.IdeaContext:
    noted = kw.pop("noted", [CLEARING])
    return idea_filter.context_from(noted, kw.pop("said", STOCK), **kw)


# --- G3 ------------------------------------------------------------------------------------------


def test_a_stock_sync_idea_fails_for_a_stock_clearing_problem() -> None:
    idea = "Keep the warehouse and outlet stock counts in step, so both always show the same sets."
    assert idea_filter.wrong_subtype(idea, "overstock_ageing") == "G3"
    assert idea_filter.failures(idea, STOCK, ctx()) == ["G3"] or "G3" in idea_filter.failures(
        idea, STOCK, ctx()
    )


def test_an_idea_for_the_problems_own_subtype_passes_g3() -> None:
    assert idea_filter.wrong_subtype(AGE_IDEA, "overstock_ageing") is None


def test_an_entry_idea_always_passes_g3() -> None:
    own = "Reorder the fast sellers when they run low, so the shelf is never bare."
    assert idea_filter.wrong_subtype(own, "overstock_ageing") == "G3"
    assert idea_filter.wrong_subtype(own, "overstock_ageing", [own]) is None


def test_g3_does_nothing_when_the_subtype_is_unknown() -> None:
    assert idea_filter.wrong_subtype("Keep the counts in step across outlets.", "") is None


# --- G4 ------------------------------------------------------------------------------------------


def test_g4_a_known_cause_must_be_the_one_the_idea_assumes() -> None:
    price = "Mark down the oldest sets a little, so price stops being the reason they sit."
    redesign = "Restyle the old designs with a new look, so they feel current again."
    assert idea_filter.cause_misfit(price, "design purane ho gaye") == "G4"
    assert idea_filter.cause_misfit(redesign, "design purane ho gaye") is None
    assert idea_filter.cause_misfit(price, "qeemat zyada hai") is None


def test_g4_unknown_cause_allows_only_ideas_that_help_whatever_the_cause_is() -> None:
    price = "Mark down the oldest sets a little, so they finally move."
    assert idea_filter.cause_misfit(price, "") == "G4"
    assert idea_filter.cause_misfit(AGE_IDEA, "") is None  # a robust idea (spec 7.5)
    test_one = "Test one offer in one outlet before doing it everywhere, so you see what works."
    assert idea_filter.cause_misfit(test_one, "") is None


def test_g4_idea_with_no_assumed_cause_passes() -> None:
    assert idea_filter.cause_misfit(OLD_CUSTOMERS, "") is None


# --- G7 ------------------------------------------------------------------------------------------


def test_g7_a_reworded_idea_already_given_fails() -> None:
    again = "Count all the stock by age and by speed of sale, so the oldest part goes first."
    assert idea_filter.repeats(again, [AGE_IDEA]) == "G7"
    assert idea_filter.repeats(OLD_CUSTOMERS, [AGE_IDEA]) is None
    assert idea_filter.repeats(again, []) is None


def test_g7_catches_it_inside_an_earlier_reply() -> None:
    reply = f"Bilkul. Do ideas abhi:\n• {AGE_IDEA}\n• {OLD_CUSTOMERS}"
    assert idea_filter.repeats(AGE_IDEA, [reply]) == "G7"


# --- G8 ------------------------------------------------------------------------------------------


def test_g8_an_idea_for_a_problem_the_owner_never_raised_is_dropped() -> None:
    rota = "Write the weekly rota for the counter staff on one page, so shifts never clash."
    nodes = ["Stock to clear 6 crore ka stock bechna hai"]
    assert idea_filter.off_the_map(rota, nodes, ["stock_inventory"], "sell_clear") == "G8"


def test_g8_ideas_on_the_stock_node_pass() -> None:
    nodes = ["Stock to clear 6 crore ka stock bechna hai"]
    assert idea_filter.off_the_map(AGE_IDEA, nodes, ["stock_inventory"], "sell_clear") is None
    # the second idea of the spec's own chat 3 relates through the goal, not through a shared word
    assert idea_filter.off_the_map(OLD_CUSTOMERS, nodes, ["stock_inventory"], "sell_clear") is None


def test_g8_without_a_map_there_is_nothing_to_judge_by() -> None:
    assert idea_filter.off_the_map("Anything at all about rotas.", []) is None


# --- the spec's own chat 3 through the whole filter ------------------------------------------------


def test_chat_3_two_ideas_pass_g1_to_g8() -> None:
    context = ctx(
        said=STOCK + ". qeemat zyada hai shayad, aur design purane ho gaye. 30% sale lagayi"
    )
    assert idea_filter.failures(AGE_IDEA, STOCK, context) == []
    assert idea_filter.failures(OLD_CUSTOMERS, STOCK, context) == []


def test_chat_3_bad_ideas_fail_with_their_rule() -> None:
    context = ctx()
    assert "G1" in idea_filter.failures("Keep a buffer of the fast sellers back.", STOCK, context)
    assert "G2" in idea_filter.failures("Plan online launches for the new designs.", STOCK, context)
    sync = "Keep the stock counts of the warehouse and the outlets in step, so sets are never double sold."
    assert "G3" in idea_filter.failures(sync, STOCK, context)


def test_failures_without_a_context_are_g1_and_g2_only() -> None:
    sync = "Keep the stock counts of the warehouse and the outlets in step, so sets are never double sold."
    assert idea_filter.failures(sync, STOCK) == []
    assert idea_filter.failures(sync, STOCK, idea_filter.IdeaContext()) == []


# --- vetted and the fallback ----------------------------------------------------------------------


def test_vetted_applies_the_whole_filter_and_reports() -> None:
    sync = "Keep the stock counts of the warehouse and the outlets in step, so sets are never double sold."
    price = "Mark down the oldest sets a little, so old stock finally moves for customers."
    report: dict[str, Any] = {}
    kept = solution_free.vetted(
        [sync, price, AGE_IDEA], STOCK, [], {"stock", "sets", "count", "oldes"}, ctx(), report
    )
    assert kept == [AGE_IDEA]
    assert report["filtered"] == 2 and {"G3", "G4"} <= set(report["rules"])


def test_vetted_with_no_context_behaves_as_before() -> None:
    sync = "Keep the stock counts of the warehouse and the outlets in step, so sets are never double sold."
    assert solution_free.vetted([sync], STOCK, [], {"stock", "sets"}) == [sync.rstrip(".") + "."]


def test_the_need_a_fact_line_is_one_question_and_last_with_no_solution_words() -> None:
    for line in (idea_filter.NEED_FACT_CAUSE, idea_filter.NEED_FACT_SINCE):
        assert line.count("?") == 1 and line.endswith("?")
        assert line.index("?") > line.rindex(". ")  # the question is the last sentence
        low = line.lower()
        assert not any(w in low for w in ("solution", "idea", "quote", "document", "offer", "pay"))
    assert idea_filter.need_fact_line(ctx()) == idea_filter.NEED_FACT_CAUSE
    assert idea_filter.need_fact_line(ctx(noted=[{**CLEARING, "cause": "design"}])) == (
        idea_filter.NEED_FACT_SINCE
    )


async def test_pi_asks_one_question_when_the_filter_removes_every_idea() -> None:
    from app.modules.pi.service_conversation import brain_free_ideas

    class Manager:
        async def complete(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                text='{"ideas": ["Keep a buffer of the fast sellers back, so you never run short of sets.",'
                ' "Keep the stock counts of the warehouse and the outlets in step, so sets are not double sold."]}'
            )

    conversation = SimpleNamespace(id=None, service_brief={})
    turn = SimpleNamespace(
        reply="",
        _summary=False,
        _decision=None,
        request_human=False,
        awaiting_customer=False,
        _free=False,
        _english=False,
    )
    policy = SimpleNamespace(response_rules={"pi_mode": "brain"}, ai_config={})
    context = {
        "solution_asked_no_ideas": True,
        "latest_customer_message": "solution dein ap",
        "noted_problems": [CLEARING],
        "history": [{"role": "customer", "text": STOCK}, {"role": "ai", "text": "Hi, I am pi."}],
    }
    await brain_free_ideas(Manager(), None, conversation, policy, turn, context)  # type: ignore[arg-type]
    assert turn.reply == idea_filter.NEED_FACT_CAUSE and turn._free and turn.awaiting_customer
    assert conversation.service_brief == {}  # no idea was given


# --- retrieval ------------------------------------------------------------------------------------

ENTRIES = [
    {
        "id": "p1",
        "subtype": "no_visibility",
        "category": "stock_inventory",
        "words": "stock count wrong",
    },
    {
        "id": "p2",
        "subtype": "overstock_ageing",
        "category": "stock_inventory",
        "words": "old stock not selling",
        "quick_ideas": ["Offer the old sets at a lower price, so qeemat stops being the reason"],
    },
    {
        "id": "p3",
        "subtype": "overstock_ageing",
        "category": "stock_inventory",
        "words": "dead stock",
        "quick_ideas": ["Restyle old designs with a new look, so they feel current"],
    },
]


def test_goal_verb_sorts_the_problem_over_the_models_own_subtype() -> None:
    assert idea_retrieval.target_subtype("no_visibility", STOCK) == (
        "overstock_ageing",
        "sell_clear",
    )
    assert idea_retrieval.target_subtype("no_visibility", "kuch masla hai") == ("no_visibility", "")


def test_retrieval_prefers_the_entry_of_the_subtype_and_known_cause() -> None:
    found = idea_retrieval.preferred_entry(ENTRIES, "no_visibility", STOCK, "design purane ho gaye")
    assert found is not None and found[0]["id"] == "p3"
    found = idea_retrieval.preferred_entry(ENTRIES, "no_visibility", STOCK, "qeemat zyada hai")
    assert found is not None and found[0]["id"] == "p2"


def test_retrieval_falls_back_when_nothing_is_keyed() -> None:
    assert idea_retrieval.preferred_entry(ENTRIES, "no_visibility", "kuch masla hai", "") is None
    assert idea_retrieval.preferred_entry(ENTRIES, "", "kuch masla hai", "design") is None
    assert idea_retrieval.key_rank(ENTRIES[1], "overstock_ageing", "", "") == 0
