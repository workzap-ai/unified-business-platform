"""A business edits its own public WhatsApp profile (about, description, address, email,
category, websites) from its own screen; the change goes to Meta through Kapso."""

import pytest
from pi_saas_support import FakeProvider, configure
from test_pi_saas import _ready_business

pytestmark = pytest.mark.integration
PROFILE = "/api/v1/pi-app/pi/whatsapp/profile"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.settings.integrations_public_base_url = "https://api.example.test"
    return fake


async def test_a_business_reads_and_changes_its_whatsapp_profile(app, provider, business_db):
    client, _ = await _ready_business(app, provider, business_db, "Profile Co", "8484848484")
    current = (await client.get(PROFILE)).json()
    assert current["connected"] is True and current["can_edit"] is True
    assert current["profile"]["about"] == "Hey there"
    assert "HEALTH" in current["verticals"]

    saved = await client.put(
        PROFILE,
        json={
            "about": "Dental care in Lahore",
            "description": "Family dentistry, braces and whitening.",
            "address": "Gulberg III, Lahore",
            "email": "hello@clinic.example",
            "vertical": "HEALTH",
            "websites": ["https://clinic.example"],
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()["profile"]
    assert body["about"] == "Dental care in Lahore" and body["vertical"] == "HEALTH"
    assert body["websites"] == ["https://clinic.example"]
    sent = provider.profiles["8484848484"]
    assert sent["address"] == "Gulberg III, Lahore" and sent["email"] == "hello@clinic.example"
    await client.aclose()


@pytest.mark.parametrize(
    "bad",
    [
        {"about": ""},
        {"about": "x" * 140},
        {"about": "ok", "email": "not-an-email"},
        {"about": "ok", "websites": ["clinic.example"]},
        {
            "about": "ok",
            "websites": ["https://a.example", "https://b.example", "https://c.example"],
        },
        {"about": "ok", "vertical": "NOT_A_CATEGORY"},
        {"about": "ok", "description": "x" * 513},
        {"about": "ok", "unknown_field": 1},
    ],
)
async def test_values_meta_would_refuse_are_refused_here(app, provider, business_db, bad):
    client, _ = await _ready_business(app, provider, business_db, "Strict Co", "8585858585")
    refused = await client.put(PROFILE, json=bad)
    assert refused.status_code == 422, refused.text
    assert "8585858585" not in provider.profiles  # nothing was sent to Meta
    await client.aclose()


async def test_no_number_means_no_profile(app, provider, business_db):
    from pi_saas_support import pi_client, pi_register

    client = pi_client(app)
    await pi_register(client, "No Number Co")
    shown = (await client.get(PROFILE)).json()
    assert shown == {"connected": False, "number": None, "profile": None}
    await client.aclose()
