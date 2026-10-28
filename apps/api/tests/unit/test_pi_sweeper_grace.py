"""Found 2026-10-28 (webhook events: attempts = 2 on every turn that took over 30 s): the sweeper
re-enqueued an event a worker was still processing, so each model turn ran twice."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects import postgresql

from app.modules.pi import runtime


def sql(now: datetime) -> str:
    compiled = runtime.due_events(now).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return str(compiled)


def test_an_event_is_due_only_after_the_grace_period() -> None:
    now = datetime(2026, 10, 28, 5, 0, 0, tzinfo=UTC)
    text = sql(now)
    cutoff = now - timedelta(seconds=runtime.EVENT_GRACE_SECONDS)
    assert "updated_at <" in text and cutoff.strftime("%Y-%m-%d %H:%M:%S") in text
    assert "attempts < 3" in text and "'received'" in text and "'queued'" in text


def test_the_grace_outlasts_a_slow_turn_and_stays_inside_the_job_timeout() -> None:
    assert runtime.EVENT_GRACE_SECONDS >= 90  # a turn takes up to about a minute
    assert runtime.EVENT_GRACE_SECONDS < 180  # the worker's job_timeout: a stuck job is retried
