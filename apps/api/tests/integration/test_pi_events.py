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
    assert recorder.sent == []
    assert (await api.post(f"{url}/takeover")).json()["mode"] == "human"
    assert recorder.sent == [
        (live_events.channel(UUID(pi.tenant_id), UUID(pi.environment_id)), "inbox")
    ]
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
    assert len(on.sent) >= 1 and {kind for _, kind in on.sent} == {"inbox"}
    assert len(await pi.outbound()) > replies_off  # the reply is produced exactly as before
    before = len(on.sent)
    await pi.deliver_all()
    assert len(on.sent) > before  # a reply that went out signals too
    pi.ctx["redis"] = Recorder(fail=True)
    await pi.process("and once more", "wamid.ev-fail")  # a broken Redis never breaks a message
    await pi.close()
