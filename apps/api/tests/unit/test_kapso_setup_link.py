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


async def test_existing_customer_is_reused_not_duplicated(settings):
    settings.kapso_api_key = SecretStr("kapso-test-key")
    posts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "08a3456c-beb1-4fde-9728-d174635f73cc",
                            "external_customer_id": "t1:production",
                        }
                    ]
                },
            )
        posts.append(request.url.path)
        return httpx.Response(201, json={"data": {"id": "11111111-2222-3333-4444-555555555555"}})

    kapso = Kapso(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await kapso.create_customer("Workzap", "t1:production") == (
        "08a3456c-beb1-4fde-9728-d174635f73cc"
    )
    assert posts == []  # nothing new created
    assert await kapso.create_customer("New Co", "t2:production") == (
        "11111111-2222-3333-4444-555555555555"
    )
    assert posts == ["/platform/v1/customers"]


async def test_rejections_are_logged_as_identifiers(settings):
    import logging

    import pytest

    from app.modules.pi_saas.kapso import KapsoUnavailable

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    settings.kapso_api_key = SecretStr("kapso-test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "param is missing or the value is empty or invalid: setup_link"}
        )

    kapso = Kapso(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    # A handler on the logger itself: the app's logging setup may stop propagation.
    handler_ = Capture(level=logging.WARNING)
    logging.getLogger("platform").addHandler(handler_)
    try:
        with pytest.raises(KapsoUnavailable):
            await kapso.create_setup_link(
                "b10b3941-272e-422a-bd9f-8ff59690f7cd",
                success_url="https://a.example/ok",
                failure_url="https://a.example/fail",
            )
    finally:
        logging.getLogger("platform").removeHandler(handler_)
    [record] = [r for r in records if r.getMessage() == "kapso_request_failed"]
    assert record.status_code == 400
    assert record.operation == "/platform/v1/customers/{id}/setup_links"
    assert record.error_kind.startswith("param_is_missing_or_the_value_is_empty")
    assert "kapso-test-key" not in str(record.__dict__)
