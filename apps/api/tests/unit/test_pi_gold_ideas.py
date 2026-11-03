"""The owner-approved gold ideas (28 problems of 28 trades, two ideas each, written 2026-10-26) are
the few-shot examples and the reference for judging pi's own ideas in independent mode. Every one
must pass the same checks pi applies to its own ideas, so an example never teaches a rule break."""

import json
from pathlib import Path

from app.modules.pi import solution_rules as rules

GOLD = json.loads(
    (Path(rules.__file__).parent / "packs" / "library" / "gold_ideas.json").read_text(
        encoding="utf-8"
    )
)


def test_the_gold_set_covers_many_trades_with_two_ideas_each():
    assert len(GOLD) >= 28 and all(len(item["ideas"]) == 2 for item in GOLD)
    assert len({item["industry"] for item in GOLD}) >= 28


def test_every_gold_idea_passes_the_idea_checks():
    bad = []
    for item in GOLD:
        for idea in item["ideas"]:
            verdict = rules.check_idea(idea, item["problem"])
            if verdict.reject or verdict.review or not rules.is_owner_action(idea):
                bad.append(idea[:60])
            assert len(idea.split()) <= 28
    assert not bad, bad
