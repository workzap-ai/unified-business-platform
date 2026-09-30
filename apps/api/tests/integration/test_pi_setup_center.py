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
    assert [f["flow_id"] for f in forms] == ["998877665544", None, None]
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
