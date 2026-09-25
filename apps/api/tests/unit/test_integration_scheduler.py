import asyncio

from app.core.jobs import InlineQueue


async def test_inline_sweeper_recovers_after_failure_and_stops_on_close(monkeypatch, settings):
    from app.integrations import jobs

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
    try:
        await asyncio.wait_for(recovered.wait(), timeout=2)
    finally:
        await queue.close()
    assert calls >= 2
    assert queue.sweeper.done()


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
