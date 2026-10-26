import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.modules.pi_saas import nori_bridge

SECRET = "s3cret"
NUMBER_ID = "123456789"


def settings(**over):
    base = {
        "nori_bridge_url": "https://nori.test/api/workzap/inbound",
        "nori_bridge_secret": SecretStr(SECRET),
        "nori_bridge_phone_number_id": NUMBER_ID,
    }
    return SimpleNamespace(**{**base, **over})


def event(text="NORI-482913", kind="message", message_type="text"):
    return {
        "kind": kind,
        "message_type": message_type,
        "sender": "923001234567",
        "message_id": "wamid.1",
        "body": text,
        "profile": "Ali",
    }


def client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def run(handler, payload, cfg=None, number_id=NUMBER_ID):
    async with client(handler) as http:
        ctx = {"settings": cfg or settings(), "http": http}
        return await nori_bridge.try_handle(
            ctx, SimpleNamespace(phone_number_id=number_id), payload
        )


def test_sign_and_verify_round_trip():
    body = b'{"a":1}'
    assert nori_bridge.verify(SECRET, body, nori_bridge.sign(SECRET, body))
    assert not nori_bridge.verify(SECRET, body, nori_bridge.sign("other", body))
    assert not nori_bridge.verify(SECRET, body, "")


@pytest.mark.asyncio
async def test_handled_reply_is_returned_and_request_is_signed():
    seen = {}

    def handler(request):
        seen["sig"] = request.headers["x-workzap-signature"]
        seen["body"] = request.content
        return httpx.Response(200, json={"handled": True, "reply": "Connected to Demo."})

    assert await run(handler, event()) == (True, "Connected to Demo.")
    assert nori_bridge.verify(SECRET, seen["body"], seen["sig"])
    assert json.loads(seen["body"])["from"] == "923001234567"


@pytest.mark.asyncio
async def test_not_handled_passes_through_to_pi():
    def handler(request):
        return httpx.Response(200, json={"handled": False, "reply": None})

    assert await run(handler, event("hello")) == (False, None)


@pytest.mark.asyncio
async def test_other_number_or_non_text_never_calls_nori():
    def handler(request):
        raise AssertionError("must not be called")

    assert await run(handler, event(), number_id="999") == (False, None)
    assert await run(handler, event(message_type="image")) == (False, None)
    assert await run(handler, event(kind="status")) == (False, None)
    assert await run(handler, event(), cfg=settings(nori_bridge_url="")) == (False, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["down", "500", "garbage"])
async def test_outage_fails_open_but_a_code_is_never_given_to_the_brain(failure):
    def handler(request):
        if failure == "down":
            raise httpx.ConnectError("no")
        if failure == "500":
            return httpx.Response(500)
        return httpx.Response(200, content=b"not json")

    assert await run(handler, event("hello there")) == (False, None)
    handled, reply = await run(handler, event("my code NORI-482913"))
    assert handled and reply == nori_bridge.RETRY_TEXT
