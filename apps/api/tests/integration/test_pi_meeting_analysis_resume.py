"""A long meeting on a rate-limited AI provider is analysed over several calls.

Every part that was read is saved at once, the meeting remembers which parts are done, the next call
carries on from the next one, and only a provider that refuses everything fails a call (and even
then nothing is lost)."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body, switch_on

from app.ai.errors import GatewayUnavailable
from app.modules.pi_meetings import analyse as stage
from app.modules.pi_meetings import routes
from app.modules.pi_meetings.models import PiMeeting, PiMeetingInsight

pytestmark = pytest.mark.integration


class Provider:
    """A model that answers one problem per part it is shown, and can be told to refuse."""

    def __init__(self):
        self.refuse = False
        self.refuse_from_part = None  # refuse any part whose first line number is at or after this
        self.calls = []

    async def complete_structured(self, scope, output, **kw):
        user = json.loads(kw["messages"][1].content)
        first = user["transcript"][0]["line"]
        self.calls.append(first)
        if self.refuse or (self.refuse_from_part is not None and first >= self.refuse_from_part):
            raise GatewayUnavailable()
        item = {"kind": "problem", "basis": "inferred", "text": f"problem from line {first}"}
        return SimpleNamespace(value=output(insights=[item]))


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: p)
    monkeypatch.setattr(stage, "CHUNK_PAUSES", (0.0, 0.0))  # no real waiting in a test
    monkeypatch.setattr(stage, "CHUNK_CHARS", 400)  # a short transcript becomes several parts
    return p


async def meeting_with_transcript(api, text_lines=24):
    mid = (await api.post(BASE, json=body())).json()["id"]
    text = "\n".join(
        f"Customer: line number {i} about the stock and the list " * 1 for i in range(text_lines)
    )
    assert (await api.post(f"{BASE}/{mid}/transcript", json={"text": text})).status_code == 200
    return mid


async def pending(db):
    db.expire_all()
    return sorted(
        await db.scalars(
            select(PiMeetingInsight.text).where(PiMeetingInsight.review_status == "pending")
        )
    )


async def status_and_progress(db):
    db.expire_all()
    meeting = await db.scalar(select(PiMeeting))
    return meeting.status, meeting.analysis_progress


async def test_a_part_the_provider_refuses_stops_this_call_but_keeps_what_was_read(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "366700001")
    await switch_on(api)
    mid = await meeting_with_transcript(api)

    provider.refuse_from_part = 8  # the later parts are rate limited
    first = await api.post(f"{BASE}/{mid}/analyse")
    assert first.status_code == 200, first.text
    got = first.json()
    assert (
        got["complete"] is False and 0 < got["done"] < got["total"] and got["status"] == "analysing"
    )
    kept = await pending(business_db)
    assert kept and len(kept) == got["done"]  # each part that was read is already saved
    state, progress = await status_and_progress(business_db)
    assert state == "analysing" and len(progress["done"]) == got["done"]

    # the provider recovers: the next call reads ONLY the parts that are left
    provider.refuse_from_part = None
    provider.calls.clear()
    second = await api.post(f"{BASE}/{mid}/analyse")
    done = second.json()
    assert done["complete"] is True and done["done"] == done["total"] and done["status"] == "review"
    assert len(provider.calls) == got["total"] - got["done"]  # nothing was read twice
    assert len(await pending(business_db)) == got["total"]  # one problem per part, none lost
    state, progress = await status_and_progress(business_db)
    assert state == "review" and progress is None  # finished: nothing left to resume
    await pi.close()


async def test_a_provider_that_refuses_everything_fails_the_call_and_the_next_one_works(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "366700002")
    await switch_on(api)
    mid = await meeting_with_transcript(api)
    provider.refuse = True
    down = await api.post(f"{BASE}/{mid}/analyse")
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_ANALYSIS_FAILED"
    assert (await status_and_progress(business_db))[0] == "failed"
    assert await pending(business_db) == []

    provider.refuse = False
    ok = await api.post(f"{BASE}/{mid}/analyse")
    assert ok.status_code == 200 and ok.json()["complete"] is True
    assert (await status_and_progress(business_db))[0] == "review"
    await pi.close()


async def test_every_call_reads_at_least_one_part_even_with_no_time_left(
    api, business_db, provider, monkeypatch
):
    monkeypatch.setattr(stage, "ANALYSE_BUDGET_S", 0.0)  # no time: one part per call
    pi, conv, scope = await workspace(api, business_db, "366700003")
    await switch_on(api)
    mid = await meeting_with_transcript(api)
    answers = []
    for _ in range(40):
        answer = (await api.post(f"{BASE}/{mid}/analyse")).json()
        answers.append((answer["done"], answer["total"]))
        if answer["complete"]:
            break
    assert answers[0][0] == 1 and answers[-1][0] == answers[-1][1] > 2  # one more part every call
    assert [d for d, _ in answers] == sorted({d for d, _ in answers})  # never goes backwards
    assert len(provider.calls) == answers[-1][1]  # every part exactly once
    await pi.close()


async def test_a_transcript_that_changed_starts_over_and_reviewed_insights_are_kept(
    api, business_db, provider
):
    pi, conv, scope = await workspace(api, business_db, "366700004")
    await switch_on(api)
    mid = await meeting_with_transcript(api)
    assert (await api.post(f"{BASE}/{mid}/analyse")).json()["complete"] is True
    business_db.expire_all()
    first = await business_db.scalar(select(PiMeetingInsight.id).order_by(PiMeetingInsight.text))
    approved = await api.post(f"{BASE}/{mid}/insights/{first}/reject")  # a person reviewed it
    assert approved.status_code == 200

    # run again: the pending ones are replaced, the reviewed one is not touched or doubled
    provider.calls.clear()
    again = (await api.post(f"{BASE}/{mid}/analyse")).json()
    assert again["complete"] is True and len(provider.calls) == again["total"]
    business_db.expire_all()
    rows = list(await business_db.scalars(select(PiMeetingInsight)))
    assert sum(1 for r in rows if r.review_status == "rejected") == 1
    texts = [r.text for r in rows]
    assert len(texts) == len(set(texts))  # nothing is listed twice
    await pi.close()


def test_the_signature_changes_with_the_transcript_and_the_chunk_size(monkeypatch):
    from app.modules.pi_meetings.insight_rules import Segment

    parts = [[Segment(0, "a" * 50, "S"), Segment(1, "b" * 50, "S")], [Segment(2, "c" * 50, "S")]]
    same = stage.signature([list(p) for p in parts])
    assert same == stage.signature(parts)
    longer = parts + [[Segment(3, "d", "S")]]
    assert stage.signature(longer) != same  # more lines: a different transcript
    edited = [[Segment(0, "a" * 51, "S"), Segment(1, "b" * 50, "S")], parts[1]]
    assert stage.signature(edited) != same
    monkeypatch.setattr(stage, "CHUNK_CHARS", 999)
    assert stage.signature(parts) != same  # cut differently: the old progress does not apply
