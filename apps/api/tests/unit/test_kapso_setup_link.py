"""Kapso rejects a setup link whose fields aren't wrapped in "setup_link" (HTTP 400,
seen live on 1 Oct 2026). The client must always send the wrapper."""

import json

import httpx
from pydantic import SecretStr

from app.modules.pi_saas.kapso import Kapso


async def test_setup_link_body_is_wrapped(settings):
    settings.kapso_api_key = SecretStr("kapso-test-key")
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if not isinstance(body.get("setup_link"), dict):
            return httpx.Response(400, json={"error": "param is missing: setup_link"})
        return httpx.Response(
            201,
            json={"data": {"id": "link_1", "url": "https://app.kapso.ai/setup/abc"}},
        )

    kapso = Kapso(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    link = await kapso.create_setup_link(
        "b10b3941-272e-422a-bd9f-8ff59690f7cd",
        success_url="https://app.example.com/operator/numbers?added=1",
        failure_url="https://app.example.com/operator/numbers?failed=1",
        connection_types=("dedicated",),
        provision_country="US",
    )
    assert link.url == "https://app.kapso.ai/setup/abc"
    [body] = sent
    assert set(body) == {"setup_link"}
    fields = body["setup_link"]
    assert fields["allowed_connection_types"] == ["dedicated"]
    assert fields["provision_phone_number"] is True
    assert fields["phone_number_country_isos"] == ["US"]
    assert fields["meta_billing_mode"] == "partner_managed"
    assert fields["success_redirect_url"].endswith("added=1")
