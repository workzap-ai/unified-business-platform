"""A number whose display name Meta has not approved is LIMITED and rejects sends. The
health summary keeps Meta's plain-language note (URLs removed) so the app can show it."""

import httpx
from pydantic import SecretStr

from app.modules.pi_saas.kapso import Kapso

LIMITED = {
    "data": {
        "status": "degraded",
        "checks": {
            "messaging_health": {
                "status": "warning",
                "details": {
                    "can_send_message": "LIMITED",
                    "entities": [
                        {
                            "can_send_message": "LIMITED",
                            "additional_info": [
                                "Your display name has not been approved yet. "
                                "See https://example.com/help for more."
                            ],
                        }
                    ],
                },
            }
        },
    }
}


async def _health(settings, body):
    settings.kapso_api_key = SecretStr("kapso-test-key")
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    )
    return await Kapso(settings, http).health("1375940488941201")


async def test_limited_number_exposes_the_reason(settings):
    health = await _health(settings, LIMITED)
    assert health["messaging"]["can_send"] == "LIMITED"
    [note] = health["messaging"]["notes"]
    assert "display name has not been approved" in note
    assert "http" not in note


async def test_healthy_number_has_no_messaging_note(settings):
    health = await _health(settings, {"data": {"status": "healthy", "checks": {}}})
    assert "messaging" not in health
