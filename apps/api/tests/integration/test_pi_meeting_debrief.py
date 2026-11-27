"""An agent's debrief of a meeting: its own starter questions answered from the meeting's lines,
kept as the meeting's debrief, replaced when run again, and gone with the meeting."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body, switch_on

from app.modules.pi_meetings import agent_routes, agents, qa, qa_routes, routes
from app.modules.pi_meetings.models import PiMeetingChat, PiMeetingChatMessage

pytestmark = pytest.mark.integration

SHORT = "Customer: our budget is about the size of a small shop\nStaff: ok, noted\nCustomer: fine"


class Model:
    def __init__(self):
        self.system: list[str] = []
        self.questions: list[str] = []

    async def complete_structured(self, scope, output, **kw):
        self.system.append(kw["messages"][0].content)
        user = json.loads(kw["messages"][1].content)
        self.questions.append(user["question"])
        line = user["transcript"][0]["line"]
        return SimpleNamespace(
            value=output(found=True, answer=f"Answer to: {user['question'][:30]}", refs=[line])
        )


@pytest.fixture
def model(monkeypatch):
    m = Model()
    for module in (agent_routes, qa_routes, routes):
        monkeypatch.setattr(module, "build_llm_manager", lambda *a, **k: m, raising=False)
    monkeypatch.setattr(qa, "RETRY_PAUSES", (0.0, 0.0))
    return m


def test_a_custom_agent_card_is_never_empty() -> None:
    text = (
        "Look at the call as a patient sales coach. Note the objections that came up! "
        "Keep the tone warm and direct, and use short sentences so a busy owner can read them."
    )
    focus = agents.focus_of(text)
    assert len(focus) == 3 and all(len(f) <= agents.FOCUS_CHARS for f in focus)
    assert focus[0] == "Look at the call as a patient sales coach"
    assert agents.focus_of("short") == []
    assert len(agents.debrief_questions("sales_coach")) == 3
    assert agents.debrief_questions("some-custom-id") == agents.debrief_questions("pi")


async def test_a_debrief_runs_the_agents_questions_and_keeps_the_answers(api, business_db, model):
    pi, conv, scope = await workspace(api, business_db, "368000001")
    await switch_on(api)
    mid = (await api.post(BASE, json=body())).json()["id"]
    await api.post(f"{BASE}/{mid}/transcript", json={"text": SHORT})
    empty = (await api.get(f"{BASE}/{mid}/debrief")).json()
    assert empty["items"] == [] and empty["chat"] is None

    await api.put(f"{BASE}/{mid}/agent", json={"agent_key": "sales_coach"})
    ran = await api.post(f"{BASE}/{mid}/debrief")
    assert ran.status_code == 200, ran.text
    out = ran.json()
    questions = [i["question"] for i in out["items"]]
    assert questions == list(agents.debrief_questions("sales_coach"))
    assert all(i["found"] and i["answer"] and i["sources"] for i in out["items"])
    assert out["agent_key"] == "sales_coach" and out["chat"]["title"] == "Debrief"
    assert all("Sales Coach" in s for s in model.system)  # the agent's focus is in every prompt

    again = (await api.post(f"{BASE}/{mid}/debrief")).json()  # replaces, never piles up
    assert len(again["items"]) == 3
    got = (await api.get(f"{BASE}/{mid}/debrief")).json()
    assert [i["question"] for i in got["items"]] == questions
    chats = (await api.get(f"{BASE}/{mid}/chats")).json()["chats"]
    assert len([c for c in chats if c["title"] == "Debrief"]) == 1

    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingChatMessage)) == 6
    assert (await api.delete(f"{BASE}/{mid}")).status_code == 200
    business_db.expire_all()
    assert await business_db.scalar(select(func.count()).select_from(PiMeetingChat)) == 0
    await pi.close()


async def test_a_debrief_needs_a_transcript_and_reports_a_model_that_is_down(
    api, business_db, model, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "368000002")
    await switch_on(api)
    empty = (await api.post(BASE, json=body())).json()["id"]
    r = await api.post(f"{BASE}/{empty}/debrief")
    assert r.status_code == 422 and r.json()["error"]["code"] == "TRANSCRIPT_EMPTY"

    mid = (await api.post(BASE, json=body())).json()["id"]
    await api.post(f"{BASE}/{mid}/transcript", json={"text": SHORT})

    async def down(*a, **k):
        raise qa.AskFailed("unavailable")

    monkeypatch.setattr(qa, "ask", down)
    r = await api.post(f"{BASE}/{mid}/debrief")
    assert r.status_code == 502 and r.json()["error"]["code"] == "MEETING_ASK_UNAVAILABLE"
    assert (await api.get(f"{BASE}/{mid}/debrief")).json()["items"] == []  # nothing half-saved
    await pi.close()
