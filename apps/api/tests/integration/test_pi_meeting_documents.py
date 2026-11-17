"""Designed meeting documents: made only from approved insights, a draft until a person approves
it, the same content is one draft, nothing sensitive inside, deleted with the meeting."""

import io

import pytest
from pptx import Presentation
from pypdf import PdfReader
from sqlalchemy import select
from test_pi_meeting_data import insight, meeting, workspace
from test_pi_meeting_routes import BASE, switch_on

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings.models import PiMeetingBot, PiMeetingDocument

pytestmark = pytest.mark.integration


async def seeded(api, db, number):
    pi, conv, scope = await workspace(api, db, number)
    await switch_on(api)
    m = meeting(scope, conv.customer_id, title="Stock call with Ayesha", status="review")
    db.add(m)
    await db.flush()
    db.add_all(
        [
            insight(scope, m.id, kind="summary", basis="inferred", text="They sell tiles."),
            insight(scope, m.id, kind="problem", text="Evening stock runs out"),
            insight(
                scope,
                m.id,
                kind="action",
                text="Send the list",
                owner_label="bilal",
                due_text="Friday",
                review_status="approved",
            ),
            insight(scope, m.id, kind="problem", text="Pending idea", review_status="pending"),
            insight(scope, m.id, kind="risk", text="Rejected idea", review_status="rejected"),
            insight(scope, m.id, kind="decision", text="Budget is Rs 50,000"),
        ]
    )
    await db.flush()
    await db.commit()
    return pi, m


async def approve_all_but_pending(db, mid):
    from sqlalchemy import update

    from app.modules.pi_meetings.models import PiMeetingInsight

    await db.execute(
        update(PiMeetingInsight)
        .where(
            PiMeetingInsight.meeting_id == mid,
            PiMeetingInsight.text.notin_(["Pending idea", "Rejected idea"]),
        )
        .values(review_status="approved")
    )
    await db.commit()


async def test_nothing_is_made_until_something_is_approved(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "369100001")
    await switch_on(api)
    m = meeting(scope, conv.customer_id, status="review")
    business_db.add(m)
    await business_db.flush()
    business_db.add(insight(scope, m.id, kind="problem", text="Evening stock runs out"))
    await business_db.commit()  # still pending
    r = await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "MEETING_NOTHING_APPROVED"
    bad = await api.post(f"{BASE}/{m.id}/documents", json={"kind": "word"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "MEETING_DOCUMENT_KIND_INVALID"
    await pi.close()


async def test_a_pdf_and_a_deck_are_made_from_approved_findings_only(api, business_db):
    pi, m = await seeded(api, business_db, "369100002")
    await approve_all_but_pending(business_db, m.id)
    pdf = await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})
    assert pdf.status_code == 201, pdf.text
    doc = pdf.json()
    assert doc["status"] == "draft" and doc["kind"] == "summary_pdf" and doc["lines_left_out"] == 1
    got = await api.get(f"{BASE}/{m.id}/documents/{doc['id']}/download")
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf"
    assert 'filename="meeting-summary-' in got.headers["content-disposition"]
    assert got.headers["cache-control"] == "no-store"
    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(got.content)).pages)
    assert "Evening stock runs out" in text and "Owner: bilal" in text
    assert "Pending idea" not in text and "Rejected idea" not in text
    assert "50,000" not in text and "Budget" not in text  # a price is never in a document

    deck = await api.post(f"{BASE}/{m.id}/documents", json={"kind": "deck_pptx"})
    assert deck.status_code == 201
    pptx = await api.get(f"{BASE}/{m.id}/documents/{deck.json()['id']}/download")
    slides = Presentation(io.BytesIO(pptx.content)).slides
    assert len(slides) >= 4 and "presentationml" in pptx.headers["content-type"]
    await pi.close()


async def test_the_same_content_is_one_draft_not_a_new_one_each_press(api, business_db):
    pi, m = await seeded(api, business_db, "369100003")
    await approve_all_but_pending(business_db, m.id)
    first = (await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})).json()
    again = await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})
    assert again.status_code == 200 and again.json()["again"] is True
    assert again.json()["id"] == first["id"]
    listed = (await api.get(f"{BASE}/{m.id}/documents")).json()["items"]
    assert len(listed) == 1
    await pi.close()


async def test_a_draft_is_approved_by_a_person_and_an_approved_one_stays(api, business_db):
    pi, m = await seeded(api, business_db, "369100004")
    await approve_all_but_pending(business_db, m.id)
    doc = (await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})).json()
    ok = await api.post(f"{BASE}/{m.id}/documents/{doc['id']}/approve")
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["approved_at"]
    keep = await api.delete(f"{BASE}/{m.id}/documents/{doc['id']}")
    assert keep.status_code == 409 and keep.json()["error"]["code"] == "MEETING_DOCUMENT_APPROVED"
    deck = (await api.post(f"{BASE}/{m.id}/documents", json={"kind": "deck_pptx"})).json()
    assert (await api.delete(f"{BASE}/{m.id}/documents/{deck['id']}")).status_code == 204
    left = (await api.get(f"{BASE}/{m.id}/documents")).json()["items"]
    assert [d["id"] for d in left] == [doc["id"]]
    actions = {
        e.action
        for e in await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action.like("pi.meeting_document_%"))
        )
    }
    assert actions == {
        "pi.meeting_document_created",
        "pi.meeting_document_approved",
        "pi.meeting_document_deleted",
    }
    await pi.close()


async def test_a_document_of_another_meeting_or_workspace_is_not_found(api, business_db):
    pi, m = await seeded(api, business_db, "369100005")
    await approve_all_but_pending(business_db, m.id)
    doc = (await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})).json()
    other = "00000000-0000-0000-0000-000000000001"
    assert (await api.get(f"{BASE}/{other}/documents")).status_code == 404
    assert (await api.get(f"{BASE}/{m.id}/documents/{other}/download")).status_code == 404
    assert (await api.get(f"{BASE}/{other}/documents/{doc['id']}/download")).status_code == 404
    await pi.close()


async def test_documents_and_bots_go_when_the_meeting_is_deleted(api, business_db):
    pi, m = await seeded(api, business_db, "369100006")
    await approve_all_but_pending(business_db, m.id)
    await api.post(f"{BASE}/{m.id}/documents", json={"kind": "summary_pdf"})
    business_db.add(
        PiMeetingBot(
            tenant_id=m.tenant_id,
            environment_id=m.environment_id,
            meeting_id=m.id,
            provider="recall",
            external_id="bot-erase-1",
            status="done",
            url_hash="x" * 64,
        )
    )
    await business_db.commit()
    gone = await api.delete(f"{BASE}/{m.id}")
    assert gone.status_code in (200, 204), gone.text
    business_db.expire_all()
    assert await business_db.scalar(select(PiMeetingDocument.id)) is None
    assert await business_db.scalar(select(PiMeetingBot.id)) is None
    await pi.close()
