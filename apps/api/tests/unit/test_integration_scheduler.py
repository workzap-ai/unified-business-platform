import asyncio

from app.core.jobs import InlineQueue

# A guard against a hang, never what a test measures: a loaded machine can be many times slower.
GUARD_SECONDS = 60

PI_SWEEPS = (
    "sweep_pi",
    "sweep_followups",
    "sweep_customer_journeys",
    "sweep_pi_saas",
    "sweep_pi_calendar",
    "sweep_pi_campaigns",
    "sweep_pi_digests",
)


async def test_inline_sweeper_recovers_after_failure_and_stops_on_close(monkeypatch, settings):
    # The sweeper imports these on its first pass and then runs the knowledge sweep and seven PI
    # sweeps before the sweep under test. Import them here, outside the guard, and make those
    # sweeps no-ops, so the only thing in the first pass is the integrations sweep this test is
    # about, and how fast a loaded machine runs the rest cannot decide the result.
    from app.integrations import jobs
    from app.modules.pi import knowledge_jobs
    from app.worker import JOB_FUNCTIONS

    async def nothing(ctx):
        return None

    monkeypatch.setattr(knowledge_jobs, "sweep_knowledge", nothing)
    for name in PI_SWEEPS:
        monkeypatch.setitem(JOB_FUNCTIONS, name, nothing)

    calls = 0
    recovered = asyncio.Event()

    async def sweep(ctx):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary test failure")
        recovered.set()

    monkeypatch.setattr(jobs, "integrations_sweep", sweep)
    queue = InlineQueue(settings, None, None)
    queue.start_sweeper(interval=0.01)
    waiter = asyncio.create_task(recovered.wait())
    try:
        # wait for the second sweep, or for the sweeper to end (a sweeper that died on the failed
        # first sweep must fail this test at once, not after the guard)
        await asyncio.wait(
            {waiter, queue.sweeper}, timeout=GUARD_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
        assert recovered.is_set(), "the sweeper did not run again after a failed sweep"
        assert not queue.sweeper.done()  # it kept going after the failure
    finally:
        waiter.cancel()
        await asyncio.wait_for(queue.close(), timeout=GUARD_SECONDS)
    assert calls >= 2
    assert queue.sweeper.done()  # and close() stopped it


async def test_completed_inline_job_can_be_enqueued_again(monkeypatch, settings):
    from app.worker import JOB_FUNCTIONS

    calls = []

    async def work(ctx):
        calls.append(True)

    monkeypatch.setitem(JOB_FUNCTIONS, "test_repeat", work)
    queue = InlineQueue(settings, None, None)
    await queue.enqueue("test_repeat", job_id="same")
    await queue.enqueue("test_repeat", job_id="same")
    await queue.drain()
    assert len(calls) == 1
    await queue.enqueue("test_repeat", job_id="same")
    await queue.close()
    assert len(calls) == 2 and not queue.seen
