"""Approving a meeting insight writes to the shared brain through the existing writers, once
(pi_meetings/brain_bridge.py), and an AI conclusion never becomes something the customer said."""

import pytest
from sqlalchemy import select
from test_pi_meeting_data import count, insight, meeting, workspace

from app.modules.pi.memory_models import PiDecision
from app.modules.pi.problem_models import PiProblem
from app.modules.pi_meetings import brain_bridge
from app.modules.pi_meetings.models import PiMeetingSegment
from app.modules.pi_saas.models import PiStaffRequest

pytestmark = pytest.mark.integration


async def seeded(api, db, number):
    pi, conv, scope = await workspace(api, db, number)
    m = meeting(scope, conv.customer_id)
    db.add(m)
    await db.flush()
    db.add(
        PiMeetingSegment(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            meeting_id=m.id,
            ordinal=0,
            start_ms=0,
            end_ms=900,
            text="our evening stock keeps running out every week",
        )
    )
    await db.flush()
    return pi, scope, m


async def test_a_stated_problem_reaches_the_problem_map_once(api, business_db):
    pi, scope, m = await seeded(api, business_db, "377000001")
    before = await count(business_db, PiProblem, scope)
    item = insight(scope, m.id, segment_refs=[0], text="evening stock keeps running out")
    business_db.add(item)
    await business_db.flush()
    first = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert first.wrote == "problem" and item.brain_ref.startswith("problem:")
    assert item.review_status == "approved" and item.written_at is not None
    assert await count(business_db, PiProblem, scope) == before + 1
    again = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert again.wrote == "problem"
    assert await count(business_db, PiProblem, scope) == before + 1  # a replay writes nothing
    await pi.close()


async def test_a_stated_decision_is_recorded_in_memory_under_a_meeting_namespace(api, business_db):
    pi, scope, m = await seeded(api, business_db, "377000002")
    item = insight(scope, m.id, kind="decision", segment_refs=[0], text="owner chose weekly counts")
    business_db.add(item)
    await business_db.flush()
    out = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert out.wrote == "decision"
    row = await business_db.scalar(
        select(PiDecision).where(PiDecision.subject_ref.like("meeting:%"))
    )
    assert row is not None and row.status == "active" and row.actor == "staff"
    await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert (
        len(
            list(
                await business_db.scalars(
                    select(PiDecision).where(PiDecision.subject_ref.like("meeting:%"))
                )
            )
        )
        == 1
    )
    await pi.close()


async def test_an_ai_conclusion_is_approved_as_information_and_never_written_as_a_fact(
    api, business_db
):
    pi, scope, m = await seeded(api, business_db, "377000003")
    problems_before = await count(business_db, PiProblem, scope)
    decisions_before = await count(business_db, PiDecision, scope)
    item = insight(scope, m.id, kind="problem", basis="inferred", text="stock control is weak")
    business_db.add(item)
    await business_db.flush()
    out = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert out.wrote == "" and item.review_status == "approved" and item.written_at is None
    assert await count(business_db, PiProblem, scope) == problems_before
    assert await count(business_db, PiDecision, scope) == decisions_before
    await pi.close()


async def test_an_action_becomes_one_staff_request(api, business_db):
    pi, scope, m = await seeded(api, business_db, "377000004")
    before = await count(business_db, PiStaffRequest, scope)
    item = insight(
        scope,
        m.id,
        kind="action",
        segment_refs=[0],
        text="send the stock list",
        owner_label="Customer",
        due_text="Friday",
    )
    business_db.add(item)
    await business_db.flush()
    out = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert out.wrote == "request" and item.brain_ref.startswith("request:")
    assert await count(business_db, PiStaffRequest, scope) == before + 1
    await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert await count(business_db, PiStaffRequest, scope) == before + 1
    await pi.close()


async def test_an_unlinked_meeting_cannot_write_and_a_rejected_insight_cannot_be_approved(
    api, business_db
):
    pi, scope, m = await seeded(api, business_db, "377000005")
    m.customer_id = None
    item = insight(scope, m.id, segment_refs=[0])
    business_db.add(item)
    await business_db.flush()
    with pytest.raises(brain_bridge.NotLinked):
        await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    await brain_bridge.reject(business_db, item, reviewer_id=None)
    assert item.review_status == "rejected"
    with pytest.raises(brain_bridge.NotPending):
        await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    await pi.close()


async def test_a_reviewers_wording_cannot_carry_a_price_or_be_emptied(
    api, business_db, monkeypatch
):
    pi, scope, m = await seeded(api, business_db, "377000005")
    item = insight(scope, m.id, kind="decision", segment_refs=[0], text="owner chose weekly counts")
    business_db.add(item)
    await business_db.flush()
    with pytest.raises(brain_bridge.PriceInEdit):
        await brain_bridge.approve(
            business_db, scope, m, item, reviewer_id=None, edited_text="we agree Rs 5,000 monthly"
        )
    monkeypatch.setattr(brain_bridge.memory_ledger, "redacted", lambda *_a, **_k: "")
    with pytest.raises(brain_bridge.EditRefused):
        await brain_bridge.approve(
            business_db, scope, m, item, reviewer_id=None, edited_text="some wording"
        )
    assert item.written_at is None and item.review_status == "pending"
    await pi.close()


async def test_a_meeting_memory_row_says_where_it_came_from_and_who_is_unconfirmed(
    api, business_db
):
    pi, scope, m = await seeded(api, business_db, "377000006")
    item = insight(scope, m.id, kind="decision", segment_refs=[0], text="we will deliver Friday")
    business_db.add(item)
    await business_db.flush()
    await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    row = await business_db.scalar(
        select(PiDecision).where(PiDecision.subject_ref.like("meeting:%"))
    )
    assert row is not None
    assert "In a meeting (speaker not confirmed as the customer)" in row.owner_words
    await pi.close()


async def test_an_ai_suggested_action_is_headed_as_unconfirmed(api, business_db):
    pi, scope, m = await seeded(api, business_db, "377000007")
    item = insight(
        scope, m.id, kind="next_step", basis="inferred", text="share a sample", segment_refs=[]
    )
    business_db.add(item)
    await business_db.flush()
    out = await brain_bridge.approve(business_db, scope, m, item, reviewer_id=None)
    assert out.wrote == "request"
    req = await business_db.scalar(
        select(PiStaffRequest).where(PiStaffRequest.id == item.brain_ref.split(":", 1)[1])
    )
    assert req is not None and "AI suggestion (unconfirmed)" in req.question
    await pi.close()
