"""Real business/API workflows and PostgreSQL; only provider networks are mocked."""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from test_integrations_api import connect_stripe
from test_integrations_api import env as env
from test_service_lifecycle import create, register

from app.integrations import jobs, workflows
from app.integrations.business import minor_units
from app.integrations.workflow_models import IntegrationOperation
from app.shared.errors import BusinessRuleViolation

pytestmark = pytest.mark.integration


async def connect(env, provider):
    config, credentials = {
        "resend": (
            {"from_address": "sender@example.com"},
            {"api_key": "re_test_workflow_secret_123456"},
        ),
        "generic_webhook": (
            {"url": "https://hooks.example.com/workflow"},
            {"signing_secret": "workflow-signing-secret-123456"},
        ),
        "slack": (
            {},
            {
                "webhook_url": "https://hooks.slack.com/services/T12345678/B12345678/workflowsecret12345"
            },
        ),
        "s3": (
            {
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "workflow-files",
                "region": "us-east-1",
                "addressing": "path",
            },
            {
                "access_key_id": "AKIATESTWORKFLOW12",
                "secret_access_key": "test-storage-secret-1234567890",
            },
        ),
    }[provider]
    return await create(
        env["api"],
        "integrations/connections",
        {
            "integration_key": provider,
            "display_name": "Workflow test",
            "mode": "production",
            "config": config,
            "credentials": credentials,
        },
    )


def success(request):
    if request.url.host == "hooks.slack.com":
        return httpx.Response(200, text="ok")
    return httpx.Response(200, json={"data": [], "id": "email_workflow_1"})


async def operations(env, connection):
    return list(
        await env["db"].scalars(
            select(IntegrationOperation).where(
                IntegrationOperation.connection_id == UUID(connection["id"])
            )
        )
    )


@pytest.mark.parametrize("provider", ["resend", "slack", "generic_webhook"])
async def test_real_customer_event_routes_to_provider_once(env, provider):
    env["provider"].handler = success
    connection = await connect(env, provider)
    api = env["api"]
    await create(api, "customers", {"name": "Before workflow"})
    response = await api.put(
        f"/api/v1/integrations/connections/{connection['id']}/workflow",
        json={
            "enabled": True,
            "event_types": ["customer.created"],
            "recipients": ["team@example.com"] if provider == "resend" else [],
        },
    )
    assert response.status_code == 200, response.text
    await create(api, "customers", {"name": "After workflow"})
    await jobs.integrations_sweep(env["ctx"])
    rows = await operations(env, connection)
    assert len(rows) == 1  # Earlier events are not backfilled.
    env["provider"].requests.clear()
    assert await jobs.deliver_integration_operation(env["ctx"], str(rows[0].id)) == "succeeded"
    assert await jobs.deliver_integration_operation(env["ctx"], str(rows[0].id)) == "skipped"
    await jobs.integrations_sweep(env["ctx"])
    assert len(await operations(env, connection)) == 1
    assert len(env["provider"].requests) == 1
    request = env["provider"].requests[0]
    if provider == "resend":
        assert json.loads(request.content)["to"] == ["team@example.com"]
        assert request.headers["Idempotency-Key"] == str(rows[0].id)
    if provider == "generic_webhook":
        assert "x-platform-signature" in request.headers


async def invoice(env):
    customer = await create(
        env["api"], "customers", {"name": "Paying customer", "email": "customer@example.com"}
    )
    row = await create(
        env["api"],
        "billing/invoices",
        {
            "customer_id": customer["id"],
            "lines": [{"description": "Service", "quantity": "1", "unit_price": "10.00"}],
        },
    )
    return await create(env["api"], f"billing/invoices/{row['id']}/actions", {"action": "issue"})


async def test_invoice_email_is_durable_idempotent_and_disabled_connection_stops_send(env):
    env["provider"].handler = success
    connection = await connect(env, "resend")
    bill = await invoice(env)
    request_id = str(uuid4())
    url = f"/api/v1/billing/invoices/{bill['id']}/email"
    one = await env["api"].post(url, json={"request_id": request_id})
    two = await env["api"].post(url, json={"request_id": request_id})
    assert one.status_code == 202, one.text
    assert one.json()["id"] == two.json()["id"]
    assert await jobs.deliver_integration_operation(env["ctx"], one.json()["id"]) == "succeeded"
    sent = [r for r in env["provider"].requests if r.url.path == "/emails"]
    assert len(sent) == 1 and json.loads(sent[0].content)["to"] == ["customer@example.com"]
    new = await env["api"].post(url, json={"request_id": str(uuid4())})
    await env["api"].post(f"/api/v1/integrations/connections/{connection['id']}/disable")
    assert await jobs.deliver_integration_operation(env["ctx"], new.json()["id"]) == "cancelled"


async def test_uncertain_delivery_needs_explicit_review(env):
    env["provider"].handler = success
    connection = await connect(env, "resend")
    bill = await invoice(env)
    response = await env["api"].post(
        f"/api/v1/billing/invoices/{bill['id']}/email", json={"request_id": str(uuid4())}
    )
    op = (await operations(env, connection))[0]
    op.status = "running"
    op.updated_at = datetime.now(UTC) - timedelta(minutes=20)
    await env["db"].flush()
    assert not await workflows.due(env["db"])
    assert op.status == "needs_review"
    retry = f"/api/v1/integrations/operations/{response.json()['id']}/retry"
    assert (await env["api"].post(retry, json={})).status_code == 422
    assert (
        await env["api"].post(retry, json={"acknowledge_duplicate_risk": True})
    ).status_code == 200


@pytest.mark.parametrize(
    "mismatch", [None, "amount_total", "currency", "client_reference_id", "livemode"]
)
async def test_invoice_checkout_and_signed_webhook_record_one_verified_payment(env, mismatch):
    connection = await connect_stripe(env)
    bill = await invoice(env)
    session_id = "cs_test_workflow123"
    saved = {}

    def provider(request):
        if request.method == "POST":
            saved.update({k: v[0] for k, v in parse_qs(request.content.decode()).items()})
            return httpx.Response(
                200,
                json={"id": session_id, "url": "https://checkout.stripe.com/c/pay/test_workflow"},
            )
        result = {
            "id": session_id,
            "payment_status": "paid",
            "livemode": False,
            "amount_total": int(saved["line_items[0][price_data][unit_amount]"]),
            "currency": saved["line_items[0][price_data][currency]"],
            "client_reference_id": saved["client_reference_id"],
        }
        if mismatch:
            result[mismatch] = {
                "amount_total": 1,
                "currency": "eur",
                "client_reference_id": str(uuid4()),
                "livemode": True,
            }[mismatch]
        return httpx.Response(200, json=result)

    env["provider"].handler = provider
    url = f"/api/v1/billing/invoices/{bill['id']}/checkout"
    first = await env["api"].post(url)
    assert first.status_code == 200, first.text
    second = await env["api"].post(url)
    assert first.json()["id"] == second.json()["id"]
    # Provider signature binds the callback, server retrieval verifies amount/currency/scope.
    from app.integrations.crypto import CredentialManager
    from app.modules.integrations.models import IntegrationConnection

    c = await env["db"].get(IntegrationConnection, UUID(connection["id"]))
    token = CredentialManager(env["settings"]).decrypt_json(c.credentials_encrypted)[
        "__endpoint_token"
    ]
    for index in range(2):
        raw = json.dumps(
            {
                "id": f"evt_workflow{index}",
                "object": "event",
                "type": "checkout.session.completed",
                "livemode": False,
                "data": {"object": {"id": session_id, "object": "checkout.session"}},
            }
        ).encode()
        stamp = str(int(time.time()))
        signature = hmac.new(
            b"whsec_integration_test_secret", stamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        response = await env["api"].post(
            f"/api/v1/webhooks/stripe/{token}",
            content=raw,
            headers={"Stripe-Signature": f"t={stamp},v1={signature}"},
        )
        assert response.status_code == 200, response.text
        job = [j for j in env["ctx"]["queue"].jobs if j[0] == "process_inbound_event"][-1]
        if mismatch:
            assert await jobs.process_inbound_event(env["ctx"], job[1][0]) == "failed"
            from app.modules.integrations.models import InboundEvent

            received = await env["db"].get(InboundEvent, UUID(job[1][0]))
            assert received.error_code == "PAYMENT_MISMATCH"
            unpaid = (await env["api"].get(f"/api/v1/billing/invoices/{bill['id']}")).json()
            assert unpaid["status"] == "issued" and not unpaid["payments"]
            return
        assert await jobs.process_inbound_event(env["ctx"], job[1][0]) == "processed"
    paid = (await env["api"].get(f"/api/v1/billing/invoices/{bill['id']}")).json()
    assert paid["status"] == "paid" and len(paid["payments"]) == 1


@pytest.mark.parametrize("provider", ["resend", "slack"])
@pytest.mark.parametrize("failure", ["timeout", "server_error"])
async def test_timeout_retries_only_idempotent_providers(env, provider, failure):
    env["provider"].handler = success
    connection = await connect(env, provider)
    await env["api"].put(
        f"/api/v1/integrations/connections/{connection['id']}/workflow",
        json={
            "enabled": True,
            "event_types": ["customer.created"],
            "recipients": ["team@example.com"] if provider == "resend" else [],
        },
    )
    await create(env["api"], "customers", {"name": "Recovery"})
    await jobs.integrations_sweep(env["ctx"])
    op = (await operations(env, connection))[0]

    def timeout(request):
        if failure == "server_error":
            return httpx.Response(503)
        raise httpx.ReadTimeout("test timeout")

    env["provider"].handler = timeout
    outcome = await jobs.deliver_integration_operation(env["ctx"], str(op.id))
    assert outcome == ("failed" if provider == "resend" else "needs_review")
    if provider == "resend":
        assert await jobs.deliver_integration_operation(env["ctx"], str(op.id)) == "not_due"
        op.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await env["db"].flush()
        env["provider"].handler = success
        assert await jobs.deliver_integration_operation(env["ctx"], str(op.id)) == "succeeded"
        sent = [r for r in env["provider"].requests if r.url.path == "/emails"]
        assert len(sent) == 2
        assert sent[0].headers["Idempotency-Key"] == sent[1].headers["Idempotency-Key"]


@pytest.mark.parametrize("queue_mode", ["inline", "arq"])
async def test_whatsapp_connection_routes_to_pi_rotates_token_and_stops_when_disabled(
    env, queue_mode
):
    from app.integrations.crypto import CredentialManager
    from app.integrations.whatsapp_bridge import token
    from app.modules.integrations.models import IntegrationConnection
    from app.modules.pi.models import WhatsAppConnection, WhatsAppWebhookEvent
    from app.modules.pi.runtime import system_scope

    env["provider"].handler = lambda request: httpx.Response(
        200, json={"display_phone_number": "+15551234567", "verified_name": "Workflow"}
    )
    connection = await create(
        env["api"],
        "integrations/connections",
        {
            "integration_key": "whatsapp_meta",
            "display_name": "PI line",
            "mode": "production",
            "config": {"phone_number_id": "123456789"},
            "credentials": {
                "access_token": "workflow-test-token",
                "app_secret": "workflow-app-secret",
                "verify_token": "workflow-verify-token",
            },
        },
    )
    activate = f"/api/v1/integrations/connections/{connection['id']}/activate-pi"
    assert (await env["api"].post(activate)).status_code == 403
    await create(env["api"], "products/pi/install", {})
    assert (
        await env["api"].put("/api/v1/products/pi/environment", json={"enabled": True})
    ).status_code == 200
    first = await env["api"].post(activate)
    assert first.status_code == 200, first.text
    assert (await env["api"].post(activate)).json() == first.json()
    row = await env["db"].get(WhatsAppConnection, UUID(first.json()["connection_id"]))
    linked = await env["db"].get(IntegrationConnection, UUID(connection["id"]))
    secrets = CredentialManager(env["settings"]).decrypt_json(linked.credentials_encrypted)
    raw = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "123456789"},
                                "messages": [
                                    {
                                        "id": "wamid.workflow1",
                                        "from": "15550000001",
                                        "type": "text",
                                        "text": {"body": "Hello from integration"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    ).encode()
    signature = "sha256=" + hmac.new(b"workflow-app-secret", raw, hashlib.sha256).hexdigest()
    for _ in range(2):
        result = await env["api"].post(
            f"/api/v1/webhooks/whatsapp_meta/{secrets['__endpoint_token']}",
            content=raw,
            headers={"X-Hub-Signature-256": signature},
        )
        assert result.status_code == 200, result.text
    job = [j for j in env["ctx"]["queue"].jobs if j[0] == "process_inbound_event"][0]
    context = dict(env["ctx"])
    if queue_mode == "arq":
        from types import SimpleNamespace

        async def enqueue_job(name, *args, _job_id=None):
            return await env["ctx"]["queue"].enqueue(name, *args, job_id=_job_id)

        context.pop("queue")
        context["redis"] = SimpleNamespace(enqueue_job=enqueue_job)
    assert await jobs.process_inbound_event(context, job[1][0]) == "processed"
    assert await jobs.process_inbound_event(context, job[1][0]) == "skipped"
    pi_jobs = [j for j in env["ctx"]["queue"].jobs if j[0] == "process_pi_event"]
    assert len(pi_jobs) == 1
    receipt = await env["db"].get(WhatsAppWebhookEvent, UUID(pi_jobs[0][1][0]))
    assert receipt.payload["body"] == "Hello from integration"
    assert receipt.connection_id == row.id and receipt.tenant_id == linked.tenant_id
    assert row.verified_at is not None
    assert await token(env["db"], env["settings"], row) == "workflow-test-token"
    secrets["access_token"] = "rotated-workflow-token"
    linked.credentials_encrypted = CredentialManager(env["settings"]).encrypt_json(secrets)
    await env["db"].flush()
    assert await token(env["db"], env["settings"], row) == "rotated-workflow-token"
    assert await system_scope(env["db"], row) is not None
    await env["api"].post(f"/api/v1/integrations/connections/{connection['id']}/disable")
    assert await system_scope(env["db"], row) is None
    with pytest.raises(BusinessRuleViolation):
        await token(env["db"], env["settings"], row)


async def test_s3_attachment_upload_download_delete_and_scope(env):
    objects = {}

    def provider(request):
        if request.method == "PUT":
            objects[request.url.path] = request.content
        if request.method == "DELETE":
            objects.pop(request.url.path, None)
        return httpx.Response(200, content=objects.get(request.url.path, b""))

    env["provider"].handler = provider
    connection = await connect(env, "s3")
    customer = await create(env["api"], "customers", {"name": "Files"})
    url = f"/api/v1/files/records/customer/{customer['id']}"
    request_id = str(uuid4())
    response = await env["api"].post(
        url,
        files={"file": ("spec.html", b"<script>test</script>", "text/html")},
        data={"request_id": request_id},
    )
    assert response.status_code == 201, response.text
    op = response.json()
    assert str(env["identity"]["tenant"]["id"]) in op["output"]["key"]
    download = await env["api"].get(f"/api/v1/files/{op['id']}/download")
    assert download.content == b"<script>test</script>"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["content-type"] == "application/octet-stream"
    other = await env["api"].post(
        url,
        files={"file": ("different.txt", b"different", "text/plain")},
        data={"request_id": request_id},
    )
    assert other.status_code == 422
    assert (await env["api"].delete(f"/api/v1/files/{op['id']}")).status_code == 204
    assert not objects
    cancelled_retry = await env["api"].post(
        url,
        files={"file": ("spec.html", b"<script>test</script>", "text/html")},
        data={"request_id": request_id},
    )
    assert cancelled_retry.status_code == 422
    assert cancelled_retry.json()["error"]["code"] == "UPLOAD_CANCELLED"
    assert (await env["api"].get(f"/api/v1/files/{op['id']}/download")).status_code == 404
    await register(env["api"])
    assert (await env["api"].get(url)).status_code == 404
    assert (
        await env["api"].get(f"/api/v1/integrations/connections/{connection['id']}/operations")
    ).status_code == 404


async def test_public_api_key_consumes_scopes_and_revocation(env):
    api = env["api"]
    await create(api, "customers", {"name": "Key customer"})
    key = await create(
        api, "integrations/api-keys", {"name": "Customer reader", "scopes": ["customers.read"]}
    )
    result = await api.get(
        "/api/v1/external/customers", headers={"authorization": "Bearer " + key["secret"]}
    )
    assert result.status_code == 200 and result.json()["total"] == 1
    assert (
        await api.get(
            f"/api/v1/external/invoices/{uuid4()}",
            headers={"authorization": "Bearer " + key["secret"]},
        )
    ).status_code == 403
    await api.delete(f"/api/v1/integrations/api-keys/{key['id']}")
    assert (
        await api.get(
            "/api/v1/external/customers", headers={"authorization": "Bearer " + key["secret"]}
        )
    ).status_code == 401


def test_currency_minor_units_do_not_round_a_charge():
    assert minor_units(Decimal("10.50"), "USD") == 1050
    assert minor_units(Decimal("10"), "JPY") == 10
    with pytest.raises(BusinessRuleViolation):
        minor_units(Decimal("10.50"), "JPY")
    with pytest.raises(BusinessRuleViolation):
        minor_units(Decimal("10"), "BHD")
