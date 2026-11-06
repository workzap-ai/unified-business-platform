"""Asking a meeting a question: only this meeting's lines are read, the answer comes with its
sources, a meeting with no transcript or another workspace's meeting is refused, and a long
meeting is searched for the question's words before the model sees anything."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body, switch_on

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import qa, qa_routes, routes

pytestmark = pytest.mark.integration


class Model:
    def __init__(self):
        self.seen = []
        self.fail = False

    async def complete_structured(self, scope, output, **kw):
        from app.ai.errors import GatewayUnavailable

        if self.fail:
            raise GatewayUnavailable()
        user = json.loads(kw["messages"][1].content)
        self.seen.append(user)
        lines = user["transcript"]
        hit = next((x for x in lines if "budget" in x["text"]), None)
        if "budget" not in user["question"].lower():
            hit = None
        if hit is None:
            return SimpleNamespace(value=output(found=False))
        return SimpleNamespace(
            value=output(found=True, answer="The budget was named", refs=[hit["line"]])
        )


@pytest.fixture
def model(monkeypatch):
    m = Model()
    monkeypatch.setattr(qa_routes, "build_llm_manager", lambda *a, **k: m)
    monkeypatch.setattr(routes, "build_llm_manager", lambda *a, **k: m)
    monkeypatch.setattr(qa, "RETRY_PAUSES", (0.0, 0.0))
    return m


async def meeting(api, text):
    mid = (await api.post(BASE, json=body())).json()["id"]
    assert (await api.post(f"{BASE}/{mid}/transcript", json={"text": text})).status_code == 200
    return mid


SHORT = "Customer: our budget is about the size of a small shop\nStaff: ok, noted\nCustomer: fine"


async def test_it_answers_from_the_meeting_with_the_lines_it_used(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "366900001")
    await switch_on(api)
    mid = await meeting(api, SHORT)
    got = await api.post(f"{BASE}/{mid}/ask", json={"question": "What did they say about budget?"})
    assert got.status_code == 200, got.text
    out = got.json()
    assert out["found"] is True and out["answer"] == "The budget was named"
    assert out["partial"] is False and [s["ordinal"] for s in out["sources"]] == [0]
    assert out["sources"][0]["speaker"] == "Customer" and "budget" in out["sources"][0]["text"]

    nothing = await api.post(f"{BASE}/{mid}/ask", json={"question": "Who is the delivery driver?"})
    assert nothing.json()["found"] is False and nothing.json()["sources"] == []

    business_db.expire_all()
    events = list(
        await business_db.scalars(select(AuditEvent).where(AuditEvent.action == "pi.meeting_asked"))
    )
    assert len(events) == 2
    assert all("budget" not in json.dumps(e.details) for e in events)  # ids and counts only
    await pi.close()


async def test_a_long_meeting_is_searched_first_and_the_answer_says_it_read_part(
    api, business_db, model, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "366900002")
    await switch_on(api)
    monkeypatch.setattr(qa, "QA_CHARS", 600)
    filler = [
        f"Customer: unrelated chat number {i} about the weather and the road" for i in range(60)
    ]
    filler[37] = "Customer: our budget is fixed at what we said last week"
    mid = await meeting(api, "\n".join(filler))
    out = (await api.post(f"{BASE}/{mid}/ask", json={"question": "budget?"})).json()
    assert out["found"] is True and out["partial"] is True
    assert [s["ordinal"] for s in out["sources"]] == [37]
    sent = model.seen[-1]["transcript"]
    assert len(sent) < 60 and any(x["line"] == 37 for x in sent)  # not the whole meeting
    await pi.close()


async def test_refusals(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "366900003")
    await switch_on(api)
    empty = (await api.post(BASE, json=body())).json()["id"]
    r = await api.post(f"{BASE}/{empty}/ask", json={"question": "anything here?"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TRANSCRIPT_EMPTY"
    mid = await meeting(api, SHORT)
    assert (await api.post(f"{BASE}/{mid}/ask", json={"question": "x"})).status_code == 422
    assert (await api.post(f"{BASE}/{mid}/ask", json={"question": "q" * 301})).status_code == 422
    assert (
        await api.post(f"{BASE}/{mid}/ask", json={"question": "okay then", "x": 1})
    ).status_code == 422
    gone = "00000000-0000-0000-0000-000000000007"
    assert (await api.post(f"{BASE}/{gone}/ask", json={"question": "budget?"})).status_code == 404
    model.fail = True
    down = await api.post(f"{BASE}/{mid}/ask", json={"question": "budget please?"})
    assert down.status_code == 502 and down.json()["error"]["code"] == "MEETING_ASK_UNAVAILABLE"
    await pi.close()


async def test_it_is_off_until_the_workspace_switches_it_on(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "366900004")
    r = await api.post(
        f"{BASE}/00000000-0000-0000-0000-000000000007/ask", json={"question": "hi there"}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "MEETING_INTEL_OFF"
    await pi.close()
