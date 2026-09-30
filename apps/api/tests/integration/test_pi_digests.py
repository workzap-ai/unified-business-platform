"""Weekly summaries: real counts, built once per week, in-app always, email only when
switched on (and honest when no email service is connected); operator weekly view."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure
from sqlalchemy import func, select
from test_pi_saas import _account, _kapso, _message_event, _ready_business, _run_jobs
from test_service_lifecycle import register

from app.modules.notifications.models import Notification
from app.modules.pi_saas import digests
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    return fake


def test_last_week_uses_the_business_time_zone():
    # Monday 5 October 2026: the summary covers Monday 28 Sept to Sunday 4 Oct.
    monday_morning = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)  # 09:00 in Karachi
    start, end, start_utc, end_utc = digests.last_week("Asia/Karachi", monday_morning)
    assert (start, end) == (date(2026, 9, 28), date(2026, 10, 5))
    assert start_utc == datetime(2026, 9, 27, 19, 0, tzinfo=UTC)  # Mon 00:00 +05:00
    assert end_utc - start_utc == timedelta(days=7)


async def test_weekly_summary_is_built_once_and_delivered_in_app(app, provider, business_db):
    client, view = await _ready_business(app, provider, business_db, "Noor", "6666666666")
    for i, sender in enumerate(["923005550001", "923005550002"]):
        await _kapso(
            client,
            "whatsapp.message.received",
            _message_event("6666666666", sender, "Salam", f"wamid.d{i}"),
        )
    await _run_jobs(app, provider, business_db)
    account = await _account(business_db, view)
    # Next Monday 09:00 local, so "last week" contains today's messages.
    tz = digests.zone(account.timezone)
    local = datetime.now(UTC).astimezone(tz)
    next_monday = (local + timedelta(days=7 - local.weekday())).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    row, created = await digests.build(business_db, account, next_monday)
    assert created and row.metrics["customers_who_messaged"] == 2
    assert row.metrics["messages_received"] == 2 and row.metrics["new_customers"] == 2
    again, created_again = await digests.build(business_db, account, next_monday)
    assert again.id == row.id and not created_again
    assert await digests.deliver(business_db, account, row) == []  # email is off
    assert row.delivery == {"in_app": "sent"}
    notes = await business_db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.kind == "pi.weekly_digest", Notification.tenant_id == account.tenant_id)
    )
    assert notes == 1

    # Email is opt-in, and reported honestly when no email service is connected.
    turned_on = await client.put("/api/v1/pi-app/digests/settings", json={"email": True})
    assert turned_on.json() == {"email": True}
    await business_db.refresh(account)
    later, _ = await digests.build(business_db, account, next_monday + timedelta(days=7))
    assert await digests.deliver(business_db, account, later) == []
    assert later.delivery["email"] == "integration_not_configured"

    listed = (await client.get("/api/v1/pi-app/digests")).json()
    assert len(listed) == 2 and "your week with Pi" in listed[0]["text"]
    current = (await client.get("/api/v1/pi-app/digests/this-week")).json()
    assert current["metrics"]["messages_received"] == 2
    await client.aclose()


async def test_operator_weekly_summary_is_scoped(api, app, provider, business_db):
    client, _ = await _ready_business(app, provider, business_db, "Hira", "7777777777")
    identity = await register(api)
    assert (await api.get("/api/v1/operator/pi/weekly")).status_code == 403
    member = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="support")
    business_db.add(member)
    await business_db.flush()
    scoped = (await api.get("/api/v1/operator/pi/weekly")).json()
    assert scoped["week"]["new_businesses"] == 0  # support sees assigned businesses only
    member.role = "owner"
    await business_db.flush()
    everything = (await api.get("/api/v1/operator/pi/weekly")).json()
    assert everything["week"]["new_businesses"] >= 1 and everything["week"]["went_live"] >= 1
    await client.aclose()
