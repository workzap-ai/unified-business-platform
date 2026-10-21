"""A pi business sets up its own email (white-label): saved encrypted, never shown back,
one connection at a time, and blank secret fields keep the saved one."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select
from test_pi_pipeline import pi_workspace

from app.modules.integrations.models import IntegrationConnection

pytestmark = pytest.mark.integration
EMAIL = "/api/v1/pi/connectors/email"


async def test_business_sets_up_its_own_email(api, business_db):
    pi = await pi_workspace(api, business_db, business_type="service_business")
    settings = api._transport.app.state.settings
    if settings.secrets_encryption_key is None:
        settings.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())

    status = (await api.get(EMAIL)).json()
    assert status["connection"] is None
    assert {p["key"] for p in status["providers"]} >= {"smtp", "resend", "sendgrid"}

    saved = await api.put(
        EMAIL,
        json={
            "provider": "resend",
            "values": {"api_key": "re_secret_value_123", "from_address": "hello@bakery.test"},
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["connection"]["provider"] == "resend"
    assert body["connection"]["from_address"] == "hello@bakery.test"
    assert "re_secret_value_123" not in saved.text  # secrets never come back
    assert "api_key" in body["connection"]["secrets_set"]

    # Changing only the sender keeps the saved key; one live connection at a time.
    again = await api.put(
        EMAIL, json={"provider": "resend", "values": {"from_address": "team@bakery.test"}}
    )
    assert again.status_code == 200, again.text
    assert again.json()["connection"]["from_address"] == "team@bakery.test"
    live = list(
        await business_db.scalars(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == pi.identity["tenant"]["id"],
                IntegrationConnection.integration_key == "resend",
                IntegrationConnection.status != "revoked",
            )
        )
    )
    assert len(live) == 1 and "api_key" in live[0].credential_hints

    removed = await api.delete(EMAIL)
    assert removed.status_code == 204
    assert (await api.get(EMAIL)).json()["connection"] is None
    await pi.close()
