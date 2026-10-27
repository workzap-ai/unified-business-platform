"""G9 (platform spec v1.4, 17.4): an idea uses the owner's trade's own words."""

from app.modules.pi import idea_filter, idea_vocabulary, industry_packs, solutions

CEMENT = "cement_blocks_pavers_and_precast"


def test_breakdown_call_is_not_a_locksmith_or_cement_word() -> None:
    idea = "Give every customer one breakdown call line so you answer them first."
    assert idea_vocabulary.foreign_terms(idea, "", [CEMENT]) == ["breakdown call"]
    assert idea_vocabulary.foreign_vocabulary(idea, "", [CEMENT]) == "G9"


def test_the_owner_may_use_the_word_themselves() -> None:
    idea = "Give every customer one breakdown call line so you answer them first."
    assert idea_vocabulary.foreign_terms(idea, "mera breakdown call ka kaam hai", [CEMENT]) == []


def test_no_known_trade_nothing_to_compare() -> None:
    assert idea_vocabulary.foreign_terms("One breakdown call line.", "", []) == []


def test_the_filter_runs_g9_only_with_a_trade() -> None:
    idea = "Give every customer one breakdown call line."
    ctx = idea_filter.IdeaContext(industries=(CEMENT,))
    assert "G9" in idea_filter.failures(idea, "", ctx)
    assert "G9" not in idea_filter.failures(idea, "", None)


def test_a_trades_own_spoken_ideas_rarely_trip_g9() -> None:
    bad = total = 0
    for key in industry_packs.load_packs():
        entry = solutions.load(key) or {}
        for problem in entry.get("problems") or []:
            for idea in problem.get("quick_ideas") or []:
                total += 1
                bad += bool(idea_vocabulary.foreign_terms(str(idea), "", [key]))
    assert total > 1000 and bad / total < 0.02
