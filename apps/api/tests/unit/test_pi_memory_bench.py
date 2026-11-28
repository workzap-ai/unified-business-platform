"""The memory harness as a test: every case must pass, and the old order must visibly fail some."""

from pi_memory_bench import CASES, run

from app.modules.pi import memory_rank, shared_memory


def test_every_memory_case_passes_with_ranking() -> None:
    failed = [case.name for case, ranked, _old, _size in run() if not ranked]
    assert not failed, failed


def test_the_harness_can_see_the_problem_it_is_for() -> None:
    """If the fixed order passed everything the cases would prove nothing."""
    rows = run()
    assert sum(1 for _c, _new, old, _s in rows if not old) >= 4


def test_the_block_stays_inside_its_cap() -> None:
    assert all(size <= shared_memory.CAP_CHARS + 200 for _c, _n, _o, size in run())


def test_no_query_keeps_the_given_order() -> None:
    records = [
        {"text": "b one", "status": "owner_said"},
        {"text": "a two", "status": "pi_inferred"},
    ]
    assert memory_rank.order(records, "") == records
    assert memory_rank.order(records, "the and of") == records  # only stop words: nothing to match


def test_stems_join_plural_and_tense() -> None:
    assert memory_rank.tokens("Orders delivered") == memory_rank.tokens("order delivering")


def test_ranking_never_changes_or_invents_a_record() -> None:
    case = CASES[0]
    ranked = memory_rank.order(case.records, case.query)
    assert all(r in case.records for r in ranked)
    assert len(ranked) <= len(case.records)


def test_a_relevant_record_far_down_survives_the_record_limit() -> None:
    records = [
        {"text": f"filler number {i} about nothing", "status": "owner_said"} for i in range(80)
    ]
    records.append({"text": "the gate code is changed on sundays", "status": "owner_said"})
    block = shared_memory.from_context(
        {"memory": {"known": records}}, query="when is the gate changed"
    )
    assert any("gate code" in r["text"] for r in block["records"])
