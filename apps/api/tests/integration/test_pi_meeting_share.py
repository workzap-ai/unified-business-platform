"""The approved meeting summary reaches the customer only when a person sends it: the summary must
be approved, the words carry no price, the conversation must be taken over (the inbox rules), and
a second press sends nothing more."""

import pytest
from sqlalchemy import select
from test_pi_meeting_data import insight, meeting, workspace

from app.modules.audit.models import AuditEvent
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration
BASE = "/api/v1/pi/meeting-intel"


async def switch(api):
    r = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": {"meeting_intel": True}}},
    )
    assert r.status_code == 200, r.text


async def seeded(api, db, number, review="approved"):
    pi, conv, scope = await workspace(api, db, number)
    await switch(api)
    m = meeting(scope, conv.customer_id, title="Stock review")
    db.add(m)
    await db.flush()
    db.add(
        insight(
            scope,
            m.id,
            kind="summary",
            basis="inferred",
            text="We agreed to count stock weekly and send a list.",
            review_status=review,
        )
    )
    mid, cid = m.id, conv.id
    await db.commit()
    return pi, cid, mid


def share(api, mid, **body):
    return api.post(f"{BASE}/{mid}/share-summary", json=body)


async def test_the_summary_must_be_approved_first(api, business_db):
    pi, cid, mid = await seeded(api, business_db, "378000001", review="pending")
    refused = await share(api, mid)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "MEETING_SUMMARY_NOT_APPROVED"
    await pi.close()


async def test_a_price_in_the_words_is_refused(api, business_db):
    pi, cid, mid = await seeded(api, business_db, "378000002")
    r = await share(api, mid, text="We can do it for Rs 5000 a month.")
    assert r.status_code == 422 and r.json()["error"]["code"] == "MEETING_PRICE_NOT_ALLOWED"
    await pi.close()


async def test_the_inbox_rules_hold_takeover_first_then_one_message_once(api, business_db):
    pi, cid, mid = await seeded(api, business_db, "378000003")
    early = await share(api, mid)
    assert early.status_code in (409, 422) and early.json()["error"]["code"] == "TAKEOVER_REQUIRED"
    taken = await api.post(f"/api/v1/pi/conversations/{cid}/actions/takeover")
    assert taken.json()["mode"] == "human"

    sent = await share(api, mid, text="We agreed to count stock weekly, 0300 123 4567.")
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "queued" and sent.json()["again"] is False
    business_db.expire_all()
    row = await business_db.get(PiMessage, sent.json()["message_id"])
    assert row.sender_type == "human" and row.direction == "outbound"
    assert "count stock weekly" in row.body and "0300" not in row.body  # phone number redacted
    assert row.body.startswith("Thank you for your time")

    again = await share(api, mid)
    assert again.status_code == 201 and again.json()["again"] is True
    assert again.json()["message_id"] == sent.json()["message_id"]
    business_db.expire_all()
    shared = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_summary_shared")
        )
    )
    assert len(shared) == 1 and "count stock" not in str(shared[0].details)
    await pi.close()
