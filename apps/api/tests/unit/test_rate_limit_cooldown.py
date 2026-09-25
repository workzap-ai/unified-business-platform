from types import SimpleNamespace

from app.core import rate_limit


class FailingRedis:
    calls = 0

    async def incr(self, key: str) -> int:
        FailingRedis.calls += 1
        raise ConnectionError("down")


async def test_redis_failure_fails_open_and_backs_off():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=FailingRedis())))
    assert await rate_limit.hit(request, "login", "k", 1, 60) is True  # type: ignore[arg-type]
    assert await rate_limit.hit(request, "login", "k", 1, 60) is True  # type: ignore[arg-type]
    assert FailingRedis.calls == 1  # second call skipped Redis during the cooldown
