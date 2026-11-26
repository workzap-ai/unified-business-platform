"""An approved meeting document reaches the customer on WhatsApp only when a person sends it: the
draft cannot be sent, the inbox rules hold (a person has taken over), the customer gets a signed
link to exactly the approved file, a second press sends nothing more, and a bad link opens
nothing."""

from urllib.parse import urlparse
from uuid import UUID

import pytest
from sqlalchemy import select
from test_pi_deals import _public
from test_pi_meeting_data import insight, meeting, workspace
from test_pi_meeting_routes import BASE, switch_on

from app.modules.audit.models import AuditEvent
from app.modules.pi import brain_docs
from app.modules.pi.models import PiMessage

pytestmark = pytest.mark.integration


async def ready(api, db, number, *, linked=True):
    """A meeting with approved findings and one summary PDF still a draft."""
    pi, conv, scope = await workspace(api, db, number)
    await switch_on(api)
    m = meeting(scope, conv.customer_id if linked else None, title="Stock review", status="review")
    db.add(m)
    await db.flush()
    db.add(
        insight(
            scope, m.id, kind="problem", text="Evening stock runs out", review_status="approved"
        )
    )
    mid, cid = m.id, conv.id
    await db.commit()
    made = await api.post(f"{BASE}/{mid}/documents", json={"kind": "summary_pdf"})
    assert made.status_code == 201, made.text
    return pi, cid, mid, made.json()["id"]


def send(api, mid, doc):
    return api.post(f"{BASE}/{mid}/documents/{doc}/send")


async def test_a_draft_cannot_be_sent(api, business_db):
    pi, cid, mid, doc = await ready(api, business_db, "379000001")
    refused = await send(api, mid, doc)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "MEETING_DOCUMENT_NOT_APPROVED"
    await pi.close()


async def test_a_meeting_without_a_customer_cannot_send(api, business_db):
    pi, cid, mid, doc = await ready(api, business_db, "379000002", linked=False)
    await api.post(f"{BASE}/{mid}/documents/{doc}/approve")
    refused = await send(api, mid, doc)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "MEETING_NOT_LINKED"
    await pi.close()


async def test_takeover_first_then_one_message_once_and_the_link_opens_the_approved_file(
    api, business_db
):
    pi, cid, mid, doc = await ready(api, business_db, "379000003")
    assert (await api.post(f"{BASE}/{mid}/documents/{doc}/approve")).status_code == 200
    early = await send(api, mid, doc)
    assert early.status_code in (409, 422) and early.json()["error"]["code"] == "TAKEOVER_REQUIRED"
    taken = await api.post(f"/api/v1/pi/conversations/{cid}/actions/takeover")
    assert taken.json()["mode"] == "human"

    sent = await send(api, mid, doc)
    assert sent.status_code == 201, sent.text
    assert sent.json()["status"] == "queued" and sent.json()["again"] is False
    business_db.expire_all()
    row = await business_db.get(PiMessage, sent.json()["message_id"])
    assert row.sender_type == "human" and row.direction == "outbound"
    assert row.body.startswith("Thank you for your time")
    link = row.media["document"]["link"]
    assert "/api/v1/pi-app/meeting-docs/" in link
    assert row.media["document"]["filename"].startswith("meeting-summary-")
    assert "Stock review" not in link  # the link carries no meeting detail

    got = await _public(api).get(urlparse(link).path)
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf"
    assert got.content.startswith(b"%PDF")
    assert "no-store" in got.headers["cache-control"]

    again = await send(api, mid, doc)
    assert again.status_code == 201 and again.json()["again"] is True
    assert again.json()["message_id"] == sent.json()["message_id"]
    business_db.expire_all()
    audits = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_document_sent")
        )
    )
    assert len(audits) == 1 and "Evening stock" not in str(audits[0].details)
    await pi.close()


async def test_a_bad_or_unapproved_link_opens_nothing(api, business_db):
    pi, cid, mid, doc = await ready(api, business_db, "379000004")
    # the draft's own signed token must still open nothing
    signed = brain_docs.doc_token(pi.app.state.settings, UUID(doc))
    public = _public(api)
    name = "meeting-summary.pdf"
    assert (await public.get(f"/api/v1/pi-app/meeting-docs/{signed}/{name}")).status_code == 404
    assert (await public.get(f"/api/v1/pi-app/meeting-docs/junk/{name}")).status_code == 404
    assert (
        await public.get(f"/api/v1/pi-app/meeting-docs/{signed[:-3]}abc/{name}")
    ).status_code == 404
    await pi.close()
