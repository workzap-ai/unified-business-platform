"""A person says who each speaker is. Until a speaker is confirmed as the customer, what they said
is never written to the Problem Map as the customer's own words; once confirmed, it is."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body, switch_on

from app.modules.pi.problem_models import PiProblem
from app.modules.pi_meetings import routes

pytestmark = pytest.mark.integration
# a name is not a role: the speaker is stored as "Speaker 1" with the role unknown
TRANSCRIPT = "Zed: our evening stock keeps running out every week\nStaff: ok, a list by Friday"


class Manager:
    async def complete_structured(self, scope, output, **kw):
        item = {
            "kind": "problem",
            "basis": "stated",
            "text": "evening stock keeps running out",
            "segment_refs": [0],
            "confidence": 90,
        }
        return SimpleNamespace(value=output(insights=[item]))


async def analysed_meeting(api, customer_id, monkeypatch):
    await switch_on(api)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: Manager())
    mid = (await api.post(BASE, json=body(customer_id=customer_id))).json()["id"]
    assert (
        await api.post(f"{BASE}/{mid}/transcript", json={"text": TRANSCRIPT})
    ).status_code == 200
    assert (await api.post(f"{BASE}/{mid}/analyse")).status_code == 200
    detail = (await api.get(f"{BASE}/{mid}")).json()
    return mid, detail


async def problems(db):
    db.expire_all()
    return await db.scalar(select(func.count()).select_from(PiProblem))


async def test_an_unmapped_speaker_is_not_the_customer_and_a_mapped_one_is(
    api, business_db, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "366800001")
    customer = str(conv.customer_id)
    mid, detail = await analysed_meeting(api, customer, monkeypatch)
    speakers = {s["label"]: s for s in detail["speakers"]}
    assert speakers["Speaker 1"]["role"] == "unknown" and speakers["Staff"]["role"] == "staff"
    insight = detail["insights"][0]["id"]

    before = await problems(business_db)
    first = await api.post(f"{BASE}/{mid}/insights/{insight}/approve", json={})
    assert first.status_code == 200 and first.json()["wrote"] == ""
    assert await problems(business_db) == before  # the speaker was not confirmed: nothing written

    # a second meeting: the reviewer says who spoke first, then approves
    mid2, detail2 = await analysed_meeting(api, customer, monkeypatch)
    who = {s["label"]: s["id"] for s in detail2["speakers"]}["Speaker 1"]
    set_ = await api.patch(f"{BASE}/{mid2}/speakers/{who}", json={"role": "customer"})
    assert set_.status_code == 200 and set_.json()["role"] == "customer"
    after = (await api.get(f"{BASE}/{mid2}")).json()
    assert {s["label"]: s["role"] for s in after["speakers"]}["Speaker 1"] == "customer"
    ok = await api.post(f"{BASE}/{mid2}/insights/{detail2['insights'][0]['id']}/approve", json={})
    assert ok.status_code == 200 and ok.json()["wrote"] == "problem"
    assert await problems(business_db) == before + 1
    await pi.close()


async def test_a_bad_role_or_another_meetings_speaker_is_refused(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366800002")
    customer = str(conv.customer_id)
    mid, detail = await analysed_meeting(api, customer, monkeypatch)
    who = detail["speakers"][0]["id"]
    assert (
        await api.patch(f"{BASE}/{mid}/speakers/{who}", json={"role": "boss"})
    ).status_code == 422
    assert (
        await api.patch(f"{BASE}/{mid}/speakers/{who}", json={"role": "customer", "x": 1})
    ).status_code == 422
    other, _ = await analysed_meeting(api, customer, monkeypatch)
    assert (
        await api.patch(f"{BASE}/{other}/speakers/{who}", json={"role": "customer"})
    ).status_code == 404  # a speaker of a different meeting
    gone = "00000000-0000-0000-0000-000000000009"
    assert (
        await api.patch(f"{BASE}/{mid}/speakers/{gone}", json={"role": "customer"})
    ).status_code == 404
    await pi.close()
