"""The pi app has what Owner OS's pi module has: pi Health (state, fixes, self-tests) and
the customer page's Activity feed, under its own session at /api/v1/pi-app/..."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


async def _pi_app(api):
    from pi_saas_support import FakeProvider, configure, pi_client, pi_register

    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    await pi_register(client)
    return client


async def test_the_pi_app_has_pi_health(api):
    client = await _pi_app(api)
    health = await client.get("/api/v1/pi-app/pi/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert 0 <= body["score"] <= 100
    assert body["verdict"]
    assert {"checks", "areas", "self_tests", "trends", "gaps", "learning"} <= set(body)
    # The owner can run pi's safe fixes from the pi app too.
    healed = await client.post("/api/v1/pi-app/pi/health/heal")
    assert healed.status_code == 200, healed.text
    assert "fixes" in healed.json()
    # Only the two known owner fixes exist.
    unknown = await client.post("/api/v1/pi-app/pi/health/fix/drop_everything")
    assert unknown.status_code == 422
    # Signed out: no health.
    client.cookies.clear()
    assert (await client.get("/api/v1/pi-app/pi/health")).status_code == 401
    await client.aclose()


async def test_the_pi_app_shows_a_customers_activity(api):
    client = await _pi_app(api)
    started = await client.post(
        "/api/v1/pi-app/pi/deals/start",
        json={"phone": "+92 300 7654321", "name": "Sana", "title": "Logo design"},
    )
    assert started.status_code == 201, started.text
    customer_id = started.json()["customer_id"]
    quote = await client.post(
        "/api/v1/pi-app/quotes",
        json={
            "customer_id": customer_id,
            "lead_id": started.json()["lead_id"],
            "lines": [{"description": "Logo", "quantity": "1", "unit_price": "20000"}],
        },
    )
    assert quote.status_code == 201, quote.text
    feed = await client.get(f"/api/v1/pi-app/customers/{customer_id}/activities")
    assert feed.status_code == 200, feed.text
    page = feed.json()
    assert page["total"] >= 1
    assert any(quote.json()["number"] in a["summary"] for a in page["items"])
    assert {"id", "kind", "summary", "actor_label", "created_at"} <= set(page["items"][0])
    # Paged like Owner OS.
    first = await client.get(
        f"/api/v1/pi-app/customers/{customer_id}/activities", params={"page_size": 1}
    )
    assert len(first.json()["items"]) == 1
    # Someone else's (or no) customer: not found.
    missing = await client.get(f"/api/v1/pi-app/customers/{uuid4()}/activities")
    assert missing.status_code == 404
    # The other customer-page reads the pi app shows answer for the same customer.
    for path in ("pi-overview", "solution", "pi-overview.pdf"):
        response = await client.get(f"/api/v1/pi-app/customers/{customer_id}/{path}")
        assert response.status_code == 200, (path, response.text[:200])
    await client.aclose()
