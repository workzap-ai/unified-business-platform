"""A WhatsApp/Kapso refusal (4xx) is reported as WHATSAPP_REJECTED with Meta's reason;
only timeouts and server errors stay DELIVERY_UNCONFIRMED (it may have been sent)."""

import httpx
import pytest
from pydantic import SecretStr

from app.modules.pi.whatsapp import WhatsApp
from app.shared.errors import BusinessRuleViolation


def _client(settings, response: httpx.Response) -> WhatsApp:
    settings.kapso_api_key = SecretStr("kapso-test-key")
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
    return WhatsApp(settings, http, provider="kapso")


async def test_meta_refusal_is_rejected_with_its_code(settings):
    meta_error = {"error": {"message": "Business eligibility payment issue", "code": 131042}}
    whatsapp = _client(settings, httpx.Response(400, json=meta_error))
    with pytest.raises(BusinessRuleViolation) as caught:
        await whatsapp.send("1258916823982550", "923001112233", "Salam", "")
    assert caught.value.code == "WHATSAPP_REJECTED"
    assert "131042" in caught.value.message


async def test_kapso_window_refusal_is_rejected(settings):
    body = {"error": "Cannot send non-template messages outside the 24-hour window."}
    whatsapp = _client(settings, httpx.Response(422, json=body))
    with pytest.raises(BusinessRuleViolation) as caught:
        await whatsapp.send("1258916823982550", "923001112233", "Salam", "")
    assert caught.value.code == "WHATSAPP_REJECTED"
    assert "24_hour_window" in caught.value.message


async def test_server_errors_stay_unconfirmed(settings):
    whatsapp = _client(settings, httpx.Response(502, text="bad gateway"))
    with pytest.raises(BusinessRuleViolation) as caught:
        await whatsapp.send("1258916823982550", "923001112233", "Salam", "")
    assert caught.value.code == "DELIVERY_UNCONFIRMED"


async def test_success_returns_the_message_id(settings):
    ok = httpx.Response(200, json={"messages": [{"id": "wamid.ok1"}]})
    assert await _client(settings, ok).send("1258916823982550", "9230011", "Salam", "") == (
        "wamid.ok1"
    )
