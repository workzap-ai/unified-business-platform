"""pi knows the client in a meeting, as in chat, without guessing: no memory means no pretending, a
returning customer is asked who is speaking first, the memory is used only after a clear yes, and a
different person on the link never gets it and never writes into the customer's record."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_pi_meeting_data import workspace
from test_pi_meeting_routes import BASE, body
from test_pi_meeting_voice import JOIN, WEBM, lines, switch, turn

from app.modules.audit.models import AuditEvent
from app.modules.pi_meetings import meeting_memory, voice, voice_routes
from app.modules.pi_meetings.models import PiMeeting

pytestmark = pytest.mark.integration

KNOWN = {
    "records": [
        {"kind": "name", "status": "owner_said", "text": "name: Ayesha", "source": "facts"},
        {
            "kind": "problem",
            "status": "owner_said",
            "text": "P1 evening stock runs out",
            "source": "problems",
        },
    ]
}


class Brain:
    """Speech-to-text and the model; keeps what the model was sent."""

    def __init__(self):
        self.heard = "yes"
        self.reply = "How often does that happen?"
        self.calls = []

    async def transcribe(self, scope, audio, mime, **kw):
        return SimpleNamespace(text=self.heard, language="en")

    async def complete_structured(self, scope, output, **kw):
        self.calls.append(
            {"system": kw["messages"][0].content, "user": json.loads(kw["messages"][1].content)}
        )
        return SimpleNamespace(value=output(reply=self.reply))


@pytest.fixture
def brain(monkeypatch):
    b = Brain()
    monkeypatch.setattr(voice_routes, "build_llm_manager", lambda *a, **k: b)
    return b


def memory_is(monkeypatch, block):
    async def fake(session, scope, meeting):
        return block if meeting.customer_id is not None else {}

    monkeypatch.setattr(meeting_memory, "load", fake)


async def room(api, conv, *, linked=True):
    """A meeting (linked to the customer unless told otherwise): a link, one guest, pi on speak."""
    extra = {"customer_id": str(conv.customer_id)} if linked else {}
    mid = (await api.post(BASE, json=body(**extra))).json()["id"]
    invite = (await api.post(f"{BASE}/{mid}/invite", json={})).json()["token"]
    guest = (await api.post(f"{JOIN}/{invite}", json={"name": "Visitor", "consent": True})).json()[
        "guest_token"
    ]
    r = await api.patch(f"{BASE}/{mid}/pi-mode", json={"mode": "speak"})
    assert r.status_code == 200, r.text
    return mid, guest


async def audits(db):
    db.expire_all()
    rows = await db.scalars(select(AuditEvent).where(AuditEvent.action == "pi.meeting_pi_turn"))
    return [e.details for e in rows]


async def test_no_memory_means_the_normal_opening_and_no_pretending(
    api, business_db, brain, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "370100001")
    await switch(api)
    memory_is(monkeypatch, {})  # a new customer: nothing is known
    mid, guest = await room(api, conv)
    words = (await turn(api, guest)).json()["reply"]
    assert voice.IDENTITY_MARK not in words and "AI" in words and words.endswith("?")
    await turn(api, guest, WEBM)
    assert "what_i_know" not in brain.calls[-1]["user"]
    assert voice.MEMORY_NOTE not in brain.calls[-1]["system"]
    assert (await audits(business_db))[-1]["memory"] is False
    await pi.close()


async def test_a_meeting_with_no_customer_has_no_memory_to_use(
    api, business_db, brain, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "370100002")
    await switch(api)
    memory_is(monkeypatch, KNOWN)  # memory exists, but this meeting is linked to nobody
    mid, guest = await room(api, conv, linked=False)
    words = (await turn(api, guest)).json()["reply"]
    assert voice.IDENTITY_MARK not in words
    await turn(api, guest, WEBM)
    assert "what_i_know" not in brain.calls[-1]["user"]
    await pi.close()


async def test_a_returning_customer_is_asked_who_is_speaking_and_a_yes_unlocks_memory(
    api, business_db, brain, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "370100003")
    await switch(api)
    memory_is(monkeypatch, KNOWN)
    mid, guest = await room(api, conv)
    opening = (await turn(api, guest)).json()["reply"]
    assert opening.count("?") == 1 and "AI" in opening and "Am I speaking with Ayesha?" in opening
    brain.heard = "yes, it is me"
    out = (await turn(api, guest, WEBM)).json()
    assert out["reply"] == "How often does that happen?"
    sent = brain.calls[-1]
    assert sent["user"]["what_i_know"]["records"][1]["text"].endswith("evening stock runs out")
    assert voice.MEMORY_NOTE.strip().splitlines()[0] in sent["system"]
    last = (await audits(business_db))[-1]
    assert last["identity"] == "confirmed" and last["memory"] is True
    assert "Ayesha" not in json.dumps(last)  # the audit holds no words
    await pi.close()


async def test_someone_else_on_the_link_gets_no_memory_and_a_neutral_question(
    api, business_db, brain, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "370100004")
    await switch(api)
    memory_is(monkeypatch, KNOWN)
    mid, guest = await room(api, conv)
    await turn(api, guest)
    brain.heard = "no, this is her brother"
    out = (await turn(api, guest, WEBM)).json()
    assert out["reply"] == voice.NOT_THEM and out["fallback"] is False
    assert brain.calls == []  # the model was not even asked
    brain.heard = "I handle the deliveries, our stock runs out"
    nxt = (await turn(api, guest, WEBM)).json()
    assert nxt["reply"] == "How often does that happen?"
    assert (
        "what_i_know" not in brain.calls[-1]["user"]
    )  # still no memory, for the whole conversation
    brain.heard = "yes"  # a later yes cannot undo the first no
    await turn(api, guest, WEBM)
    assert "what_i_know" not in brain.calls[-1]["user"]
    seen = await audits(business_db)
    assert [a["identity"] for a in seen][-3:] == ["denied", "denied", "denied"]
    assert all(a["memory"] is False for a in seen)
    # what a different person said is on the transcript but is not attributed to the customer
    said = await lines(business_db, mid)
    assert any("brother" in t for t in said)
    detail = (await api.get(f"{BASE}/{mid}")).json()
    roles = {s["label"]: s["role"] for s in detail["speakers"]}
    assert (
        roles["Visitor"] == "other"
    )  # marked, so a reviewer sees it and nothing is taken as theirs
    assert "customer" not in roles.values()
    await pi.close()


async def test_an_unclear_answer_does_not_unlock_memory(api, business_db, brain, monkeypatch):
    pi, conv, scope = await workspace(api, business_db, "370100005")
    await switch(api)
    memory_is(monkeypatch, KNOWN)
    mid, guest = await room(api, conv)
    await turn(api, guest)
    brain.heard = "hello who is this, what is this about"
    await turn(api, guest, WEBM)
    assert "what_i_know" not in brain.calls[-1]["user"]
    assert (await audits(business_db))[-1]["identity"] == "unclear"
    await pi.close()


async def test_the_real_memory_door_returns_nothing_for_an_unknown_customer_or_none(
    api, business_db
):
    pi, conv, scope = await workspace(api, business_db, "370100006")

    def meeting(customer_id):
        return PiMeeting(
            tenant_id=scope.tenant_id,
            environment_id=scope.environment_id,
            customer_id=customer_id,
            language="",
        )

    assert await meeting_memory.load(business_db, scope, meeting(None)) == {}
    assert await meeting_memory.load(business_db, scope, meeting(uuid4())) == {}
    known = await meeting_memory.load(business_db, scope, meeting(conv.customer_id))
    assert isinstance(known, dict)  # whatever the customer's chat left; never an error
    await pi.close()


async def test_a_reply_that_recites_memory_is_replaced_by_the_safe_line(
    api, business_db, brain, monkeypatch
):
    pi, conv, scope = await workspace(api, business_db, "370100007")
    await switch(api)
    recited = {
        "records": [
            {"kind": "name", "status": "owner_said", "text": "name: Ayesha", "source": "facts"},
            {"kind": "order", "status": "owner_said", "text": "order 4471 was late", "source": "x"},
            {"kind": "guess", "status": "pi_inferred", "text": "P9 secret guess", "source": "x"},
        ]
    }
    memory_is(monkeypatch, recited)
    mid, guest = await room(api, conv)
    await turn(api, guest)
    brain.heard = "yes"
    brain.reply = "How is order 4471 going?"  # a number the person never said
    out = (await turn(api, guest, WEBM)).json()
    assert out["fallback"] is True and "4471" not in out["reply"]
    # and a pi guess never reaches the prompt at all
    assert all(
        "secret guess" not in r["text"] for r in brain.calls[-1]["user"]["what_i_know"]["records"]
    )
    await pi.close()
