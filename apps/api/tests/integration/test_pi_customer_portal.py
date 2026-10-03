"""PI Customer: a customer signs in with their WhatsApp number and a code sent on
WhatsApp, then sees only their own conversations with businesses that allow it."""

import json
import re
from types import SimpleNamespace

import httpx
import pytest
from pi_saas_support import FakeProvider, configure, pi_client
from sqlalchemy import select
from test_pi_saas import _is_read_receipt, _kapso, _message_event, _ready_business, _run_jobs
from test_pi_service_conversations import mock_turns, turn

from app.ai.manager import LLMManager
from app.modules.pi.models import PiConversation, PiHandoff, PiSettings
from app.modules.pi_customer.access import CSRF_COOKIE, MemoryCodeStore
from app.modules.pi_customer.service import Issue, IssueReport

pytestmark = pytest.mark.integration

PORTAL = "/api/v1/pi-app/customer-portal"
NUMBER, CUSTOMER = "6200000001", "15550007001"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.pi_customer_codes = MemoryCodeStore()
    return fake


def _sent_codes(provider: FakeProvider, to: str) -> list[str]:
    codes = []
    for request in provider.requests:
        if not request.url.path.endswith("/messages") or _is_read_receipt(request):
            continue
        body = json.loads(request.content)
        text = body.get("text", {}).get("body", "")
        found = re.search(r"code: \*([0-9]{6})\*", text)
        if found and body.get("to") == to:
            codes.append(found.group(1))
    return codes


async def _business_with_chat(app, provider, db, monkeypatch, name="Portal Co", number=NUMBER):
    mock_turns(monkeypatch, *[turn(reply="Ji, website ke liye kaunsa feature chahiye?")] * 3)
    client, _ = await _ready_business(app, provider, db, name, number)
    await _kapso(
        client,
        "whatsapp.message.received",
        _message_event(number, CUSTOMER, "Website chahiye", f"wamid.p-{number}"),
    )
    await _run_jobs(app, provider, db)
    return client


async def _sign_in(app, provider, phone: str = "+1 555 000 7001") -> httpx.AsyncClient:
    customer = pi_client(app)
    sent = await customer.post(f"{PORTAL}/code", json={"phone": phone})
    assert sent.status_code == 202, sent.text
    code = _sent_codes(provider, "".join(c for c in phone if c.isdigit()))[-1]
    verified = await customer.post(f"{PORTAL}/verify", json={"phone": phone, "code": code})
    assert verified.status_code == 200, verified.text
    assert verified.json()["phone"].endswith(phone[-4:])
    return customer


async def test_customer_signs_in_with_a_whatsapp_code_and_sees_the_conversation(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    anonymous = pi_client(app)
    assert (await anonymous.get(f"{PORTAL}/conversations")).status_code == 401
    customer = await _sign_in(app, provider)
    listed = (await customer.get(f"{PORTAL}/conversations")).json()
    assert [c["business"] for c in listed] == ["Test business"]  # the WhatsApp name
    detail = (await customer.get(f"{PORTAL}/conversations/{listed[0]['id']}")).json()
    senders = [(m["from"], m["body"]) for m in detail["messages"]]
    assert ("you", "Website chahiye") in senders
    assert ("assistant", "Ji, website ke liye kaunsa feature chahiye?") in senders
    # Internal details never reach the customer.
    flat = json.dumps(detail)
    assert "summary" not in flat and "agent_key" not in flat and "sent_by" not in flat
    # The sign-in code itself was never stored as a conversation message.
    assert all("PI Customer code" not in m["body"] for m in detail["messages"])
    await business.aclose()
    await customer.aclose()
    await anonymous.aclose()


async def test_codes_are_not_sent_to_unknown_numbers_and_expire_after_wrong_tries(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    stranger = pi_client(app)
    response = await stranger.post(f"{PORTAL}/code", json={"phone": "+1 555 000 9999"})
    assert response.status_code == 202  # same answer: never reveals who has chats
    assert _sent_codes(provider, "15550009999") == []
    customer = pi_client(app)
    await customer.post(f"{PORTAL}/code", json={"phone": f"+{CUSTOMER}"})
    code = _sent_codes(provider, CUSTOMER)[-1]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        bad = await customer.post(f"{PORTAL}/verify", json={"phone": f"+{CUSTOMER}", "code": wrong})
        assert bad.status_code == 400
    late = await customer.post(f"{PORTAL}/verify", json={"phone": f"+{CUSTOMER}", "code": code})
    assert late.status_code == 400  # five wrong tries end the code
    await business.aclose()
    await stranger.aclose()
    await customer.aclose()


async def test_customers_never_see_other_numbers_or_businesses_that_turned_it_off(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    # Another customer of the same business, signed in with their own number.
    await _kapso(
        business,
        "whatsapp.message.received",
        _message_event(NUMBER, "15550007002", "Hello", "wamid.p-other"),
    )
    await _run_jobs(app, provider, business_db)
    other = await _sign_in(app, provider, "+1 555 000 7002")
    assert [c["id"] for c in (await other.get(f"{PORTAL}/conversations")).json()] != [
        conversation_id
    ]
    assert (await other.get(f"{PORTAL}/conversations/{conversation_id}")).status_code == 404
    # The business turns PI Customer off: its conversations disappear from the portal.
    conversation = await business_db.get(PiConversation, conversation_id)
    policy = await business_db.scalar(
        select(PiSettings).where(
            PiSettings.tenant_id == conversation.tenant_id,
            PiSettings.environment_id == conversation.environment_id,
        )
    )
    policy.whatsapp_config = {**policy.whatsapp_config, "customer_portal": False}
    await business_db.commit()
    assert (await customer.get(f"{PORTAL}/conversations")).json() == []
    for client in (business, customer, other):
        await client.aclose()


async def test_customer_can_ask_for_a_person_with_csrf(app, provider, business_db, monkeypatch):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    path = f"{PORTAL}/conversations/{conversation_id}/team"
    assert (await customer.post(path)).status_code == 403  # no CSRF header
    asked = await customer.post(path, headers={"x-csrf-token": customer.cookies[CSRF_COOKIE]})
    assert asked.status_code == 200 and asked.json()["status"] == "with_team"
    handoff = await business_db.scalar(
        select(PiHandoff).where(PiHandoff.conversation_id == conversation_id)
    )
    assert handoff is not None and handoff.reason == "customer_request"
    detail = (await customer.get(f"{PORTAL}/conversations/{conversation_id}")).json()
    assert detail["with_team"] is True
    await business.aclose()
    await customer.aclose()


async def test_ai_lists_the_customers_requests_once_per_new_message(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    calls = []

    async def complete(self, scope, output, **kwargs):
        assert output is IssueReport and kwargs["purpose"] == "pi_customer_issues"
        assert "Website chahiye" in kwargs["messages"][-1].text()
        calls.append(1)
        report = IssueReport(
            issues=[
                Issue(
                    title="Website banwana",
                    category="inquiry",
                    status="open",
                    summary="Aap ne website ke baare mein poocha.",
                    next_step="Features batayein.",
                )
            ]
        )
        return SimpleNamespace(value=report, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    path = f"{PORTAL}/conversations/{conversation_id}/issues"
    first = (await customer.get(path)).json()
    assert first["available"] and first["issues"][0]["title"] == "Website banwana"
    again = (await customer.get(path)).json()
    assert again["issues"] == first["issues"] and calls == [1]  # cached until a new message
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["issues_open"] == 1
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    # Pi's own brief keys are kept beside the cached list.
    assert "customer_issues" in conversation.service_brief
    await business.aclose()
    await customer.aclose()
