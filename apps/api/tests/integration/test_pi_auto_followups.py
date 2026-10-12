"""pi sets up its own follow-up templates: it writes them, submits them to Meta (Utility,
no variables), saves them in the settings and switches reminders on. Running it again
reuses what already exists."""

import pytest
from pi_saas_support import FakeProvider, configure
from sqlalchemy import select
from test_pi_saas import _ready_business

from app.modules.pi.models import PiSettings, WhatsAppConnection

pytestmark = pytest.mark.integration
AUTO = "/api/v1/pi-app/pi/whatsapp/templates/follow-ups"


@pytest.fixture
def app(api):
    return api._transport.app  # type: ignore[attr-defined]


@pytest.fixture
def provider(app):
    fake = FakeProvider()
    fake.queue = configure(app, fake)  # type: ignore[attr-defined]
    app.state.settings.integrations_public_base_url = "https://api.example.test"
    return fake


async def test_pi_creates_and_saves_its_follow_up_templates(app, provider, business_db):
    client, _ = await _ready_business(app, provider, business_db, "Auto Co", "8383838383")
    made = await client.post(AUTO)
    assert made.status_code == 200, made.text
    statuses = made.json()["templates"]
    assert set(statuses) == {
        f"{lang}:{step}"
        for lang in ("en", "roman_ur")
        for step in ("reminder", "day3", "day7", "day14")
    }
    assert all(status == "PENDING" for status in statuses.values())
    created = {(t["name"], t["language"], t["category"]) for t in provider.templates}
    assert ("pi_reminder_en", "en_US", "UTILITY") in created
    assert ("pi_followup_day14_ru", "ur", "UTILITY") in created
    assert all("{{" not in str(t.get("components")) for t in provider.templates)

    number = await business_db.scalar(
        select(WhatsAppConnection).where(WhatsAppConnection.phone_number_id == "8383838383")
    )
    policy = await business_db.scalar(
        select(PiSettings).where(
            PiSettings.tenant_id == number.tenant_id,
            PiSettings.environment_id == number.environment_id,
        )
    )
    await business_db.refresh(policy)
    config = policy.whatsapp_config
    assert config["reminder_enabled"] is True
    assert config["reminder_templates"]["en"] == {"name": "pi_reminder_en", "language": "en_US"}
    assert config["ladder_templates"]["roman_ur"]["day7"]["name"] == "pi_followup_day7_ru"

    count = len(provider.templates)
    again = await client.post(AUTO)
    assert again.status_code == 200
    assert len(provider.templates) == count  # nothing created twice
    await client.aclose()
