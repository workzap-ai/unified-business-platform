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
    assert listed["issues_open"] == 1 and listed["issues_fresh"] is True
    assert listed["counts"]["waiting_on_us"] == 1  # "noted": pi's turn, not the customer's
    [issue] = listed["issues"]
    assert issue["title"] == "Website banwana" and issue["stage"] == "noted"
    assert issue["department_name"] == "Customer support"
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    # Pi's own brief keys are kept beside the cached list.
    assert "customer_issues" in conversation.service_brief
    await business.aclose()
    await customer.aclose()


def _mock_issues(monkeypatch, *reports: IssueReport) -> list[dict]:
    """Scripted request lists; returns the context pi was given each time."""
    seen: list[dict] = []
    queue = list(reports)

    async def complete(self, scope, output, **kwargs):
        assert output is IssueReport
        seen.append(json.loads(kwargs["messages"][-1].text()))
        report = queue.pop(0) if len(queue) > 1 else queue[0]
        return SimpleNamespace(value=report, response=SimpleNamespace(attempts=[]))

    monkeypatch.setattr(LLMManager, "complete_structured", complete)
    return seen


THREE = IssueReport(
    headline="Kitne staff ERP app use karenge?",
    issues=[
        Issue(
            title="Mobile ERP app",
            stage="need_answer",
            open_question="Kitne staff ERP app use karenge?",
            original_words="mujhe erp chahiye mobile pe",
            next_step="You: staff ki tadaad batayein",
        ),
        Issue(
            title="Furniture website",
            stage="on_it",
            # A question on the team's turn is not the customer's to answer.
            open_question="Should we use Shopify?",
            next_step="Team: scope bana rahi hai",
        ),
        Issue(title="Features PDF", stage="live", summary="PDF bhej di gayi."),
    ],
)


async def test_every_number_counts_requests_by_whose_turn_it_is(
    app, provider, business_db, monkeypatch
):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    _mock_issues(monkeypatch, THREE)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["headline"] == "Kitne staff ERP app use karenge?"
    assert listed["issues_total"] == 3 and len(listed["issues"]) == 3
    assert listed["counts"] == {
        "waiting_on_you": 1,
        "waiting_on_other": 0,
        "waiting_on_us": 1,
        "done": 1,
        "paused": 0,
    }
    erp, site, pdf = listed["issues"]
    assert erp["ball_with"] == "client" and erp["next_step_owner"] == "you"
    assert erp["open_question"] and erp["original_words"] == "mujhe erp chahiye mobile pe"
    assert site["ball_with"] == "team" and site["open_question"] == ""
    assert site["next_update_by"] and site["status"] == "with_team"  # board still works
    assert pdf["status"] == "resolved" and pdf["journey_steps"] == 7
    assert erp["journey_steps"] == 2 and site["journey_steps"] == 3
    await business.aclose()
    await customer.aclose()


async def test_waiting_on_someone_else_pauses_reminders_and_can_be_undone(
    app, provider, business_db, monkeypatch
):
    from app.modules.pi.followups import _waiting_until

    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    _mock_issues(monkeypatch, THREE)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    headers = {"x-csrf-token": customer.cookies[CSRF_COOKIE]}
    path = f"{PORTAL}/conversations/{conversation_id}/waiting"
    paused = await customer.post(path, json={"days": 5}, headers=headers)
    assert paused.status_code == 200 and paused.json()["waiting_on_other_until"]
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["counts"]["waiting_on_other"] == 1 and listed["counts"]["waiting_on_you"] == 0
    conversation = await business_db.get(PiConversation, conversation_id)
    await business_db.refresh(conversation)
    assert _waiting_until(conversation.service_brief) is not None  # reminders skip it
    assert "customer_issues" in conversation.service_brief  # other brief keys kept
    resumed = await customer.post(path, json={"days": 0}, headers=headers)
    assert resumed.status_code == 200, resumed.text
    listed = (await customer.get(f"{PORTAL}/conversations")).json()[0]
    assert listed["counts"]["waiting_on_you"] == 1, listed
    await business.aclose()
    await customer.aclose()


async def test_language_choice_rewrites_the_request_list(app, provider, business_db, monkeypatch):
    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    seen = _mock_issues(monkeypatch, THREE)
    path = f"{PORTAL}/conversations/{conversation_id}/issues"
    await customer.get(path)
    assert seen[-1]["language"] == "auto"
    headers = {"x-csrf-token": customer.cookies[CSRF_COOKIE]}
    saved = await customer.put(f"{PORTAL}/prefs", json={"language": "en"}, headers=headers)
    assert saved.status_code == 200 and saved.json()["language"] == "en"
    await customer.get(path)
    assert len(seen) == 2 and seen[-1]["language"] == "en"
    await customer.get(path)
    assert len(seen) == 2  # cached again for the chosen language
    bad = await customer.put(f"{PORTAL}/prefs", json={"language": "xx"}, headers=headers)
    assert bad.status_code == 422
    first = (await customer.post(f"{PORTAL}/seen", headers=headers)).json()
    second = (await customer.post(f"{PORTAL}/seen", headers=headers)).json()
    assert first["previous"] is None and second["previous"] is not None
    await business.aclose()
    await customer.aclose()


async def test_a_shared_link_shows_requests_only_and_can_be_turned_off(
    app, provider, business_db, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.modules.pi_customer.models import CustomerShareLink

    business = await _business_with_chat(app, provider, business_db, monkeypatch)
    customer = await _sign_in(app, provider)
    conversation_id = (await customer.get(f"{PORTAL}/conversations")).json()[0]["id"]
    _mock_issues(monkeypatch, THREE)
    await customer.get(f"{PORTAL}/conversations/{conversation_id}/issues")
    headers = {"x-csrf-token": customer.cookies[CSRF_COOKIE]}
    assert (await customer.post(f"{PORTAL}/share", json={})).status_code == 403  # CSRF
    made = await customer.post(f"{PORTAL}/share", json={}, headers=headers)
    assert made.status_code == 201
    token, link_id = made.json()["token"], made.json()["id"]
    boss = pi_client(app)  # not signed in
    shown = await boss.get(f"{PORTAL}/shared/{token}")
    assert shown.status_code == 200
    flat = json.dumps(shown.json())
    assert "Mobile ERP app" in flat and "Kitne staff" in flat
    # No chat, no customer number, no customer's own words.
    assert "Website chahiye" not in flat and CUSTOMER not in flat
    assert "original_words" not in flat and "mujhe erp" not in flat
    assert [s["id"] for s in (await customer.get(f"{PORTAL}/share")).json()] == [link_id]
    revoked = await customer.delete(f"{PORTAL}/share/{link_id}", headers=headers)
    assert revoked.status_code == 204
    assert (await boss.get(f"{PORTAL}/shared/{token}")).status_code == 404
    # An expired link stops working too.
    again = (await customer.post(f"{PORTAL}/share", json={}, headers=headers)).json()
    link = await business_db.get(CustomerShareLink, again["id"])
    link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await business_db.commit()
    assert (await boss.get(f"{PORTAL}/shared/{again['token']}")).status_code == 404
    assert (await boss.get(f"{PORTAL}/shared/not-a-real-token")).status_code == 404
    for client in (business, customer, boss):
        await client.aclose()
