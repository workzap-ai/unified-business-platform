"""Live inbox signals on the disposable database: the ticket and the stream endpoint (with a fake
Redis, no network), and that the publish hooks never change what a message, a reply or a staff
action does. Run only through scripts/pi-test-env.sh."""

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from test_pi_pipeline import intent, pi_workspace, scripted_gateway

from app.modules.pi import events_routes, live_events

pytestmark = pytest.mark.integration

TICKET = "/api/v1/pi/events/ticket"
STREAM = "/api/v1/pi/events/stream"


class Recorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def publish(self, name: str, data: str) -> int:
        if self.fail:
            raise ConnectionError("redis is down")
        self.sent.append((name, data))
        return 1

    async def enqueue_job(self, *args: Any, **kwargs: Any) -> None:
        return None  # the worker's ctx["redis"] is also the job queue


class FakePubSub:
    def __init__(self, messages: list[bytes]) -> None:
        self.messages, self.subscribed, self.closed = list(messages), [], False

    async def subscribe(self, name: str) -> None:
        self.subscribed.append(name)

    async def get_message(self, **kwargs: Any) -> Any:
        if self.messages:
            return {"type": "message", "data": self.messages.pop(0)}
        await asyncio.sleep(0.01)
        return None

    async def aclose(self) -> None:
        self.closed = True


class FakeRedis:
    def __init__(self, messages: list[bytes]) -> None:
        self.ps = FakePubSub(messages)

    def pubsub(self) -> FakePubSub:
        return self.ps

    async def exists(self, key: str) -> int:
        return 1


def turn_on(pi: Any) -> None:
    pi.app.state.settings.pi_events_enabled = True


async def test_the_ticket_says_disabled_until_the_flag_is_on(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    assert (await api.post(TICKET)).json() == {"enabled": False}
    assert (await api.get(STREAM, params={"ticket": "x"})).status_code == 204
    turn_on(pi)
    body = (await api.post(TICKET)).json()
    assert body["enabled"] is True and body["expires_in"] == live_events.TICKET_SECONDS
    await pi.close()


async def test_the_stream_refuses_a_bad_ticket_and_needs_a_ticket(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    turn_on(pi)
    assert (await api.get(STREAM, params={"ticket": "not-a-ticket"})).status_code == 401
    assert (await api.get(STREAM)).status_code == 422
    await pi.close()


async def test_a_ticket_opens_a_stream_for_its_own_workspace_only(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    turn_on(pi)
    fake = FakeRedis([b"inbox"])
    monkeypatch.setattr(events_routes, "events_client", lambda request: fake)
    original = live_events.stream

    def short(redis: Any, tenant: UUID, environment: UUID, **kw: Any) -> Any:
        return original(redis, tenant, environment, max_seconds=0.3)

    monkeypatch.setattr(live_events, "stream", short)
    ticket = (await api.post(TICKET)).json()["ticket"]
    response = await api.get(STREAM, params={"ticket": ticket})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: ready" in response.text and "event: change" in response.text
    assert fake.ps.subscribed == [live_events.channel(UUID(pi.tenant_id), UUID(pi.environment_id))]
    assert fake.ps.closed
    # the body never names a chat, a person or a number
    assert "conversation" not in response.text and pi.tenant_id not in response.text
    await pi.close()


async def test_a_person_over_the_stream_cap_gets_busy_not_a_connection(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    turn_on(pi)
    monkeypatch.setattr(events_routes, "events_client", lambda request: FakeRedis([]))
    ticket = (await api.post(TICKET)).json()["ticket"]
    _, _, person = live_events.read_ticket(pi.app.state.settings, ticket)  # type: ignore[misc]
    for _ in range(live_events.MAX_PER_USER):
        assert live_events.acquire(person)
    try:
        response = await api.get(STREAM, params={"ticket": ticket})
        assert "event: busy" in response.text and "event: ready" not in response.text
    finally:
        for _ in range(live_events.MAX_PER_USER):
            live_events.release(person)
    await pi.close()


async def test_a_staff_action_publishes_and_a_redis_failure_changes_nothing(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await pi.process("hello", "wamid.ev-1")
    chat = await pi.conversation()
    turn_on(pi)
    recorder = Recorder()
    pi.app.state.redis = recorder
    url = f"/api/v1/pi/conversations/{chat.id}/actions"
    assert (await api.post(f"{url}/read")).status_code == 200  # reading is not news
    await live_events.drain()
    assert recorder.sent == []
    assert (await api.post(f"{url}/takeover")).json()["mode"] == "human"
    await live_events.drain()
    [(name, data)] = recorder.sent
    assert name == live_events.channel(UUID(pi.tenant_id), UUID(pi.environment_id))
    assert live_events.split_signal(data)[0] == "inbox"
    pi.app.state.redis = Recorder(fail=True)  # Redis down: the action still works
    assert (await api.post(f"{url}/return-to-ai")).json()["mode"] == "ai"
    await pi.close()


async def test_a_message_and_its_reply_are_unchanged_and_signal_when_on(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    off = Recorder()
    pi.ctx["redis"] = off
    await pi.process("hello", "wamid.ev-off")  # flag off: nothing is published
    assert off.sent == []
    replies_off = len(await pi.outbound())
    turn_on(pi)
    on = Recorder()
    pi.ctx["redis"] = on
    await pi.process("hello again", "wamid.ev-on")
    await live_events.drain()
    assert len(on.sent) >= 1 and {live_events.split_signal(data)[0] for _, data in on.sent} == {
        "inbox"
    }
    assert len(await pi.outbound()) > replies_off  # the reply is produced exactly as before
    before = len(on.sent)
    await pi.deliver_all()
    await live_events.drain()
    assert len(on.sent) > before  # a reply that went out signals too
    pi.ctx["redis"] = Recorder(fail=True)
    await pi.process("and once more", "wamid.ev-fail")  # a broken Redis never breaks a message
    await live_events.drain()
    await pi.close()


class PipeRecorder(Recorder):
    """A Recorder that also takes the pipeline calls the timing samples use."""

    def __init__(self) -> None:
        super().__init__()
        self.ops: list[tuple[Any, ...]] = []

    def pipeline(self) -> Any:
        parent = self
        queued: list[tuple[Any, ...]] = []

        class Pipe:
            def lpush(self, key: str, value: str) -> "Pipe":
                queued.append(("lpush", key, value))
                return self

            def ltrim(self, key: str, start: int, stop: int) -> "Pipe":
                queued.append(("ltrim", key, start, stop))
                return self

            def expire(self, key: str, seconds: int) -> "Pipe":
                queued.append(("expire", key, seconds))
                return self

            async def execute(self) -> list[Any]:
                parent.ops.extend(queued)
                return []

        return Pipe()

    async def exists(self, key: str) -> int:
        return 1

    async def lrange(self, key: str, start: int, stop: int) -> list[bytes]:
        return [op[2].encode() for op in self.ops if op[0] == "lpush"]


async def test_the_speed_report_times_a_real_reply_and_holds_no_text_or_ids(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await pi.process("hello there", "wamid.speed-1")
    await pi.deliver_all()
    response = await api.get("/api/v1/pi/events/speed", params={"hours": 24})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replies"]["replies"] >= 1 and body["replies"]["with_send_timing"] >= 1
    total = body["replies"]["total_s"]
    assert total is not None and 0 <= total["p50"] <= total["p90"] <= total["max"]
    stages = body["replies"]["stages_s"]
    assert {"thinking", "queue_to_sender", "send_checks", "whatsapp_call"} <= set(stages)
    assert "sending" not in stages  # replaced by the two parts it was made of
    assert body["live"]["enabled"] is False  # the flag is off here
    assert "hello there" not in response.text and pi.tenant_id not in response.text
    assert (await api.get("/api/v1/pi/events/speed", params={"hours": 0})).status_code == 422
    assert (await api.get("/api/v1/pi/events/speed", params={"hours": 999})).status_code == 422
    await pi.close()


async def test_a_timing_sample_is_kept_only_when_live_events_are_on_and_must_be_numbers(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    store = PipeRecorder()
    pi.app.state.redis = store
    url = "/api/v1/pi/events/timing"
    assert (await api.post(url, json={"lag_ms": 40, "screen_ms": 700})).status_code == 204
    assert store.ops == []  # off: nothing is kept
    turn_on(pi)
    assert (await api.post(url, json={"lag_ms": 40, "screen_ms": 700})).status_code == 204
    assert [op[0] for op in store.ops] == ["lpush", "ltrim", "expire"]
    assert (await api.post(url, json={"lag_ms": -1, "screen_ms": 5})).status_code == 422
    assert (await api.post(url, json={"lag_ms": 1, "screen_ms": 5, "name": "x"})).status_code == 422
    live = (await api.get("/api/v1/pi/events/speed")).json()["live"]
    assert live["enabled"] and live["publishing"] and live["samples"] == 1
    assert live["total_ms"]["max"] == 740
    await pi.close()


async def test_the_queue_stage_is_the_workers_wait_not_the_turns_own_time(
    api: httpx.AsyncClient, business_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    pi = await pi_workspace(api, business_db)
    scripted_gateway(monkeypatch, lambda text: intent("greeting", 1.0))
    await pi.process("hello there", "wamid.queue-1")
    pi.ctx["enqueue_time"] = datetime.now(UTC) - timedelta(seconds=3)  # arq: queued 3 s ago
    await pi.deliver_all()
    stages = (await api.get("/api/v1/pi/events/speed")).json()["replies"]["stages_s"]
    assert 3 <= stages["queue_to_sender"]["p50"] < 10
    assert stages["whatsapp_call"]["p50"] <= stages["send_checks"]["p50"] + 5
    await pi.close()
