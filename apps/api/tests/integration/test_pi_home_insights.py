"""Home insights count real activity only: messages per day, conversations Pi handled
without a person, reply speed and topics."""

import pytest
from pi_saas_support import FakeProvider, configure
from test_pi_saas import _kapso, _message_event, _ready_business, _run_jobs
from test_pi_service_conversations import mock_turns, turn

pytestmark = pytest.mark.integration


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


async def test_insights_count_this_weeks_activity(app, provider, business_db, monkeypatch):
    mock_turns(monkeypatch, *[turn(reply="Ji, kaunsa feature chahiye?")] * 3)
    client, _ = await _ready_business(app, provider, business_db, "Insight Co", "6300000001")
    empty = (await client.get("/api/v1/pi-app/home/insights")).json()
    assert len(empty["daily"]) == 7 and empty["conversations"] == 0
    assert empty["automation_rate"] is None and empty["median_reply_seconds"] is None
    for n, sender in enumerate(("15550008001", "15550008002")):
        await _kapso(
            client,
            "whatsapp.message.received",
            _message_event("6300000001", sender, "Website chahiye", f"wamid.ins-{n}"),
        )
    await _run_jobs(app, provider, business_db)
    data = (await client.get("/api/v1/pi-app/home/insights")).json()
    today = data["daily"][-1]
    assert today["customers"] == 2 and today["pi"] == 2 and today["team"] == 0
    assert sum(d["customers"] for d in data["daily"][:-1]) == 0
    assert data["conversations"] == 2 and data["handled_by_pi"] == 2
    assert data["automation_rate"] == 1.0
    assert data["median_reply_seconds"] is not None
    assert data["timezone"] == "UTC"
    # Another business sees none of it.
    other, _ = await _ready_business(app, provider, business_db, "Other Co", "6300000002")
    assert (await other.get("/api/v1/pi-app/home/insights")).json()["conversations"] == 0
    for c in (client, other):
        await c.aclose()
