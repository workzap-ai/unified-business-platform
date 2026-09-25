"""Integration platform against real PostgreSQL: contract endpoints, isolation, RBAC,
secrets, inbound webhooks, outbox deliveries, OAuth, sync and API keys.

Provider HTTP is served by httpx.MockTransport; DNS by a fake public resolver. Redis is
unavailable locally, so rate limiting runs in its documented conservative fallback.
"""

import hashlib
import hmac
import importlib.util
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from test_service_lifecycle import create, register

from app.integrations import jobs as integration_jobs
from app.integrations import oauth, outbox, webhooks
from app.integrations.catalog import REGISTRY
from app.integrations.http import OutboundClient
from app.integrations.outbox import EntityRef, emit
from app.integrations.registry import (
    ConfigField,
    HealthResult,
    IntegrationDefinition,
    IntegrationProvider,
    OAuthSpec,
)
from app.integrations.signing import verify_signature_header
from app.modules.access.models import Role, RolePermission
from app.modules.audit.models import AuditEvent
from app.modules.integrations.api_keys import authenticate, key_hash
from app.modules.integrations.models import (
    ApiKey,
    Delivery,
    ExternalReference,
    InboundEvent,
    IntegrationConnection,
    OAuthState,
)
from app.shared.errors import Unauthenticated
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration

MIGRATION_0004 = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0004_integration_platform.py"
)
GW_SECRET = "gw-signing-secret-0123456789"
STRIPE_KEY = "sk_test_51Hsupersecretvalue"
WHSEC = "whsec_integration_test_secret"


async def public(host, port):
    return ["93.184.216.34"]


class CaptureQueue:
    def __init__(self):
        self.jobs = []

    async def enqueue(self, name, *args, job_id=None):
        self.jobs.append((name, args, job_id))
        return True

    async def close(self):
        pass


class Provider:
    """Programmable provider endpoint shared by the app and job contexts."""

    def __init__(self):
        self.handler = lambda request: httpx.Response(200, json={})
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        return self.handler(request)


@pytest.fixture
async def env(api, business_db):
    identity = await register(api)
    app = api._transport.app
    s = app.state.settings
    s.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())
    s.integrations_public_base_url = "https://api.example.test"
    s.oauth_redirect_base_url = "https://app.example.test"
    # No Redis locally: raise the conservative in-process fallback so tests are not throttled.
    s.integration_rate_limit_fallback_per_minute = 100000
    provider = Provider()
    http = httpx.AsyncClient(transport=httpx.MockTransport(provider))
    app.state.http = http
    app.state.integration_resolver = public
    app.state.queue = CaptureQueue()

    @asynccontextmanager
    async def sessions():
        yield business_db

    ctx = {
        "sessions": sessions,
        "settings": s,
        "http": http,
        "integration_resolver": public,
        "queue": app.state.queue,
    }
    yield {
        "api": api,
        "app": app,
        "db": business_db,
        "identity": identity,
        "provider": provider,
        "ctx": ctx,
        "settings": s,
    }
    await http.aclose()


def scope_of(env_) -> WorkspaceScope:
    ident = env_["identity"]
    return WorkspaceScope.system(
        UUID(ident["tenant"]["id"]), UUID(ident["environment"]["id"]), frozenset(), "test"
    )


async def connect_generic(api, name="Zapier hook"):
    response = await api.post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "generic_webhook",
            "display_name": name,
            "mode": "production",
            "config": {"url": "https://hooks.example.com/abc"},
            "credentials": {"signing_secret": GW_SECRET},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def stripe_ok(request):
    if request.url.path == "/v1/balance":
        return httpx.Response(200, json={"object": "balance", "livemode": False})
    return httpx.Response(404, json={})


async def connect_stripe(env_):
    env_["provider"].handler = stripe_ok
    response = await env_["api"].post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "stripe",
            "display_name": "Stripe",
            "mode": "sandbox",
            "credentials": {"secret_key": STRIPE_KEY, "webhook_secret": WHSEC},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- directory + connection lifecycle ------------------------------------------------------


async def test_definitions_directory(env):
    items = (await env["api"].get("/api/v1/integrations/definitions")).json()
    by_key = {d["key"]: d for d in items}
    assert by_key["generic_webhook"]["availability"] == "available"
    assert by_key["google_calendar"]["availability"] == "planned"
    assert by_key["stripe"]["sync_support"] == ["pull"]
    assert by_key["slack"]["sync_support"] == ["none"]
    secret_field = next(
        f for f in by_key["generic_webhook"]["config_schema"] if f["key"] == "signing_secret"
    )
    assert secret_field["secret"] is True and secret_field["type"] == "password"
    types = (await env["api"].get("/api/v1/integrations/event-types")).json()
    assert {"customer.created", "order.confirmed", "invoice.paid", "handoff.created"} <= {
        t["key"] for t in types
    }


async def test_connection_lifecycle_never_returns_credentials(env):
    api = env["api"]
    created = await connect_generic(api)
    assert created["status"] == "connected" and created["health"] == "healthy"
    assert env["provider"].requests == []  # the test validated the URL without sending
    cid = created["id"]
    detail = (await api.get(f"/api/v1/integrations/connections/{cid}")).json()
    assert detail["credentials"] == [{"key": "signing_secret", "set": True, "hint": "…6789"}]
    assert detail["config"] == {"url": "https://hooks.example.com/abc"}
    assert detail["recent_activity"][0]["kind"] == "test"
    assert (
        await api.patch(f"/api/v1/integrations/connections/{cid}", json={"display_name": "Renamed"})
    ).json()["display_name"] == "Renamed"
    result = (await api.post(f"/api/v1/integrations/connections/{cid}/test")).json()
    assert result["ok"] and result["status"] == "connected"
    assert (await api.post(f"/api/v1/integrations/connections/{cid}/disable")).json()[
        "status"
    ] == "disabled"
    blocked = await api.post(f"/api/v1/integrations/connections/{cid}/test")
    assert blocked.status_code == 409
    assert (await api.post(f"/api/v1/integrations/connections/{cid}/enable")).json()[
        "status"
    ] == "connected"
    new_secret = "rotated-signing-secret-ABCDEFGH"
    rotated = await api.put(
        f"/api/v1/integrations/connections/{cid}/credentials",
        json={"credentials": {"signing_secret": new_secret}},
    )
    assert rotated.status_code == 200 and rotated.json()["credentials"][0]["hint"] == "…EFGH"
    listing = (await api.get("/api/v1/integrations/connections")).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == cid
    assert (await api.delete(f"/api/v1/integrations/connections/{cid}")).status_code == 204
    gone = (await api.get(f"/api/v1/integrations/connections/{cid}")).json()
    assert gone["status"] == "revoked" and gone["credentials"][0]["set"] is False
    row = await env["db"].scalar(
        select(IntegrationConnection).where(IntegrationConnection.id == UUID(cid))
    )
    assert row.credentials_encrypted is None
    # Nothing we returned or audited contains a secret value.
    everything = json.dumps([created, detail, result, rotated.json(), listing, gone])
    audits = (
        await env["db"].scalars(select(AuditEvent).where(AuditEvent.entity_id == UUID(cid)))
    ).all()
    actions = {a.action for a in audits}
    assert {
        "integration.connection.created",
        "integration.connection.tested",
        "integration.credentials.rotated",
        "integration.connection.disconnected",
    } <= actions
    everything += json.dumps([a.details for a in audits])
    assert GW_SECRET not in everything and new_secret not in everything


async def test_connection_validation(env):
    api = env["api"]
    bad = await api.post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "generic_webhook",
            "display_name": "x",
            "config": {"url": "https://hooks.example.com/a", "signing_secret": GW_SECRET},
        },
    )
    assert bad.status_code == 422 and GW_SECRET not in bad.text  # secrets never as config
    planned = await api.post(
        "/api/v1/integrations/connections",
        json={"integration_key": "quickbooks", "display_name": "QB"},
    )
    assert planned.status_code == 422 and planned.json()["error"]["code"] == "NOT_CONNECTABLE"
    private = await api.post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "generic_webhook",
            "display_name": "internal",
            "config": {"url": "https://169.254.169.254/latest"},
            "credentials": {"signing_secret": GW_SECRET},
        },
    )
    assert private.status_code == 201 and private.json()["status"] == "error"
    assert "not allowed" in private.json()["last_error"]
    unknown = await api.post(
        "/api/v1/integrations/connections",
        json={"integration_key": "nope_nope", "display_name": "x"},
    )
    assert unknown.status_code == 404


async def test_create_time_failure_is_safe_and_health_is_recorded(env):
    env["provider"].handler = lambda r: httpx.Response(
        401, json={"error": {"message": "Invalid API Key provided: sk_test_***"}}
    )
    response = await env["api"].post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "stripe",
            "display_name": "Stripe",
            "mode": "sandbox",
            "credentials": {"secret_key": STRIPE_KEY},
        },
    )
    body = response.json()
    assert body["status"] == "error" and body["health"] == "failing"
    assert (
        body["last_error"] == "The provider rejected the credentials or they lack required access"
    )
    assert "Invalid API Key" not in response.text and STRIPE_KEY not in response.text
    before = len(env["provider"].requests)
    health = (await env["api"].get("/api/v1/integrations/health")).json()
    assert len(env["provider"].requests) == before  # health never calls providers
    assert health["summary"]["failing"] == 1
    assert health["connections"][0]["sync_state"] == "idle"
    assert health["connections"][0]["webhook_state"] == "healthy"


async def test_encryption_key_required(env):
    env["settings"].secrets_encryption_key = None
    response = await env["api"].post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "generic_webhook",
            "display_name": "x",
            "config": {"url": "https://hooks.example.com/a"},
            "credentials": {"signing_secret": GW_SECRET},
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENCRYPTION_NOT_CONFIGURED"


# --- isolation + RBAC -----------------------------------------------------------------------


async def test_cross_tenant_and_cross_environment_access_is_404(env):
    api = env["api"]
    connection = await connect_generic(api)
    hook = (
        await api.post(
            "/api/v1/integrations/webhooks",
            json={
                "name": "Orders",
                "url": "https://receiver.example.com/h",
                "event_types": ["order.confirmed"],
            },
        )
    ).json()
    key = (
        await api.post(
            "/api/v1/integrations/api-keys",
            json={"name": "CI", "scopes": ["customers.read"], "expires_in_days": None},
        )
    ).json()
    event_id = uuid4()
    await env["db"].execute(
        InboundEvent.__table__.insert().values(
            id=event_id,
            tenant_id=UUID(env["identity"]["tenant"]["id"]),
            environment_id=UUID(connection["environment_id"]),
            connection_id=UUID(connection["id"]),
            integration_key="generic_webhook",
            provider_event_id="e1",
            event_type="x",
            status="failed",
            payload_hash="0" * 64,
            received_at=datetime.now(UTC),
        )
    )
    cid = connection["id"]

    async def assert_hidden():
        for method, path, body in [
            ("GET", f"/api/v1/integrations/connections/{cid}", None),
            ("PATCH", f"/api/v1/integrations/connections/{cid}", {"display_name": "x"}),
            ("POST", f"/api/v1/integrations/connections/{cid}/test", None),
            ("DELETE", f"/api/v1/integrations/connections/{cid}", None),
            ("PATCH", f"/api/v1/integrations/webhooks/{hook['id']}", {"enabled": False}),
            ("GET", f"/api/v1/integrations/webhooks/{hook['id']}/deliveries", None),
            ("DELETE", f"/api/v1/integrations/api-keys/{key['id']}", None),
            ("POST", f"/api/v1/integrations/events/{event_id}/replay", None),
        ]:
            response = await api.request(method, path, json=body)
            assert response.status_code == 404, (method, path, response.text)
        assert (await api.get("/api/v1/integrations/connections")).json()["total"] == 0
        assert (await api.get("/api/v1/integrations/events")).json()["total"] == 0
        assert (await api.get("/api/v1/integrations/api-keys")).json() == []

    staging = await create(
        api, "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
    )
    switched = await api.put(
        "/api/v1/auth/session/workspace",
        json={"tenant_id": env["identity"]["tenant"]["id"], "environment_id": staging["id"]},
    )
    assert switched.status_code == 200
    await assert_hidden()  # same tenant, other environment
    await create(api, "auth/workspaces", {"name": "Other Tenant"})
    await assert_hidden()  # other tenant


async def test_rbac_denies_without_permissions(env):
    api = env["api"]
    connection = await connect_generic(api)
    reader_role = await create(
        api,
        "roles",
        {"key": "intg-reader", "name": "Integration reader", "permissions": ["integrations.read"]},
    )
    nobody_role = await create(
        api,
        "roles",
        {"key": "no-intg", "name": "No integrations", "permissions": ["customers.read"]},
    )
    for role, email_prefix in ((reader_role, "reader"), (nobody_role, "nobody")):
        email = f"{email_prefix}-{uuid4().hex}@example.com"
        await create(
            api,
            "members",
            {
                "email": email,
                "display_name": email_prefix,
                "initial_password": "MemberSecure123!",
                "role_ids": [role["id"]],
            },
        )
        async with httpx.AsyncClient(
            transport=api._transport,
            base_url="http://testserver",
            headers={"origin": "http://localhost:3000"},
        ) as member:
            login = await member.post(
                "/api/v1/auth/login", json={"email": email, "password": "MemberSecure123!"}
            )
            assert login.status_code == 200
            member.headers["x-csrf-token"] = member.cookies["platform_csrf"]
            listing = await member.get("/api/v1/integrations/connections")
            if email_prefix == "reader":
                assert listing.status_code == 200
                detail = await member.get(f"/api/v1/integrations/connections/{connection['id']}")
                assert detail.status_code == 200 and GW_SECRET not in detail.text
            else:
                assert listing.status_code == 403
            for method, path, body in [
                (
                    "POST",
                    "/api/v1/integrations/connections",
                    {"integration_key": "generic_webhook", "display_name": "x"},
                ),
                ("POST", f"/api/v1/integrations/connections/{connection['id']}/test", None),
                ("DELETE", f"/api/v1/integrations/connections/{connection['id']}", None),
                ("POST", "/api/v1/integrations/api-keys", {"name": "k", "scopes": []}),
                ("GET", "/api/v1/integrations/api-keys", None),
                (
                    "POST",
                    "/api/v1/integrations/webhooks",
                    {
                        "name": "w",
                        "url": "https://r.example.com",
                        "event_types": ["order.confirmed"],
                    },
                ),
            ]:
                response = await member.request(method, path, json=body)
                assert response.status_code == 403, (email_prefix, method, path)


# --- inbound webhooks -----------------------------------------------------------------------


def stripe_event(event_id="evt_1234567890"):
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": "payment_intent.succeeded",
            "created": int(time.time()),
            "livemode": False,
            "data": {
                "object": {
                    "id": "pi_1234567890",
                    "object": "payment_intent",
                    "client_secret": "pi_secret_should_not_persist",
                }
            },
        }
    ).encode()


def stripe_signature(body, ts=None, secret=WHSEC):
    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


async def test_inbound_webhook_pipeline(env):
    api, db, queue = env["api"], env["db"], env["app"].state.queue
    connection = await connect_stripe(env)
    detail = (await api.get(f"/api/v1/integrations/connections/{connection['id']}")).json()
    webhook_url = detail["webhook_url"]
    assert webhook_url.startswith("https://api.example.test/api/v1/webhooks/stripe/")
    path = urlsplit(webhook_url).path
    body = stripe_event()
    headers = {
        "stripe-signature": stripe_signature(body),
        "content-type": "application/json",
        "origin": "https://evil.example.com",
    }  # foreign Origin must not block webhooks
    first = await api.post(path, content=body, headers=headers)
    assert first.status_code == 200 and first.json()["accepted"] == 1
    assert [j[0] for j in queue.jobs] == ["process_inbound_event"]
    second = await api.post(path, content=body, headers=headers)
    assert second.status_code == 200 and second.json()["duplicates"] == 1
    assert len(queue.jobs) == 1  # duplicate: no new job
    count = await db.scalar(
        select(func.count())
        .select_from(InboundEvent)
        .where(InboundEvent.connection_id == UUID(connection["id"]))
    )
    assert count == 1
    row = await db.scalar(
        select(InboundEvent).where(InboundEvent.connection_id == UUID(connection["id"]))
    )
    assert row.payload_hash == hashlib.sha256(body).hexdigest() and row.signature_verified
    assert "pi_secret" not in json.dumps(row.payload)

    for bad_headers in (
        {"stripe-signature": stripe_signature(body, secret="whsec_wrong")},
        {},
        {"stripe-signature": stripe_signature(body, ts=int(time.time()) - 3600)},
    ):
        rejected = await api.post(path, content=stripe_event("evt_other12345"), headers=bad_headers)
        assert rejected.status_code == 401
    unknown = await api.post("/api/v1/webhooks/stripe/" + "A" * 43, content=body, headers=headers)
    wrong_key = await api.post(path.replace("/stripe/", "/slack/"), content=body, headers=headers)
    assert unknown.status_code == wrong_key.status_code == 404
    assert unknown.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert "stripe" not in unknown.json()["error"]["message"].lower()
    env["settings"].webhook_max_body_bytes = 1024
    huge = await api.post(path, content=b"x" * 2048, headers=headers)
    assert huge.status_code == 413

    # Worker: no handler -> ignored; replay after a handler exists -> processed, idempotent.
    await integration_jobs.process_inbound_event(env["ctx"], str(row.id))
    await db.refresh(row)
    assert row.status == "ignored"
    calls = []

    @webhooks.register_handler("stripe", "payment_intent.succeeded")
    async def handle(session, scope, event):
        assert scope.tenant_id == event.tenant_id and scope.is_system
        calls.append(event.id)
        return "processed"

    try:
        replay = await api.post(f"/api/v1/integrations/events/{row.id}/replay")
        assert replay.status_code == 200 and replay.json()["status"] == "queued"
        again = await api.post(f"/api/v1/integrations/events/{row.id}/replay")
        assert again.json()["status"] == "queued"
        replay_jobs = [j for j in queue.jobs if j[1] == (str(row.id),)]
        assert len(replay_jobs) == 2  # original receipt + one replay (second was a no-op)
        await integration_jobs.process_inbound_event(env["ctx"], str(row.id))
        await integration_jobs.process_inbound_event(env["ctx"], str(row.id))
        await db.refresh(row)
        assert row.status == "processed" and calls == [row.id]
    finally:
        webhooks._HANDLERS.pop(("stripe", "payment_intent.succeeded"), None)
    events = (
        await api.get("/api/v1/integrations/events", params={"connection_id": connection["id"]})
    ).json()
    assert events["total"] == 1 and events["items"][0]["provider_event_id"] == "evt_1234567890"


async def test_whatsapp_verification_handshake_and_pi_route_intact(env):
    api = env["api"]
    env["provider"].handler = lambda r: httpx.Response(
        200,
        json={"id": "1234567890", "display_phone_number": "+1 555 0100", "quality_rating": "GREEN"},
    )
    created = await api.post(
        "/api/v1/integrations/connections",
        json={
            "integration_key": "whatsapp_meta",
            "display_name": "Support line",
            "config": {"phone_number_id": "1234567890"},
            "credentials": {
                "access_token": "EAAG-token-value",
                "app_secret": "meta-app-secret",
                "verify_token": "verify-me",
            },
        },
    )
    assert created.json()["status"] == "connected"
    detail = (await api.get(f"/api/v1/integrations/connections/{created.json()['id']}")).json()
    path = urlsplit(detail["webhook_url"]).path
    ok = await api.get(
        path,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me",
            "hub.challenge": "8675309",
        },
    )
    assert ok.status_code == 200 and ok.text == "8675309"
    denied = await api.get(
        path, params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}
    )
    assert denied.status_code == 403
    body = json.dumps(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "1234567890"},
                                "messages": [
                                    {
                                        "id": "wamid.X1",
                                        "from": "15550001111",
                                        "type": "text",
                                        "text": {"body": "hello"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ],
        }
    ).encode()
    signature = "sha256=" + hmac.new(b"meta-app-secret", body, hashlib.sha256).hexdigest()
    received = await api.post(path, content=body, headers={"x-hub-signature-256": signature})
    assert received.status_code == 200 and received.json()["accepted"] == 1
    # PI's existing platform-level webhook still routes (unconfigured -> 403, not 404).
    assert (await api.get("/api/v1/webhooks/whatsapp")).status_code == 403


# --- outbox + deliveries ---------------------------------------------------------------------


async def test_outbox_delivery_signing_retry_dead_letter_and_manual_retry(env):
    api, db, s = env["api"], env["db"], env["settings"]
    s.delivery_max_attempts = 2
    created = await api.post(
        "/api/v1/integrations/webhooks",
        json={
            "name": "Orders",
            "url": "https://receiver.example.com/hook",
            "event_types": ["order.confirmed"],
            "enabled": True,
        },
    )
    assert created.status_code == 201
    hook = created.json()
    secret = hook["signing_secret"]
    assert secret.startswith("whsec_") and hook["secret_hint"] == "…" + secret[-4:]
    listed = await api.get("/api/v1/integrations/webhooks")
    assert secret not in listed.text and listed.json()["total"] == 1
    bad = await api.post(
        "/api/v1/integrations/webhooks",
        json={"name": "x", "url": "https://127.0.0.1/hook", "event_types": ["order.confirmed"]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "URL_REJECTED"
    unknown = await api.post(
        "/api/v1/integrations/webhooks",
        json={"name": "x", "url": "https://r.example.com/h", "event_types": ["order.exploded"]},
    )
    assert unknown.status_code == 422

    scope = scope_of(env)
    order_id = uuid4()
    await emit(
        db,
        scope,
        "order.confirmed",
        {"order_id": str(order_id), "total": "10.50"},
        EntityRef("order", order_id),
    )
    await emit(db, scope, "customer.created", {"customer_id": "c"})  # no subscriber
    with pytest.raises(ValueError):
        await emit(db, scope, "made.up", {})
    await db.commit()
    assert await integration_jobs.dispatch_outbox(env["ctx"]) == 1
    assert await integration_jobs.dispatch_outbox(env["ctx"]) == 0  # no duplicate delivery
    delivery = await db.scalar(select(Delivery).where(Delivery.subscription_id == UUID(hook["id"])))

    env["provider"].handler = lambda r: httpx.Response(500)
    assert await integration_jobs.deliver_webhook(env["ctx"], str(delivery.id)) == "failed"
    await db.refresh(delivery)
    assert delivery.next_attempt_at is not None and delivery.attempt_count == 1
    assert await integration_jobs.deliver_webhook(env["ctx"], str(delivery.id)) == "not_due"
    sent = env["provider"].requests[-1]
    assert verify_signature_header(secret, sent.content, sent.headers["x-platform-signature"])
    assert sent.headers["idempotency-key"] == f"{delivery.outbox_event_id}:{hook['id']}"
    payload = json.loads(sent.content)
    assert payload["type"] == "order.confirmed" and payload["data"]["total"] == "10.50"
    await db.execute(
        update(Delivery)
        .where(Delivery.id == delivery.id)
        .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    assert await integration_jobs.deliver_webhook(env["ctx"], str(delivery.id)) == "dead_letter"
    assert (
        env["provider"].requests[-1].headers["idempotency-key"] == sent.headers["idempotency-key"]
    )

    deliveries = (await api.get(f"/api/v1/integrations/webhooks/{hook['id']}/deliveries")).json()
    assert deliveries["items"][0]["status"] == "dead_letter"
    failures = (await api.get("/api/v1/integrations/failures")).json()
    assert failures["total"] == 1 and failures["items"][0]["kind"] == "delivery"
    queue = env["app"].state.queue
    queued_before = [j[0] for j in queue.jobs].count("deliver_webhook")
    retry = await api.post(f"/api/v1/integrations/deliveries/{delivery.id}/retry")
    assert retry.status_code == 200 and retry.json()["status"] == "pending"
    again = await api.post(f"/api/v1/integrations/deliveries/{delivery.id}/retry")
    assert again.json()["status"] == "pending"
    # Idempotent: the second retry request did not enqueue another attempt.
    assert [j[0] for j in queue.jobs].count("deliver_webhook") == queued_before + 1
    env["provider"].handler = lambda r: httpx.Response(204)
    assert await integration_jobs.deliver_webhook(env["ctx"], str(delivery.id)) == "succeeded"
    done = await api.post(f"/api/v1/integrations/deliveries/{delivery.id}/retry")
    assert done.status_code == 409
    rotated = (await api.post(f"/api/v1/integrations/webhooks/{hook['id']}/rotate-secret")).json()
    assert rotated["signing_secret"] != secret
    assert (await api.delete(f"/api/v1/integrations/webhooks/{hook['id']}")).status_code == 204
    assert (await api.get("/api/v1/integrations/webhooks")).json()["total"] == 0


async def test_private_redirect_target_is_never_followed(env):
    api, db = env["api"], env["db"]
    hook = (
        await api.post(
            "/api/v1/integrations/webhooks",
            json={
                "name": "R",
                "url": "https://receiver.example.com/hook",
                "event_types": ["invoice.paid"],
            },
        )
    ).json()
    await emit(db, scope_of(env), "invoice.paid", {"invoice_id": "i"})
    await db.commit()
    await integration_jobs.dispatch_outbox(env["ctx"])
    delivery = await db.scalar(select(Delivery).where(Delivery.subscription_id == UUID(hook["id"])))
    env["provider"].handler = lambda r: httpx.Response(
        307, headers={"location": "http://169.254.169.254/latest/meta-data"}
    )
    before = len(env["provider"].requests)
    assert await integration_jobs.deliver_webhook(env["ctx"], str(delivery.id)) == "failed"
    assert len(env["provider"].requests) == before + 1  # exactly one request, no follow


# --- OAuth ---------------------------------------------------------------------------------

FAKE_KEY = "fake_oauth"


class FakeOAuthProvider(IntegrationProvider):
    key = FAKE_KEY
    capabilities = frozenset({"read"})

    async def health_check(self, ctx):
        token = ctx.credentials.get("access_token")
        response = await ctx.http.request(
            "GET", "https://api.fake.example.com/me", headers={"authorization": f"Bearer {token}"}
        )
        response.ensure_success()
        return HealthResult(True, "ok")


@pytest.fixture
def fake_oauth_definition():
    definition = IntegrationDefinition(
        key=FAKE_KEY,
        name="Fake OAuth",
        description="Test only",
        category="identity",
        provider="Fake",
        auth_type="oauth2_pkce",
        capabilities=("read",),
        supported_scopes=("read", "write"),
        required_scopes=("read",),
        config_schema=(
            ConfigField("client_id", "Client ID"),
            ConfigField("client_secret", "Client secret", "password", secret=True, required=False),
        ),
        oauth=OAuthSpec(
            "https://auth.fake.example.com/authorize",
            "https://auth.fake.example.com/token",
            "https://auth.fake.example.com/revoke",
        ),
    )
    REGISTRY.register(definition, FakeOAuthProvider())
    yield definition
    REGISTRY._definitions.pop(FAKE_KEY, None)
    REGISTRY._providers.pop(FAKE_KEY, None)


def token_endpoint(tokens):
    def handler(request):
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            tokens.append(form)
            if form.get("grant_type") == ["refresh_token"] and form["refresh_token"] == ["bad"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": f"at-{len(tokens)}",
                    "refresh_token": f"rt-{len(tokens)}",
                    "expires_in": 3600,
                    "scope": "read",
                },
            )
        if request.url.path == "/revoke":
            return httpx.Response(200)
        return httpx.Response(200, json={"id": "me"})

    return handler


async def test_oauth_pkce_state_binding_and_refresh(env, fake_oauth_definition):
    api, db = env["api"], env["db"]
    tokens: list[dict] = []
    env["provider"].handler = token_endpoint(tokens)
    created = (
        await api.post(
            "/api/v1/integrations/connections",
            json={
                "integration_key": FAKE_KEY,
                "display_name": "Fake",
                "config": {"client_id": "client-123"},
                "credentials": {"client_secret": "client-secret-value"},
            },
        )
    ).json()
    assert created["status"] == "draft"
    cid = created["id"]
    start = await api.post(f"/api/v1/integrations/connections/{cid}/oauth/start")
    assert start.status_code == 200
    url = start.json()["authorization_url"]
    query = parse_qs(urlsplit(url).query)
    assert url.startswith("https://auth.fake.example.com/authorize?")
    assert query["redirect_uri"] == ["https://app.example.test/api/v1/integrations/oauth/callback"]
    assert query["code_challenge_method"] == ["S256"] and query["scope"] == ["read"]
    state = query["state"][0]
    stored = await db.scalar(select(OAuthState).where(OAuthState.connection_id == UUID(cid)))
    assert stored.state_hash == hashlib.sha256(state.encode()).hexdigest()
    assert state not in json.dumps([stored.state_hash, stored.code_verifier_encrypted])

    tampered = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": state + "x", "code": "abc"}
    )
    assert tampered.status_code == 302 and tampered.headers["location"].endswith("oauth=error")
    ok = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": state, "code": "abc"}
    )
    assert ok.headers["location"] == f"/settings/integrations/connections/{cid}?oauth=ok"
    exchange = tokens[0]
    assert exchange["grant_type"] == ["authorization_code"] and "code_verifier" in exchange
    assert exchange["redirect_uri"] == query["redirect_uri"]
    reused = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": state, "code": "abc"}
    )
    assert reused.headers["location"].endswith("oauth=error") and len(tokens) == 1
    detail = await api.get(f"/api/v1/integrations/connections/{cid}")
    assert detail.json()["status"] == "connected"
    assert "at-1" not in detail.text and "rt-1" not in detail.text
    assert "client-secret-value" not in detail.text

    # Expired state is rejected.
    second = parse_qs(
        urlsplit(
            (await api.post(f"/api/v1/integrations/connections/{cid}/oauth/start")).json()[
                "authorization_url"
            ]
        ).query
    )["state"][0]
    await db.execute(
        update(OAuthState)
        .where(OAuthState.state_hash == hashlib.sha256(second.encode()).hexdigest())
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    expired = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": second, "code": "abc"}
    )
    assert expired.headers["location"].endswith("oauth=error") and len(tokens) == 1

    # State is bound to the session's workspace: another tenant cannot redeem it.
    third = parse_qs(
        urlsplit(
            (await api.post(f"/api/v1/integrations/connections/{cid}/oauth/start")).json()[
                "authorization_url"
            ]
        ).query
    )["state"][0]
    await create(api, "auth/workspaces", {"name": "Elsewhere"})
    foreign = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": third, "code": "abc"}
    )
    assert foreign.headers["location"].endswith("oauth=error") and len(tokens) == 1

    # Refresh rotates tokens; an invalid grant marks the connection expired.
    connection = await db.scalar(
        select(IntegrationConnection).where(IntegrationConnection.id == UUID(cid))
    )
    http = OutboundClient(env["settings"], env["ctx"]["http"], resolver=public)
    connection.expires_at = datetime.now(UTC)
    assert oauth.needs_refresh(connection)
    assert await oauth.refresh(db, env["settings"], http, connection, fake_oauth_definition)
    assert tokens[-1]["grant_type"] == ["refresh_token"] and tokens[-1]["refresh_token"] == ["rt-1"]
    assert not oauth.needs_refresh(connection)
    from app.integrations.crypto import CredentialManager

    manager = CredentialManager(env["settings"])
    creds = manager.decrypt_json(connection.credentials_encrypted)
    assert creds["refresh_token"] == "rt-2" and creds["access_token"] == "at-2"
    creds["refresh_token"] = "bad"
    connection.credentials_encrypted = manager.encrypt_json(creds)
    assert not await oauth.refresh(db, env["settings"], http, connection, fake_oauth_definition)
    assert connection.status == "expired"


async def test_oauth_missing_required_scope_fails(env, fake_oauth_definition):
    api = env["api"]

    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t", "scope": "write"})
        return httpx.Response(200, json={})

    env["provider"].handler = handler
    cid = (
        await api.post(
            "/api/v1/integrations/connections",
            json={
                "integration_key": FAKE_KEY,
                "display_name": "Fake",
                "config": {"client_id": "client-123"},
            },
        )
    ).json()["id"]
    url = (await api.post(f"/api/v1/integrations/connections/{cid}/oauth/start")).json()[
        "authorization_url"
    ]
    state = parse_qs(urlsplit(url).query)["state"][0]
    result = await api.get(
        "/api/v1/integrations/oauth/callback", params={"state": state, "code": "c"}
    )
    assert result.headers["location"].endswith("oauth=error")
    detail = (await api.get(f"/api/v1/integrations/connections/{cid}")).json()
    assert detail["status"] == "error" and "not granted" in detail["last_error"]


# --- sync ----------------------------------------------------------------------------------


async def test_stripe_customer_sync_job(env):
    api, db = env["api"], env["db"]
    connection = await connect_stripe(env)
    customer = await create(api, "customers", {"name": "Alpha", "email": "alpha@example.com"})
    pages = {
        None: {
            "data": [{"id": "cus_ALPHA0001", "email": "Alpha@Example.com", "name": "Alpha"}],
            "has_more": True,
        },
        "cus_ALPHA0001": {
            "data": [{"id": "cus_BETA00002", "email": "beta@example.com"}],
            "has_more": False,
        },
    }

    def handler(request):
        if request.url.path == "/v1/customers":
            return httpx.Response(200, json=pages[request.url.params.get("starting_after")])
        return stripe_ok(request)

    env["provider"].handler = handler
    unsupported = await api.post(
        f"/api/v1/integrations/connections/{connection['id']}/sync",
        json={"entity": "orders", "mode": "full"},
    )
    assert unsupported.status_code == 422
    started = await api.post(
        f"/api/v1/integrations/connections/{connection['id']}/sync",
        json={"entity": "customers", "mode": "incremental"},
    )
    assert started.status_code == 201 and started.json()["status"] == "pending"
    duplicate = await api.post(
        f"/api/v1/integrations/connections/{connection['id']}/sync",
        json={"entity": "customers", "mode": "full"},
    )
    assert duplicate.status_code == 409
    job_id = started.json()["id"]
    assert await integration_jobs.run_sync_job(env["ctx"], job_id) == "succeeded"
    job = (await api.get("/api/v1/integrations/jobs")).json()["items"][0]
    assert job["status"] == "succeeded" and job["stats"]["discovered"] == 2
    assert job["stats"]["created"] == 2 and job["direction"] == "pull"
    ref = await db.scalar(
        select(ExternalReference).where(ExternalReference.external_id == "cus_ALPHA0001")
    )
    assert ref.platform_entity_id == UUID(customer["id"]) and ref.last_write_origin == "provider"
    again = await api.post(
        f"/api/v1/integrations/connections/{connection['id']}/sync",
        json={"entity": "customers", "mode": "incremental"},
    )
    await integration_jobs.run_sync_job(env["ctx"], again.json()["id"])
    rerun = next(
        j
        for j in (await api.get("/api/v1/integrations/jobs")).json()["items"]
        if j["id"] == again.json()["id"]
    )
    assert rerun["stats"]["skipped"] == 2 and rerun["stats"]["created"] == 0  # loop-safe
    # Controls
    third = (
        await api.post(
            f"/api/v1/integrations/connections/{connection['id']}/sync",
            json={"entity": "customers", "mode": "full"},
        )
    ).json()
    paused = await api.post(f"/api/v1/integrations/jobs/{third['id']}/pause")
    assert paused.json()["status"] == "paused"
    assert await integration_jobs.run_sync_job(env["ctx"], third["id"]) == "skipped"
    assert (await api.post(f"/api/v1/integrations/jobs/{third['id']}/resume")).json()[
        "status"
    ] == "pending"
    assert (await api.post(f"/api/v1/integrations/jobs/{third['id']}/cancel")).json()[
        "status"
    ] == "cancelled"
    assert (await api.post(f"/api/v1/integrations/jobs/{third['id']}/resume")).status_code == 422
    generic = await connect_generic(api)
    no_sync = await api.post(
        f"/api/v1/integrations/connections/{generic['id']}/sync", json={"entity": "customers"}
    )
    assert no_sync.status_code == 422


async def test_sync_failure_is_recorded_and_retryable(env):
    api = env["api"]
    connection = await connect_stripe(env)

    def handler(request):
        if request.url.path == "/v1/customers":
            return httpx.Response(401, json={})
        return stripe_ok(request)

    env["provider"].handler = handler
    job = (
        await api.post(
            f"/api/v1/integrations/connections/{connection['id']}/sync",
            json={"entity": "customers"},
        )
    ).json()
    assert await integration_jobs.run_sync_job(env["ctx"], job["id"]) == "dead_letter"
    failures = (await api.get("/api/v1/integrations/failures")).json()
    assert any(f["kind"] == "job" for f in failures["items"])
    detail = (await api.get(f"/api/v1/integrations/connections/{connection['id']}")).json()
    assert detail["status"] == "error"  # credentials rejected during sync


# --- API keys ------------------------------------------------------------------------------


async def test_api_keys_hashing_scopes_revocation_and_expiry(env):
    api, db = env["api"], env["db"]
    escalate = await api.post(
        "/api/v1/integrations/api-keys", json={"name": "x", "scopes": ["api_keys.manage"]}
    )
    assert escalate.status_code == 422
    unknown = await api.post(
        "/api/v1/integrations/api-keys", json={"name": "x", "scopes": ["root.everything"]}
    )
    assert unknown.status_code == 422
    created = await api.post(
        "/api/v1/integrations/api-keys",
        json={"name": "Reporting", "scopes": ["customers.read"], "expires_in_days": 30},
    )
    assert created.status_code == 201
    key = created.json()
    secret = key["secret"]
    assert secret.startswith(key["prefix"] + "_") and key["prefix"].startswith("pk_live_")
    row = await db.scalar(select(ApiKey).where(ApiKey.id == UUID(key["id"])))
    assert row.secret_hash == key_hash(secret) and secret not in json.dumps(row.scopes)
    listing = await api.get("/api/v1/integrations/api-keys")
    assert secret not in listing.text and listing.json()[0]["prefix"] == key["prefix"]
    scope = await authenticate(db, secret)
    assert scope.tenant_id == UUID(env["identity"]["tenant"]["id"])
    assert scope.environment_id == UUID(env["identity"]["environment"]["id"])
    assert scope.permissions == frozenset({"customers.read"})
    assert scope.actor_label == f"api_key:{key['prefix']}"
    await db.refresh(row)
    assert row.last_used_at is not None
    for bad in (secret[:-1] + ("A" if secret[-1] != "A" else "B"), "pk_live_zz_nope", ""):
        with pytest.raises(Unauthenticated):
            await authenticate(db, bad)
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == row.id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    with pytest.raises(Unauthenticated):
        await authenticate(db, secret)
    await db.execute(update(ApiKey).where(ApiKey.id == row.id).values(expires_at=None))
    assert (await api.delete(f"/api/v1/integrations/api-keys/{key['id']}")).status_code == 204
    with pytest.raises(Unauthenticated):
        await authenticate(db, secret)
    audits = {
        a.action
        for a in (await db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row.id))).all()
    }
    assert {"api_key.created", "api_key.revoked"} <= audits


async def test_api_key_prefix_by_environment_kind(env):
    api = env["api"]
    staging = await create(
        api, "environments", {"key": "dev", "name": "Dev", "kind": "development"}
    )
    await api.put(
        "/api/v1/auth/session/workspace",
        json={"tenant_id": env["identity"]["tenant"]["id"], "environment_id": staging["id"]},
    )
    key = (
        await api.post("/api/v1/integrations/api-keys", json={"name": "Dev", "scopes": []})
    ).json()
    assert key["prefix"].startswith("pk_test_")
    scope = await authenticate(env["db"], key["secret"])
    assert scope.environment_id == UUID(staging["id"])


# --- migration backfill --------------------------------------------------------------------


async def test_permission_backfill_restores_owner_admin_grants(env):
    db = env["db"]
    path = MIGRATION_0004
    spec = importlib.util.spec_from_file_location("migration_0004", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tenant_id = UUID(env["identity"]["tenant"]["id"])
    roles = {
        r.key: r.id
        for r in (await db.scalars(select(Role).where(Role.tenant_id == tenant_id))).all()
    }
    await db.execute(
        delete(RolePermission).where(
            RolePermission.tenant_id == tenant_id,
            RolePermission.permission.in_(module.NEW_PERMISSIONS),
        )
    )
    await db.execute(module.BACKFILL)
    await db.execute(module.BACKFILL)  # idempotent
    rows = (
        await db.execute(
            select(RolePermission.role_id, RolePermission.permission).where(
                RolePermission.tenant_id == tenant_id,
                RolePermission.permission.in_(module.NEW_PERMISSIONS),
            )
        )
    ).all()
    assert {(r, p) for r, p in rows} == {
        (roles[k], p) for k in ("owner", "admin") for p in module.NEW_PERMISSIONS
    }


async def test_outbox_uses_callers_transaction(env):
    db = env["db"]
    async with db.begin_nested() as nested:
        await emit(db, scope_of(env), "customer.created", {"customer_id": "x"})
        await nested.rollback()
    ids = await outbox.dispatch_pending(db, env["settings"])
    assert ids == []


async def test_circuit_opens_after_repeated_failures_and_is_reported(env):
    api = env["api"]
    connection = await connect_stripe(env)
    env["settings"].circuit_failure_threshold = 3
    env["provider"].handler = lambda r: httpx.Response(503)
    for _ in range(3):
        result = (
            await api.post(f"/api/v1/integrations/connections/{connection['id']}/test")
        ).json()
        assert not result["ok"]
    health = (await api.get("/api/v1/integrations/health")).json()["connections"][0]
    assert health["circuit_state"] == "open" and health["health"] == "failing"
    before = len(env["provider"].requests)
    paused = (await api.post(f"/api/v1/integrations/connections/{connection['id']}/test")).json()
    assert not paused["ok"] and "paused" in paused["message"]
    assert len(env["provider"].requests) == before  # open circuit: provider not called
