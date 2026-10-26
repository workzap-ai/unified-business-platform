"""The owner's rewrites of industry quick ideas (packs/solutions_overlay/idea_rewrites.json):
keyed by the spec's own sentence, applied by solutions.load (so a rebuild of the packs keeps
them), free of time words inside advice, and a hard-blocked idea is never picked."""

import json

from app.modules.pi import solution_lint, solutions

FILE = solutions.OVERLAY_DIR / "idea_rewrites.json"
DATA = json.loads(FILE.read_text(encoding="utf-8"))["rewrites"]


def pack_ideas(industry: str) -> list[str]:
    path = solutions.SOLUTIONS_DIR / f"{industry}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [t for p in raw["problems"] for t in p.get("quick_ideas") or []]


def test_every_rewrite_is_keyed_by_a_sentence_of_its_industry_pack() -> None:
    for industry, changes in DATA.items():
        have = pack_ideas(industry)
        for original in changes:
            assert original in have, (industry, original)


def test_load_applies_the_rewrites_and_keeps_every_problem() -> None:
    for industry, changes in DATA.items():
        raw = json.loads((solutions.SOLUTIONS_DIR / f"{industry}.json").read_text(encoding="utf-8"))
        loaded = solutions.load(industry)
        assert loaded is not None
        assert [p["id"] for p in loaded["problems"]][: len(raw["problems"])] == [
            p["id"] for p in raw["problems"]
        ]
        served = [t for p in loaded["problems"] for t in p.get("quick_ideas") or []]
        for original, new in changes.items():
            assert new in served and original not in served, (industry, original)


def test_a_rewrite_survives_a_rebuild_because_it_is_applied_at_load() -> None:
    solutions.load.cache_clear()
    solutions.idea_rewrites.cache_clear()
    industry, changes = next(iter(DATA.items()))
    loaded = solutions.load(industry)
    assert loaded is not None
    served = [t for p in loaded["problems"] for t in p.get("quick_ideas") or []]
    assert all(new in served for new in changes.values())


def test_a_rewritten_idea_passes_the_reply_rules_and_a_blocked_one_is_not_picked() -> None:
    for changes in DATA.values():
        for new in changes.values():
            assert solution_lint.passes(new), new
    assert not solution_lint.passes("Name who may give a discount, so there is one rule.")
    assert solution_lint.passes("Ask staff to send a photo of each delivery note, so none is lost.")


def test_no_seed_idea_breaks_the_time_word_or_tool_rules_when_pi_says_it() -> None:
    from app.modules.pi import constitution
    from app.modules.pi.solution_ask import OFFER_AFTER

    ratchet = {"R-HONEST-01", "R-VOICE-06", "R-META-01"}
    bad = []
    for industry in solutions.industries():
        for problem in (solutions.load(industry) or {}).get("problems") or []:
            for idea in solutions.ideas(industry, problem):
                if idea.extra:
                    continue
                reply = (
                    f"Here are two ideas you can try now:\n\n• {idea.text}\n\n{OFFER_AFTER['en']}"
                )
                context = {
                    "pi_mode": "brain",
                    "flow": {"state": "S5_READINESS"},
                    "reply_language": "en",
                    "history": solution_lint.HISTORY,
                    "solution_asked": True,
                }
                rules = {v.rule for v in constitution.lint(reply, context) if v.hard}
                if rules & ratchet:
                    bad.append((industry, idea.text[:60], rules & ratchet))
    assert bad == [], bad[:5]
