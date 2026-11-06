"""pi suggests the next question to the person running a live meeting: off until the workspace
switches it on, only this meeting's newest lines are read, ticks need a cited line, and the audit
entry holds counts, never the question or a line."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import pilot, pilot_routes

pytestmark = pytest.mark.integration
TRANSCRIPT = "Customer: our evening stock keeps running out\nStaff: I see\nCustomer: every week"


class Model:
    def __init__(self):
        self.fail = False
        self.seen = []
        self.question = "How often does the stock run out?"

    async def complete_structured(self, scope, output, **kw):
        from app.ai.errors import GatewayUnavailable

        if self.fail:
            raise GatewayUnavailable()
        user = json.loads(kw["messages"][1].content)
        self.seen.append(user)
        first = user["transcript"][0]["line"] if user["transcript"] else 0
        return SimpleNamespace(
            value=output(question=self.question, covered=[{"item": 0, "refs": [first]}])
        )


@pytest.fixture
def model(monkeypatch):
    m = Model()
    monkeypatch.setattr(pilot_routes, "build_llm_manager", lambda *a, **k: m)
    monkeypatch.setattr(pilot, "RETRY_PAUSES", (0.0,))
    return m


async def switch(api, pilot_on=True):
    brain = {"meeting_intel": True, "meeting_pilot": pilot_on}
    r = await api.patch(
        "/api/v1/pi/settings/response_rules", json={"value": {"pi_mode": "brain", "brain": brain}}
    )
    assert r.status_code == 200, r.text


async def meeting(api, text=TRANSCRIPT):
    mid = (await api.post(BASE, json=body())).json()["id"]
    if text:
        assert (await api.post(f"{BASE}/{mid}/transcript", json={"text": text})).status_code == 200
    return mid


async def test_it_is_off_until_the_workspace_switches_it_on(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "367000001")
    await switch(api, pilot_on=False)
    mid = await meeting(api)
    r = await api.post(f"{BASE}/{mid}/pilot/suggest", json={"checklist": ["problem"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "MEETING_PILOT_OFF"
    assert model.seen == []
    await pi.close()


async def test_it_suggests_one_question_and_ticks_what_a_line_answers(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "367000002")
    await switch(api)
    mid = await meeting(api)
    r = await api.post(f"{BASE}/{mid}/pilot/suggest", json={"checklist": ["problem", "budget"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["question"] == "How often does the stock run out?" and out["lines_read"] == 3
    assert [c["done"] for c in out["checklist"]] == [True, False]
    assert out["checklist"][0]["refs"]
    assert model.seen[-1]["transcript"][0]["role"] in {"customer", "unknown", "staff"}

    business_db.expire_all()
    events = list(
        await business_db.scalars(
            select(AuditEvent).where(AuditEvent.action == "pi.meeting_suggested")
        )
    )
    assert len(events) == 1 and "stock" not in json.dumps(events[0].details)
    await pi.close()


async def test_a_question_that_breaks_a_rule_is_not_shown(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "367000003")
    await switch(api)
    mid = await meeting(api)
    model.question = "Would Rs 5000 a month suit you?"
    out = (await api.post(f"{BASE}/{mid}/pilot/suggest", json={"checklist": ["problem"]})).json()
    assert out["question"] == "" and out["checklist"][0]["done"] is True
    await pi.close()


async def test_an_empty_meeting_reads_nothing_and_asks_the_model_nothing(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "367000004")
    await switch(api)
    mid = await meeting(api, text="")
    out = (await api.post(f"{BASE}/{mid}/pilot/suggest", json={"checklist": ["problem"]})).json()
    assert out["question"] == "" and out["lines_read"] == 0 and model.seen == []
    await pi.close()


async def test_refusals_and_a_provider_that_is_down(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "367000005")
    await switch(api)
    mid = await meeting(api)
    too_many = {"checklist": [f"i{n}" for n in range(9)]}
    assert (await api.post(f"{BASE}/{mid}/pilot/suggest", json=too_many)).status_code == 422
    assert (await api.post(f"{BASE}/{mid}/pilot/suggest", json={"x": 1})).status_code == 422
    gone = "00000000-0000-0000-0000-000000000005"
    assert (await api.post(f"{BASE}/{gone}/pilot/suggest", json={})).status_code == 404
    model.fail = True
    down = await api.post(f"{BASE}/{mid}/pilot/suggest", json={"checklist": []})
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_PILOT_UNAVAILABLE"
    await pi.close()
