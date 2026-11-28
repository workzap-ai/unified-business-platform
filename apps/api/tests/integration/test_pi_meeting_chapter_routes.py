"""Chapters and key moments over the API: made once from the transcript, read with the approved
findings at their time, refused when there is nothing to read or the model is down."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import insight, meeting, workspace
from test_pi_meeting_routes import BASE, switch_on

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import chapter_routes
from app.modules.pi_meetings.chapters import ChapterDraft
from app.modules.pi_meetings.models import PiMeetingParticipant, PiMeetingSegment

pytestmark = pytest.mark.integration


class FakeManager:
    def __init__(self, drafts=None, down=False):
        self.drafts, self.down, self.calls = drafts or [], down, 0

    async def complete_structured(self, scope, schema, **kwargs):
        from app.ai.errors import GatewayUnavailable

        self.calls += 1
        if self.down:
            raise GatewayUnavailable("down")
        return SimpleNamespace(value=schema(chapters=self.drafts))


@pytest.fixture
def model(monkeypatch):
    fake = FakeManager(
        [
            ChapterDraft(start_line=0, title="The shop", summary="What the shop sells"),
            ChapterDraft(start_line=3, title="Delivery", summary="How orders get to customers"),
        ]
    )
    monkeypatch.setattr(chapter_routes, "build_llm_manager", lambda *a, **k: fake)
    return fake


async def meeting_with_lines(api, db, phone, lines=6, approve=True):
    pi, conv, scope = await workspace(api, db, phone)
    await switch_on(api)
    m = meeting(scope, conv.customer_id, title="Kickoff", status="review")
    db.add(m)
    await db.flush()
    who = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=m.id,
        label="Ayesha",
    )
    db.add(who)
    await db.flush()
    for i in range(lines):
        db.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=m.id,
                ordinal=i,
                start_ms=i * 10_000,
                end_ms=i * 10_000 + 9_000,
                participant_id=who.id,
                text=f"line {i} about the shop",
            )
        )
    if approve:
        db.add_all(
            [
                insight(
                    scope,
                    m.id,
                    kind="decision",
                    text="Start with the shop page",
                    segment_refs=[4],
                    review_status="approved",
                ),
                insight(
                    scope,
                    m.id,
                    kind="next_step",
                    text="A draft nobody checked",
                    segment_refs=[2],
                    review_status="pending",
                ),
            ]
        )
    await db.commit()
    return pi, m


async def test_chapters_are_made_stored_and_listed_with_the_approved_moments(
    api, business_db, model
):
    pi, m = await meeting_with_lines(api, business_db, "369800001")
    empty = (await api.get(f"{BASE}/{m.id}/chapters")).json()
    assert empty["chapters"] == [] and empty["made_at"] is None and empty["lines"] == 6
    assert [x["text"] for x in empty["moments"]] == ["Start with the shop page"]  # no model needed

    made = await api.post(f"{BASE}/{m.id}/chapters")
    assert made.status_code == 200
    body = made.json()
    assert [(c["title"], c["start_ms"], c["end_ms"]) for c in body["chapters"]] == [
        ("The shop", 0, 30_000),
        ("Delivery", 30_000, 59_000),
    ]
    assert body["moments"][0]["start_ms"] == 40_000 and body["moments"][0]["line"] == 4
    assert datetime.fromisoformat(body["made_at"]).tzinfo is UTC or body["made_at"]
    assert (await api.get(f"{BASE}/{m.id}/chapters")).json()["chapters"] == body["chapters"]
    again = await api.post(f"{BASE}/{m.id}/chapters")  # pressed twice: made once
    assert again.status_code == 200 and model.calls == 1
    audit = await business_db.scalar(
        select(AuditEvent).where(AuditEvent.action == "pi.meeting_chapters_made")
    )
    assert audit is not None and "shop" not in str(audit.details)  # counts only, never the words
    await pi.close()


async def test_no_transcript_or_a_model_that_is_down_makes_nothing(api, business_db, monkeypatch):
    pi, m = await meeting_with_lines(api, business_db, "369800002", lines=0, approve=False)
    monkeypatch.setattr(chapter_routes, "build_llm_manager", lambda *a, **k: FakeManager())
    none = await api.post(f"{BASE}/{m.id}/chapters")
    assert none.status_code == 422 and none.json()["error"]["code"] == "TRANSCRIPT_EMPTY"
    assert (await api.get(f"{BASE}/{m.id}/chapters")).json()["moments"] == []
    await pi.close()

    pi, m = await meeting_with_lines(api, business_db, "369800003")
    monkeypatch.setattr(chapter_routes, "build_llm_manager", lambda *a, **k: FakeManager(down=True))
    down = await api.post(f"{BASE}/{m.id}/chapters")
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_CHAPTERS_FAILED"
    assert (await api.get(f"{BASE}/{m.id}/chapters")).json()["chapters"] == []  # nothing stored
    await pi.close()


async def test_chapters_need_the_feature_on_and_stay_inside_the_workspace(api, business_db, model):
    pi, m = await meeting_with_lines(api, business_db, "369800004")
    other = "00000000-0000-0000-0000-000000000000"
    assert (await api.get(f"{BASE}/{other}/chapters")).status_code == 404
    assert (await api.post(f"{BASE}/{other}/chapters")).status_code == 404
    await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": {"meeting_intel": False}}},
    )
    off = await api.get(f"{BASE}/{m.id}/chapters")
    assert off.status_code == 403 and off.json()["error"]["code"] == "MEETING_INTEL_OFF"
    await pi.close()
