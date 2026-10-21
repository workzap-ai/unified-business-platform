"""pi Customer: the WhatsApp code, then the face (real face engine) or an optional
fingerprint. Adding either needs a fresh code; the code alone never signs in someone
who saved one; wrong tries lock the step and the count resets after success."""

import time

import httpx
import pytest
from fastapi import Response
from test_face_sign_in import frames
from test_passkeys import Authenticator

from app.modules.pi_customer import access
from app.modules.pi_customer.access import MemoryCodeStore

pytestmark = pytest.mark.integration

PI_ORIGIN = "http://localhost:3200"
PORTAL = "/api/v1/pi-app/customer-portal"
PHONE = "15550007101"


@pytest.fixture
def app(api):
    from pi_saas_support import FakeProvider, configure

    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    app.state.pi_customer_codes = MemoryCodeStore()
    return app


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"origin": PI_ORIGIN},
    )


def _signed_in(app, phone: str = PHONE, *, age_seconds: int = 0) -> httpx.AsyncClient:
    """A customer whose WhatsApp code was entered `age_seconds` ago."""
    response = Response()
    original = access.time.time
    access.time.time = lambda: original() - age_seconds  # type: ignore[assignment]
    try:
        access.issue(response, app.state.settings, phone)
    finally:
        access.time.time = original  # type: ignore[assignment]
    client = _client(app)
    for header in response.headers.getlist("set-cookie"):
        name, _, rest = header.partition("=")
        client.cookies.set(name, rest.split(";", 1)[0])
    client.headers["x-csrf-token"] = client.cookies[access.CSRF_COOKIE]
    return client


async def _code(app, client: httpx.AsyncClient, phone: str = PHONE) -> httpx.Response:
    """Enter a correct WhatsApp code (the code store is filled as /code would)."""
    settings = app.state.settings
    await app.state.pi_customer_codes.put(
        access.code_key(settings, phone),
        {
            "h": access.code_hash(settings, phone, "123456"),
            "t": 0,
            "e": int(time.time()) + 600,
        },
        600,
    )
    return await client.post(f"{PORTAL}/verify", json={"phone": f"+{phone}", "code": "123456"})


async def _add_face(customer: httpx.AsyncClient) -> httpx.Response:
    started = await customer.post(f"{PORTAL}/faces/start")
    assert started.status_code == 200, started.text
    return await customer.post(
        f"{PORTAL}/faces", json={"ticket": started.json()["ticket"], "frames": frames()}
    )


async def test_code_then_face_and_the_code_alone_is_not_enough(app):
    stale = _signed_in(app, age_seconds=3600)
    old = await stale.post(f"{PORTAL}/faces/start")
    assert old.status_code == 403 and old.json()["error"]["code"] == "SIGN_IN_AGAIN"

    customer = _signed_in(app)
    added = await _add_face(customer)
    assert added.status_code == 201, added.text
    listed = (await customer.get(f"{PORTAL}/faces")).json()
    assert len(listed["faces"]) == 1 and listed["max"] == 3 and listed["fresh"] is True

    browser = _client(app)
    step = (await _code(app, browser)).json()
    assert step["mfa_required"] is True and step["methods"] == ["face"]
    assert PHONE not in step["phone"]  # masked
    assert access.SESSION_COOKIE not in browser.cookies  # the code alone didn't sign in
    signed_in = await browser.post(
        f"{PORTAL}/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert signed_in.status_code == 200, signed_in.text
    assert (await browser.get(f"{PORTAL}/me")).status_code == 200

    # Without a face saved, the code alone signs in as before.
    other = _client(app)
    plain = await _code(app, other, "15550007102")
    assert plain.status_code == 200 and "mfa_required" not in plain.json()
    for c in (stale, customer, browser, other):
        await c.aclose()


async def test_three_faces_at_most_and_wrong_tries_lock(app, monkeypatch):
    customer = _signed_in(app)
    for _ in range(3):
        assert (await _add_face(customer)).status_code == 201
    fourth = await customer.post(f"{PORTAL}/faces/start")
    assert fourth.status_code == 422 and fourth.json()["error"]["code"] == "TOO_MANY_FACES"

    from app.modules.auth import face as engine

    monkeypatch.setattr(engine, "similarity", lambda found, code: 0.1)
    browser = _client(app)
    step = (await _code(app, browser)).json()
    for left in (4, 3, 2, 1):
        miss = await browser.post(
            f"{PORTAL}/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
        )
        assert miss.status_code == 401 and f"{left} tr" in miss.json()["error"]["message"]
    locked = await browser.post(
        f"{PORTAL}/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert locked.status_code == 423
    monkeypatch.undo()
    step = (await _code(app, browser)).json()
    still = await browser.post(
        f"{PORTAL}/mfa/face", json={"ticket": step["ticket"], "frames": frames()}
    )
    assert still.status_code == 423  # locked even with a new code
    # Another customer can't remove these faces.
    stranger = _signed_in(app, "15550007103")
    mine = (await customer.get(f"{PORTAL}/faces")).json()["faces"]
    assert (await stranger.delete(f"{PORTAL}/faces/{mine[0]['id']}")).status_code == 404
    for c in (customer, browser, stranger):
        await c.aclose()


async def test_optional_fingerprint_after_the_code(app):
    customer = _signed_in(app, "15550007104")
    options = (await customer.post(f"{PORTAL}/fingerprints/register/options")).json()
    assert options["rp"]["name"] == "pi Customer"
    assert "15550007104" not in str(options)
    device = Authenticator()
    added = await customer.post(
        f"{PORTAL}/fingerprints/register/verify",
        json={"credential": device.create(options, origin=PI_ORIGIN)},
    )
    assert added.status_code == 201, added.text
    browser = _client(app)
    # No sign-in with the fingerprint alone.
    assert (await browser.post(f"{PORTAL}/passkeys/login/options")).status_code in (404, 405)
    step = (await _code(app, browser, "15550007104")).json()
    assert step["methods"] == ["fingerprint"]
    challenge = (
        await browser.post(f"{PORTAL}/mfa/fingerprint/options", json={"ticket": step["ticket"]})
    ).json()["options"]
    signed_in = await browser.post(
        f"{PORTAL}/mfa/fingerprint",
        json={"ticket": step["ticket"], "credential": device.get(challenge, origin=PI_ORIGIN)},
    )
    assert signed_in.status_code == 200, signed_in.text
    assert (await browser.get(f"{PORTAL}/me")).status_code == 200
    for c in (customer, browser):
        await c.aclose()


async def test_live_guidance_for_customers_needs_their_ticket(app):
    customer = _signed_in(app, "15550007105")
    started = (await customer.post(f"{PORTAL}/faces/start")).json()
    browser = _client(app)
    refused = await browser.post(
        f"{PORTAL}/face/probe", json={"ticket": "y" * 32, "frame": frames()[0]}
    )
    assert refused.status_code == 422
    seen = (
        await browser.post(
            f"{PORTAL}/face/probe", json={"ticket": started["ticket"], "frame": frames()[0]}
        )
    ).json()
    assert seen["faces"] == 1
    for c in (customer, browser):
        await c.aclose()
