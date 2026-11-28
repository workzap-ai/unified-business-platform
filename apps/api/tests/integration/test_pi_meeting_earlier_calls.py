"""pi remembers what the team approved from a customer's earlier calls, and nothing else."""

import pytest
from test_pi_meeting_data import meeting, workspace

from app.modules.pi_meetings import meeting_memory
from app.modules.pi_meetings.models import PiMeetingInsight

pytestmark = pytest.mark.integration


def insight(scope, meeting_id, kind, text, status):
    return PiMeetingInsight(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=meeting_id,
        kind=kind,
        basis="stated",
        text=text,
        review_status=status,
    )


async def test_only_approved_points_of_this_customers_other_calls_are_remembered(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "379200001")
    old = meeting(scope, conv.customer_id, title="Earlier call", status="review")
    other = meeting(scope, None, title="Somebody else", status="review")
    now = meeting(scope, conv.customer_id, title="This call", status="created")
    business_db.add_all([old, other, now])
    await business_db.flush()
    business_db.add_all(
        [
            insight(scope, old.id, "problem", "Orders get missed on busy days", "approved"),
            insight(scope, old.id, "decision", "Draft decision nobody checked", "pending"),
            insight(scope, old.id, "problem", "Rejected guess", "rejected"),
            insight(scope, old.id, "question", "Approved but not a remembered kind", "approved"),
            insight(scope, other.id, "problem", "Another customer's secret", "approved"),
            insight(scope, now.id, "problem", "Said in this very call", "approved"),
        ]
    )
    await business_db.commit()

    found = await meeting_memory.earlier_calls(business_db, scope, now)
    assert len(found) == 1
    assert found[0]["points"] == ["problem: Orders get missed on busy days"]
    assert await meeting_memory.earlier_calls(business_db, scope, other) == []  # no customer


async def test_what_was_left_open_comes_first_and_keeps_its_due_date(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "379200002")
    old = meeting(scope, conv.customer_id, title="Earlier call", status="review")
    now = meeting(scope, conv.customer_id, title="This call", status="created")
    business_db.add_all([old, now])
    await business_db.flush()
    rows = [
        insight(scope, old.id, "summary", "A recap", "approved"),
        insight(scope, old.id, "problem", "Orders get missed", "approved"),
        insight(scope, old.id, "decision", "Start with the shop", "edited"),
        insight(scope, old.id, "requirement_explicit", "Needs Urdu", "approved"),
        insight(scope, old.id, "next_step", "Send the layout", "approved"),
        insight(scope, old.id, "commitment", "Draft that was never checked", "pending"),
    ]
    rows[4].due_text = "Friday"
    rows[4].owner_label = "Ayesha"
    business_db.add_all(rows)
    await business_db.commit()

    points = (await meeting_memory.earlier_calls(business_db, scope, now))[0]["points"]
    assert points[0] == "next_step: Send the layout (by Friday)"
    assert points[1].startswith("decision:") and len(points) == meeting_memory.EARLIER_POINTS
    assert not any("Ayesha" in p or "never checked" in p for p in points)
    assert "summary: A recap" not in points  # the recap is the least useful, so it is cut first
