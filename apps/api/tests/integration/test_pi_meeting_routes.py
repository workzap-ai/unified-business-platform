"""The /pi/meeting-intel API end to end: off unless the workspace switched it on, consent before
anything is stored, import then analyse then approve into the brain, search, and delete."""

from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import workspace

from app.modules.pi.problem_models import PiProblem
from app.modules.pi_meetings import routes

pytestmark = pytest.mark.integration
BASE = "/api/v1/pi/meeting-intel"
TRANSCRIPT = (
    "Customer: our evening stock keeps running out every week\n"
    "Staff: ok, we will send a stock list by Friday\n"
    "Customer: fine"
)


class FakeManager:
    async def complete_structured(self, scope, output, **kw):
        items = [
            {
                "kind": "problem",
                "basis": "stated",
                "text": "evening stock keeps running out",
                "segment_refs": [0],
                "confidence": 90,
            },
            {"kind": "requirement_implicit", "basis": "inferred", "text": "needs stock alerts"},
            {"kind": "decision", "basis": "stated", "text": "no source cited", "segment_refs": []},
        ]
        return SimpleNamespace(value=output(insights=items))


async def switch_on(api):
    response = await api.patch(
        "/api/v1/pi/settings/response_rules",
        json={"value": {"pi_mode": "brain", "brain": {"meeting_intel": True}}},
    )
    assert response.status_code == 200, response.text


def body(**kw):
    return {"title": "Kickoff call", "consent_given": True, **kw}


async def test_it_is_off_until_the_workspace_switches_it_on(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366000001")
    for call in (api.get(BASE), api.post(BASE, json=body())):
        response = await call
        assert (
            response.status_code == 403 and response.json()["error"]["code"] == "MEETING_INTEL_OFF"
        )
    await pi.close()


async def test_consent_comes_first_and_an_unknown_customer_is_not_found(api, business_db):
    pi, conv, scope = await workspace(api, business_db, "366000002")
    await switch_on(api)
    refused = await api.post(BASE, json=body(consent_given=False))
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "MEETING_CONSENT_REQUIRED"
    missing = await api.post(BASE, json=body(customer_id="00000000-0000-0000-0000-000000000001"))
    assert missing.status_code == 404
    assert (await api.get(f"{BASE}/00000000-0000-0000-0000-000000000002")).status_code == 404
    assert (await api.get(BASE)).json()["items"] == []  # nothing was stored
    await pi.close()


async def test_import_analyse_approve_search_and_delete(api, business_db, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "366000003")
    await switch_on(api)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: FakeManager())
    created = await api.post(BASE, json=body())
    assert created.status_code == 201, created.text
    mid = created.json()["id"]
    assert created.json()["consent_at"] and created.json()["status"] == "created"

    imported = await api.post(f"{BASE}/{mid}/transcript", json={"text": TRANSCRIPT})
    assert imported.status_code == 200, imported.text
    assert imported.json()["lines"] == 3 and imported.json()["speakers"] == 2

    analysed = await api.post(f"{BASE}/{mid}/analyse")
    assert analysed.status_code == 200, analysed.text
    assert analysed.json()["insights"] == 2 and analysed.json()["dropped"] == 1
    assert analysed.json()["status"] == "review"

    detail = (await api.get(f"{BASE}/{mid}")).json()
    assert [s["speaker"] for s in detail["segments"]] == ["Customer", "Staff", "Customer"]
    by_kind = {i["kind"]: i for i in detail["insights"]}
    assert by_kind["problem"]["review_status"] == "pending"

    # not linked to a customer: approving is refused and nothing reaches the brain
    first = by_kind["problem"]["id"]
    refused = await api.post(f"{BASE}/{mid}/insights/{first}/approve", json={})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "MEETING_NOT_LINKED"

    linked = await api.patch(f"{BASE}/{mid}/customer", json={"customer_id": str(conv.customer_id)})
    assert linked.status_code == 200
    before = await business_db.scalar(select(func.count()).select_from(PiProblem))
    approved = await api.post(f"{BASE}/{mid}/insights/{first}/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["wrote"] == "problem" and approved.json()["review_status"] == "approved"
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiProblem)) == before + 1
    again = await api.post(f"{BASE}/{mid}/insights/{first}/approve", json={})
    assert again.status_code == 200
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiProblem)) == before + 1

    # the AI's own conclusion is approved as information only; a rejection sticks
    guess = by_kind["requirement_implicit"]["id"]
    rejected = await api.post(f"{BASE}/{mid}/insights/{guess}/reject")
    assert rejected.status_code == 200 and rejected.json()["review_status"] == "rejected"
    late = await api.post(f"{BASE}/{mid}/insights/{guess}/approve", json={})
    assert late.status_code == 409

    found = (await api.get(f"{BASE}/search", params={"q": "stock"})).json()["items"]
    assert found and found[0]["meeting_id"] == mid
    assert (await api.get(f"{BASE}/search", params={"q": "zzzzqqq"})).json()["items"] == []

    gone = await api.delete(f"{BASE}/{mid}")
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert (await api.get(f"{BASE}/{mid}")).status_code == 404
    await pi.close()
