"""Setup Center, WhatsApp templates and one-click forms, sandbox numbers, WhatsApp
usage for operators, and connector OAuth returning to the right app."""

from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from test_pi_saas import _ready_business
from test_service_lifecycle import register

from app.modules.pi_saas import connectors
from app.modules.pi_saas.models import PiOperatorMember, PiPoolNumber
from app.modules.pi_saas.whatsapp_tools import flow_json

pytestmark = pytest.mark.integration
PUBLIC = "https://api.example.test"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.settings.integrations_public_base_url = PUBLIC
    return fake


async def test_setup_center_shows_every_tool_and_tests_them(app, provider, business_db):
    client = pi_client(app)
    await pi_register(client, "Setup Co")
    status = (await client.get("/api/v1/pi-app/setup/status")).json()
    keys = [i["key"] for i in status["items"]]
    assert keys[:2] == ["whatsapp", "ai"] and {"email", "stripe", "google_calendar"} <= set(keys)
    whatsapp = status["items"][0]
    assert whatsapp["state"] == "not_connected" and whatsapp["href"] == "/settings/whatsapp"
    assert status["ready"] is False
    await client.aclose()

    connected, _ = await _ready_business(app, provider, business_db, "Ready Co", "8181818181")
    ready = (await connected.get("/api/v1/pi-app/setup/status")).json()
    assert ready["items"][0]["state"] == "connected"
    assert "via Kapso" in ready["items"][0]["detail"]
    tested = (await connected.post("/api/v1/pi-app/setup/test-all")).json()
    assert tested["results"][0]["key"] == "whatsapp" and tested["results"][0]["ok"] is True
    await connected.aclose()


async def test_platform_checklist_for_operators(api, app, provider, business_db):
    identity = await register(api)
    assert (await api.get("/api/v1/operator/pi/setup")).status_code == 403
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner"))
    await business_db.flush()
    checklist = (await api.get("/api/v1/operator/pi/setup")).json()
    checks = {c["key"]: c for c in checklist["checks"]}
    assert checks["kapso_api_key"]["ok"] and checks["public_api_url"]["ok"]
    app.state.settings.integrations_public_base_url = None
    checks = {c["key"]: c for c in (await api.get("/api/v1/operator/pi/setup")).json()["checks"]}
    assert (
        not checks["public_api_url"]["ok"]
        and "INTEGRATIONS_PUBLIC_BASE_URL" in checks["public_api_url"]["fix"]
    )


async def test_templates_and_one_click_forms(app, provider, business_db):
    client, _ = await _ready_business(app, provider, business_db, "Forms Co", "8282828282")
    provider.templates.append(
        {
            "name": "eid_offer",
            "language": "en",
            "status": "APPROVED",
            "category": "MARKETING",
            "components": [{"type": "BODY", "text": "Eid Mubarak!"}],
        }
    )
    provider.templates.append(
        {
            "name": "order_update",
            "language": "en",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Your order {{1}} is ready"}],
        }
    )
    listed = (await client.get("/api/v1/pi-app/pi/whatsapp/templates")).json()["templates"]
    sendable = {t["name"]: t["sendable"] for t in listed}
    assert sendable == {"eid_offer": True, "order_update": False}
    created = await client.post(
        "/api/v1/pi-app/pi/whatsapp/templates",
        json={"name": "welcome_note", "language": "en", "category": "UTILITY", "body": "Welcome!"},
    )
    assert created.status_code == 201 and created.json()["status"] == "PENDING"
    bad = await client.post(
        "/api/v1/pi-app/pi/whatsapp/templates",
        json={"name": "Bad Name", "language": "en", "category": "UTILITY", "body": "x"},
    )
    assert bad.status_code == 422

    made = await client.post("/api/v1/pi-app/pi/whatsapp/forms/lead/create")
    assert made.status_code == 200, made.text
    assert made.json()["flow_id"] == "998877665544"
    [flow] = provider.flows
    assert flow["phone_number_id"] == "8282828282" and flow["publish"] is True
    screen = flow["flow_json"]["screens"][0]
    footer = screen["layout"]["children"][0]["children"][-1]
    assert footer["on-click-action"]["name"] == "complete"
    assert footer["on-click-action"]["payload"]["name"] == "${form.name}"
    forms = (await client.get("/api/v1/pi-app/pi/whatsapp/forms")).json()["forms"]
    assert [f["flow_id"] for f in forms] == ["998877665544", None, None, None]
    await client.aclose()


async def test_templates_page_creates_edits_and_sends_a_first_message(app, provider, business_db):
    client, _ = await _ready_business(app, provider, business_db, "Page Co", "8383838383")
    base = "/api/v1/pi-app/pi/whatsapp/templates"
    provider.templates.append(
        {
            "id": "555001",
            "name": "nori_welcome_en",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [{"type": "BODY", "text": "Hello {{1}}, welcome to nori."}],
        }
    )
    provider.templates.append(
        {
            "id": "555002",
            "name": "with_button",
            "language": "en_US",
            "status": "APPROVED",
            "category": "UTILITY",
            "components": [
                {"type": "BODY", "text": "Hi {{1}}"},
                {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Yes"}]},
            ],
        }
    )
    listed = {t["name"]: t for t in (await client.get(base)).json()["templates"]}
    assert listed["nori_welcome_en"]["variables"] == 1 and listed["nori_welcome_en"]["fillable"]
    assert listed["nori_welcome_en"]["id"] == "555001"
    assert not listed["with_button"]["fillable"]  # a button template is not one pi can fill

    # create with a variable needs an example for it
    body = {"name": "trial_note", "language": "en_US", "category": "UTILITY", "body": "Hi {{1}}"}
    assert (await client.post(base, json=body)).status_code == 422
    made = await client.post(base, json={**body, "examples": ["Ayesha"]})
    assert made.status_code == 201, made.text

    # edit goes to Meta and the template is reviewed again
    edited = await client.put(f"{base}/555001", json={"body": "Hi {{1}}!", "examples": ["Sam"]})
    assert edited.status_code == 200, edited.text
    assert provider.edited[0]["components"][0]["text"] == "Hi {{1}}!"
    assert (await client.put(f"{base}/999", json={"body": "x"})).status_code == 404

    send = {"phone": "+92 300 5551234", "name": "nori_welcome_en", "language": "en_US"}
    approved = {**send, "values": ["Ayesha"]}
    # not approved any more after the edit: pending templates cannot be sent
    refused = await client.post(f"{base}/send", json={**approved, "consent": True})
    assert refused.status_code == 422 and not provider.sent_messages
    provider.templates[0]["status"] = "APPROVED"
    assert (await client.post(f"{base}/send", json=approved)).status_code == 422  # no consent
    assert (
        await client.post(f"{base}/send", json={**send, "values": [], "consent": True})
    ).status_code == 422  # wrong number of values
    sent = await client.post(f"{base}/send", json={**approved, "consent": True})
    assert sent.status_code == 200, sent.text
    [message] = provider.sent_messages
    assert message["to"] == "923005551234" and message["type"] == "template"
    assert message["template"]["components"][0]["parameters"][0]["text"] == "Ayesha"
    await client.aclose()


def test_flow_json_shapes():
    for purpose in ("lead", "booking", "feedback"):
        data = flow_json(purpose)
        screen = data["screens"][0]
        assert screen["terminal"] and screen["id"] == "DETAILS"
        fields = [
            c for c in screen["layout"]["children"][0]["children"] if c["type"] == "TextInput"
        ]
        payload = screen["layout"]["children"][0]["children"][-1]["on-click-action"]["payload"]
        assert set(payload) == {f["name"] for f in fields}


async def test_sandbox_numbers_only_by_operator_offer_and_usage(api, app, provider, business_db):
    client = pi_client(app)
    view = await pi_register(client, "Tester Co")
    identity = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner"))
    await business_db.flush()
    pool = (await api.get("/api/v1/operator/pi/numbers")).json()["pool_customer_id"]
    provider.add_number(pool, "7000000001", "+1 415 555 0177", kind="sandbox")
    inventory = (await api.get("/api/v1/operator/pi/numbers")).json()
    [sandbox] = inventory["pool"]
    assert "sandbox" in sandbox["warnings"]
    assert (await client.get("/api/v1/pi-app/whatsapp/numbers")).json() == []
    offered = await api.post(
        f"/api/v1/operator/pi/numbers/{sandbox['id']}/offer",
        json={"tenant_id": view["business"]["id"]},
    )
    assert offered.status_code == 200, offered.text
    [mine] = (await client.get("/api/v1/pi-app/whatsapp/numbers")).json()
    assert mine["offered_to_you"] is True
    took = await client.post(f"/api/v1/pi-app/whatsapp/numbers/{mine['id']}/choose", json={})
    assert took.status_code == 200 and took.json()["status"] == "connected"
    row = await business_db.get(PiPoolNumber, UUID(mine["id"]))
    assert row.status == "assigned"
    usage = (await api.get("/api/v1/operator/pi/whatsapp-usage")).json()
    assert usage["billing_mode"] == "partner_managed" and "totals" in usage
    await client.aclose()


def test_connector_oauth_returns_to_the_app_it_started_from(app):
    settings = app.state.settings
    web = connectors.callback_uri(settings, "google_calendar", "web")
    assert web.endswith("/api/v1/pi/connectors/google_calendar/callback")
    pi = connectors.callback_uri(settings, "google_calendar", "pi")
    assert pi.endswith("/api/v1/pi-app/pi/connectors/google_calendar/callback")
