"""After a video call pi drafts the findings by itself, and only as drafts: the meeting moves to
review, the team gets one notification, nothing is approved, and a call that said almost nothing or
a model that cannot be reached leaves things as they were."""

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import meeting, workspace

from app.modules.notifications.models import Notification
from app.modules.pi_meetings import analyse as analysis
from app.modules.pi_meetings import auto_analyse
from app.modules.pi_meetings.models import PiMeeting, PiMeetingParticipant, PiMeetingSegment

pytestmark = pytest.mark.integration


async def ready(api, db, phone, *, lines):
    pi, conv, scope = await workspace(api, db, phone)
    m = meeting(scope, conv.customer_id, title="Video call", status="analysing")
    db.add(m)
    await db.flush()
    who = PiMeetingParticipant(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        meeting_id=m.id,
        label="Guest",
    )
    db.add(who)
    await db.flush()
    for ordinal in range(lines):
        db.add(
            PiMeetingSegment(
                tenant_id=scope.tenant_id,
                environment_id=scope.environment_id,
                meeting_id=m.id,
                ordinal=ordinal,
                start_ms=ordinal * 1000,
                end_ms=ordinal * 1000 + 900,
                participant_id=who.id,
                text=f"line number {ordinal} about the stock running out",
            )
        )
    await db.commit()
    return pi, scope, m


async def notifications(db, scope):
    return await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.tenant_id == scope.tenant_id,
            Notification.kind == "pi_meeting_ready",
        )
    )


async def test_a_finished_call_is_read_and_the_team_is_told_once(api, business_db, monkeypatch):
    pi, scope, m = await ready(api, business_db, "379100001", lines=6)
    mid = m.id

    async def fake_run(session, scope, meeting, manager, segments, **kw):
        assert len(segments) == 6 and kw["speakers"] == ["Guest"]
        return analysis.Progress(done=1, total=1)

    monkeypatch.setattr(analysis, "run", fake_run)
    assert await auto_analyse.analyse_finished_meeting(business_db, scope, m, object()) is True
    business_db.expire_all()
    assert (await business_db.get(PiMeeting, mid)).status == "review"
    assert await notifications(business_db, scope) == 1
    # a second time (a retried job) does not tell the team again
    await auto_analyse.analyse_finished_meeting(business_db, scope, m, object())
    assert await notifications(business_db, scope) == 1
    await pi.close()


async def test_a_call_with_almost_nothing_said_is_left_alone(api, business_db, monkeypatch):
    pi, scope, m = await ready(api, business_db, "379100002", lines=2)
    mid = m.id

    async def never(*a, **k):
        raise AssertionError("an empty call is not read")

    monkeypatch.setattr(analysis, "run", never)
    assert await auto_analyse.analyse_finished_meeting(business_db, scope, m, object()) is False
    business_db.expire_all()
    assert (await business_db.get(PiMeeting, mid)).status == "analysing"
    assert await notifications(business_db, scope) == 0
    await pi.close()


async def test_a_model_that_cannot_be_reached_leaves_the_meeting_for_the_button(
    api, business_db, monkeypatch
):
    pi, scope, m = await ready(api, business_db, "379100003", lines=6)
    mid = m.id

    async def failing(*a, **k):
        raise analysis.AnalysisFailed()

    monkeypatch.setattr(analysis, "run", failing)
    assert await auto_analyse.analyse_finished_meeting(business_db, scope, m, object()) is False
    business_db.expire_all()
    assert (await business_db.get(PiMeeting, mid)).status == "analysing"
    assert await notifications(business_db, scope) == 0
    await pi.close()


async def test_a_long_transcript_is_read_over_several_rounds_and_drafts_stay_drafts(
    api, business_db, monkeypatch
):
    pi, scope, m = await ready(api, business_db, "379100004", lines=8)
    rounds = []

    async def slow(session, scope, meeting, manager, segments, **kw):
        rounds.append(1)
        return analysis.Progress(done=len(rounds), total=3)

    monkeypatch.setattr(analysis, "run", slow)
    assert await auto_analyse.analyse_finished_meeting(business_db, scope, m, object()) is True
    assert len(rounds) == 3  # three parts, read one round at a time
    await pi.close()
