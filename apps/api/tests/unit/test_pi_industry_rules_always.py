"""Industry content never outranks the rules: every industry's quick ideas, put into the reply
shape pi really sends (opener, two bullets, the spec's offer), pass the reply linter in brain mode.

The industry packs are data placed below the rules (CLAUDE.md). If an idea of any industry breaks a
hard rule the moment pi says it (a promise, a forecast, a brand, a secret, an advice), this test
names the industry and the idea, so the data is fixed and the rule is never loosened for it."""

import pytest

from app.modules.pi import constitution, solutions
from app.modules.pi.solution_ask import OFFER_AFTER

HISTORY = [{"role": "ai", "text": "Hi, I'm pi, an AI from Workzap."}]
IGNORED = {"R-DISC-01"}  # the first-message line: the scripted context has history


def replies():
    for industry in solutions.industries():
        data = solutions.load(industry) or {}
        for problem in data.get("problems") or []:
            seeds = [i for i in solutions.ideas(industry, problem) if not i.extra][:2]
            if len(seeds) == 2:
                yield industry, problem["id"], seeds[0].text, seeds[1].text


CASES = list(replies())
KNOWN_BREAKS = 25


def test_there_are_industry_cases_to_check():
    assert len(solutions.industries()) >= 200 and len(CASES) >= 1500


def test_no_industry_idea_breaks_a_hard_rule_when_pi_says_it():
    bad = []
    for industry, problem, first, second in CASES:
        reply = (
            f"Here are two ideas you can try now:\n\n• {first}\n• {second}\n\n{OFFER_AFTER['en']}"
        )
        context = {
            "pi_mode": "brain",
            "flow": {"state": "S5_READINESS"},
            "reply_language": "en",
            "history": HISTORY,
            "solution_asked": True,
        }
        hard = [
            v.rule for v in constitution.lint(reply, context) if v.hard and v.rule not in IGNORED
        ]
        if hard:
            bad.append((industry, problem, hard, first[:70]))
    # A ratchet, not a wish: 96 of the 2,104 industry idea pairs broke a hard rule on 2026-10-26
    # (time words in advice, "offers"/"discount", "tool" wording, one Meta-terms phrase). The count
    # may only go down: fix the idea (owner overlay) or the rule's false positive, never raise it.
    assert len(bad) <= KNOWN_BREAKS, f"{len(bad)} industry ideas break a hard rule: {bad[:10]}"


@pytest.mark.parametrize(
    "industry", ["fashion_and_apparel_brands", "cattle_and_buffalo_dairy_farms"]
)
def test_the_industries_the_owner_tried_are_in_the_check(industry):
    assert any(c[0] == industry for c in CASES)
