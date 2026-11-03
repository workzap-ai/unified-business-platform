# ruff: noqa: E501
"""The ideas added to Part 4 after the seed (extra_ideas): vetted, additive, never replacing a seed."""

import collections

from app.modules.pi import solution_rules, solutions


def _all():
    for key in solutions.industries():
        for problem in (solutions.load(key) or {})["problems"]:
            yield key, problem


def test_the_seed_ideas_are_untouched_except_the_entries_that_had_none_usable() -> None:
    replaced = 0
    for _key, problem in _all():
        if "quick_ideas_original" in problem:
            replaced += 1
            assert not any(solution_rules.check_idea(t).ok for t in problem["quick_ideas_original"])
            assert all(solution_rules.check_idea(t).ok for t in problem["quick_ideas"])
    assert replaced == 8


def test_every_problem_has_a_usable_idea_now() -> None:
    for key, problem in _all():
        usable = [i for i in solutions.ideas(key, problem) if solution_rules.check_idea(i.text).ok]
        assert usable, (key, problem["id"])


def test_an_extra_idea_passes_the_guard_or_waits_for_a_person() -> None:
    extras = 0
    for key, problem in _all():
        for idea in (i for i in solutions.ideas(key, problem) if i.extra):
            extras += 1
            # judged as it was written: a word the owner said first (their own tool) is allowed
            verdict = solution_rules.check_idea(idea.text, problem["words"])
            assert not verdict.reject, (key, idea.arm_id, verdict.reject)
            if verdict.review:
                assert idea.review, (
                    key,
                    idea.arm_id,
                )  # a regulated topic is never served unreviewed
    assert extras > 4000


def test_extras_get_their_own_stable_arm_ids_and_two_per_problem() -> None:
    for key, problem in _all():
        ids = [i.arm_id for i in solutions.ideas(key, problem)]
        assert len(ids) == len(set(ids))
        extra = [i for i in ids if i.rsplit(":", 1)[1].startswith("x")]
        assert len(extra) in (0, 2), (key, problem["id"])


def test_the_new_ideas_do_not_all_end_the_same_way() -> None:
    endings = collections.Counter()
    total = 0
    for key, problem in _all():
        for idea in (i for i in solutions.ideas(key, problem) if i.extra):
            total += 1
            endings[" ".join(idea.text.rstrip(".").split()[-3:]).lower()] += 1
    assert endings.most_common(1)[0][1] < total * 0.03
