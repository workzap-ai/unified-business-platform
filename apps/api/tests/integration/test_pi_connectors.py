"""Business-owned connections: Google Calendar (OAuth, busy times, event sync) and Shopify
(per-shop OAuth with HMAC, customer-scoped order status), plus booking emails.

Google, Shopify and Resend are HTTP doubles (MockTransport) and AI is not involved: tools
are called through the ToolRegistry exactly as the runtime does. These tests prove the
trust boundaries and idempotency; they do not prove live provider behaviour.
"""

import base64
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from pydantic import SecretStr
from sqlalchemy import func, select
from test_pi_pipeline import Pi, pi_workspace
from test_pi_tools import conversation_with_run as _conversation_with_run
from test_service_lifecycle import create

from app.integrations import workflows
from app.integrations.crypto import CredentialManager
from app.integrations.http import OutboundClient
from app.integrations.providers.google_calendar import event_id
from app.integrations.workflow_models import IntegrationOperation
from app.modules.customers.models import Customer
from app.modules.integrations.models import IntegrationConnection
from app.modules.pi.models import PiConversation
from app.modules.pi.tools.registry import ToolRegistry
from app.modules.pi_saas import calendar_sync, connectors, work
from app.modules.pi_saas.models import PiBookableService, PiBooking
from app.shared.errors import PermissionDenied
from app.shared.scope import WorkspaceScope

pytestmark = pytest.mark.integration

ALL_DAY = {d: [["00:00", "23:59"]] for d in work.DAY_KEYS}
SHOPIFY_SECRET = "shpss_test_app_secret"
EVENTS = "https://www.googleapis.com/auth/calendar.events"
FREEBUSY = "https://www.googleapis.com/auth/calendar.freebusy"


async def conversation_with_run(pi: Pi, mid: str) -> tuple[Any, Any]:
    """A conversation Pi is handling (no AI is scripted, so undo the fallback handoff)."""
    conversation, run = await _conversation_with_run(pi, mid)
    await pi.db.execute(
        PiConversation.__table__.update()
        .where(PiConversation.id == conversation.id)
        .values(mode="ai", status="open")
    )
    return conversation, run


async def public(host: str, port: int) -> list[str]:
    return ["93.184.216.34"]


class Remote:
    """Scripted Google OAuth + Calendar, Shopify and Resend."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.events: dict[str, dict[str, Any]] = {}
        self.busy: list[tuple[datetime, datetime]] = []
        self.freebusy_fails = False
        self.token = "ya29.first"
        self.shop_customers: dict[str, list[str]] = {}  # phone/email -> customer ids
        self.orders: dict[str, list[dict[str, Any]]] = {}  # customer numeric id -> orders
        self.emails: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url, path = request.url, request.url.path
        if url.host == "oauth2.googleapis.com" and path == "/token":
            form = dict(parse_qsl(request.content.decode()))
            if form.get("grant_type") == "authorization_code" and form.get("code") == "good":
                assert form.get("code_verifier")  # PKCE is always used
                return httpx.Response(
                    200,
                    json={
                        "access_token": self.token,
                        "refresh_token": "1//refresh",
                        "expires_in": 3599,
                        "scope": f"{EVENTS} {FREEBUSY}",
                    },
                )
            if form.get("grant_type") == "refresh_token" and form.get("refresh_token"):
                self.token = "ya29.refreshed"
                return httpx.Response(200, json={"access_token": self.token, "expires_in": 3599})
            return httpx.Response(400, json={"error": "invalid_grant"})
        if url.host == "www.googleapis.com":
            if request.headers.get("authorization") != f"Bearer {self.token}":
                return httpx.Response(401)
            if path == "/calendar/v3/freeBusy":
                if self.freebusy_fails:
                    return httpx.Response(500)
                busy = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in self.busy]
                return httpx.Response(200, json={"calendars": {"primary": {"busy": busy}}})
            prefix = "/calendar/v3/calendars/primary/events"
            if path == prefix and request.method == "POST":
                body = json.loads(request.content)
                if body["id"] in self.events:
                    return httpx.Response(409, json={"error": {"code": 409}})
                self.events[body["id"]] = {**body, "sendUpdates": url.params.get("sendUpdates")}
                return httpx.Response(200, json=body)
            if path.startswith(prefix + "/"):
                key = path.rsplit("/", 1)[-1]
                if key not in self.events:
                    return httpx.Response(404)
                if request.method == "GET":
                    return httpx.Response(200, json=self.events[key])
                if request.method == "PATCH":
                    self.events[key].update(json.loads(request.content))
                    return httpx.Response(200, json=self.events[key])
                if request.method == "DELETE":
                    del self.events[key]
                    return httpx.Response(204)
            return httpx.Response(404)
        if url.host.endswith(".myshopify.com"):
            if path == "/admin/oauth/access_token":
                form = dict(parse_qsl(request.content.decode()))
                if form.get("client_secret") != SHOPIFY_SECRET or form.get("code") != "good":
                    return httpx.Response(400)
                assert form.get("expiring") == "1"
                return httpx.Response(
                    200,
                    json={
                        "access_token": "shpat_store",
                        "refresh_token": "shprt_store",
                        "expires_in": 3600,
                        "scope": "read_orders,read_customers",
                    },
                )
            if path == "/admin/api/2026-07/graphql.json":
                if request.headers.get("x-shopify-access-token") != "shpat_store":
                    return httpx.Response(401)
                body = json.loads(request.content)
                query = body["variables"]["q"]
                if "customers(" in body["query"]:
                    value = query.split(":", 1)[1].strip('"')
                    ids = self.shop_customers.get(value, [])
                    edges = [{"node": {"id": f"gid://shopify/Customer/{i}"}} for i in ids]
                    return httpx.Response(200, json={"data": {"customers": {"edges": edges}}})
                numeric = query.split(":", 1)[1]
                edges = [{"node": o} for o in self.orders.get(numeric, [])]
                return httpx.Response(200, json={"data": {"orders": {"edges": edges}}})
            return httpx.Response(404)
        if url.host == "api.resend.com" and path == "/emails":
            self.emails.append(json.loads(request.content))
            return httpx.Response(200, json={"id": f"email_{len(self.emails)}"})
        return httpx.Response(503)

    def count(self, host: str, method: str | None = None) -> int:
        return sum(
            1
            for r in self.requests
            if r.url.host == host and (method is None or r.method == method)
        )


def _settings(app: Any, remote: Remote) -> httpx.AsyncClient:
    s = app.state.settings
    if s.secrets_encryption_key is None:
        s.secrets_encryption_key = SecretStr(Fernet.generate_key().decode())
    s.google_oauth_client_id = "google-client.apps.googleusercontent.com"
    s.google_oauth_client_secret = SecretStr("google-secret")
    s.shopify_client_id = "shopify-client"
    s.shopify_client_secret = SecretStr(SHOPIFY_SECRET)
    s.integration_rate_limit_fallback_per_minute = 100000
    client = httpx.AsyncClient(transport=httpx.MockTransport(remote))
    app.state.http = client
    app.state.integration_resolver = public
    return client


async def _connection(
    db: Any,
    app: Any,
    tenant: str,
    environment: str,
    key: str,
    credentials: dict[str, str],
    config: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
) -> IntegrationConnection:
    """A connection as it is after a completed authorization."""
    row = IntegrationConnection(
        tenant_id=UUID(tenant),
        environment_id=UUID(environment),
        integration_key=key,
        display_name=key,
        mode="production",
        status="connected",
        health="healthy",
        config=config or {},
        credentials_encrypted=CredentialManager(app.state.settings).encrypt_json(credentials),
        scopes=[EVENTS, FREEBUSY] if key == "google_calendar" else [],
        connected_at=datetime.now(UTC),
        expires_at=expires_at,
    )
    db.add(row)
    await db.flush()
    return row


async def _booking_setup(api: httpx.AsyncClient, db: Any) -> tuple[Pi, Remote, Any, Any]:
    pi = await pi_workspace(api, db, business_type="service_business")
    remote = Remote()
    client = _settings(pi.app, remote)
    for tool in (
        "check_availability",
        "create_booking",
        "cancel_booking",
        "reschedule_booking",
        "email_booking_confirmation",
        "get_store_orders",
    ):
        response = await api.put(f"/api/v1/pi/tools/{tool}/enabled", json={"enabled": True})
        assert response.status_code == 200, response.text
    service = await create(
        api,
        "pi/bookable-services",
        {"name": "Consultation", "duration_minutes": 60, "working_hours": ALL_DAY},
    )
    outbound = OutboundClient(pi.app.state.settings, client, resolver=public)
    return pi, remote, service, (pi.app.state.settings, outbound)


async def test_google_calendar_busy_times_event_sync_and_idempotent_retries(api, business_db):
    pi, remote, service, http = await _booking_setup(api, business_db)
    try:
        conversation, run = await conversation_with_run(pi, "wamid.cal-1")
        await business_db.execute(
            Customer.__table__.update()
            .where(Customer.id == conversation.customer_id)
            .values(email="amina@example.com")
        )
        # An expired token is refreshed before the first calendar call.
        await _connection(
            business_db,
            pi.app,
            pi.tenant_id,
            pi.environment_id,
            "google_calendar",
            {"access_token": "ya29.stale", "refresh_token": "1//refresh"},
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        registry, scope = ToolRegistry(business_db, http), pi.scope()
        row = await business_db.get(PiBookableService, UUID(service["id"]))
        native = await work.available_slots(business_db, scope, row, "UTC")
        first = datetime.fromisoformat(native[0]["start"])
        remote.busy = [(first, first + timedelta(hours=1))]  # e.g. a dentist appointment

        async def call(name: str, args: Any) -> Any:
            return await registry.execute(scope, conversation, name, args, run=run)

        offered = await call("check_availability", {"service_id": service["id"], "days": 2})
        assert offered.ok, offered
        starts = [s["start"] for s in offered.data["services"][0]["slots"]]
        assert native[0]["start"] not in starts  # the calendar's busy time is not offered
        assert remote.token == "ya29.refreshed"
        # Booking the busy time is refused even if the model tries it.
        taken = await call("create_booking", {"service_id": service["id"], "start": first})
        assert (taken.ok, taken.error_code) == (False, "SLOT_UNAVAILABLE")
        booked = await call("create_booking", {"service_id": service["id"], "start": starts[0]})
        assert booked.ok, booked
        booking_id = UUID(booked.data["booking_id"])
        booking = await business_db.get(PiBooking, booking_id)
        assert booking.external_sync == "pending"
        assert remote.events == {}  # nothing is written to the calendar before commit
        await business_db.commit()

        # After commit the sync creates exactly one event and invites the customer.
        settings, outbound = http
        assert await calendar_sync.sync_booking(business_db, settings, outbound, booking_id) == (
            "synced"
        )
        event = remote.events[event_id(booking_id)]
        assert event["attendees"] == [{"email": "amina@example.com", "displayName": "Customer"}]
        assert event["sendUpdates"] == "all"
        # A retry after an uncertain outcome converges on the same event (409 -> read).
        booking = await business_db.get(PiBooking, booking_id, populate_existing=True)
        booking.external_sync = "pending"
        await business_db.commit()
        assert await calendar_sync.sync_booking(business_db, settings, outbound, booking_id) == (
            "synced"
        )
        assert len(remote.events) == 1

        # Reschedule moves the event; cancelling removes it.
        moved = await call(
            "reschedule_booking", {"booking_id": str(booking_id), "start": starts[2]}
        )
        assert moved.ok, moved
        await business_db.commit()
        await calendar_sync.sync_booking(business_db, settings, outbound, booking_id)
        event = remote.events[event_id(booking_id)]
        assert datetime.fromisoformat(event["start"]["dateTime"]) == datetime.fromisoformat(
            starts[2]
        )
        cancelled = await call("cancel_booking", {"booking_id": str(booking_id)})
        assert cancelled.ok and cancelled.data["status"] == "cancelled"
        await business_db.commit()
        await calendar_sync.sync_booking(business_db, settings, outbound, booking_id)
        assert remote.events == {}

        # A connected calendar that can't be read never means "everything is free".
        remote.freebusy_fails = True
        refused = await call("check_availability", {"service_id": service["id"]})
        assert (refused.ok, refused.error_code) == (False, "CALENDAR_UNAVAILABLE")
        refused = await call("create_booking", {"service_id": service["id"], "start": starts[3]})
        assert (refused.ok, refused.error_code) == (False, "CALENDAR_UNAVAILABLE")
    finally:
        await pi.close()


async def test_customers_only_move_or_confirm_their_own_bookings(api, business_db):
    pi, remote, service, http = await _booking_setup(api, business_db)
    try:
        conversation, run = await conversation_with_run(pi, "wamid.own-1")
        other = await create(api, "customers", {"name": "Other", "email": "o@example.com"})
        scope = pi.scope()
        row = await business_db.get(PiBookableService, UUID(service["id"]))
        slots = await work.available_slots(business_db, scope, row, "UTC")
        theirs = await work.book(
            business_db,
            scope,
            service_id=row.id,
            customer_id=UUID(other["id"]),
            conversation_id=None,
            starts_at=datetime.fromisoformat(slots[0]["start"]),
            timezone="UTC",
            idempotency_key=f"other-{uuid4()}",
        )
        registry = ToolRegistry(business_db, http)
        for tool, args in (
            ("reschedule_booking", {"booking_id": str(theirs.id), "start": slots[2]["start"]}),
            ("email_booking_confirmation", {"booking_id": str(theirs.id)}),
            ("cancel_booking", {"booking_id": str(theirs.id)}),
        ):
            result = await registry.execute(scope, conversation, tool, args, run=run)
            assert (result.ok, result.error_code) == (False, "RESOURCE_NOT_FOUND"), tool
        still = await business_db.get(PiBooking, theirs.id, populate_existing=True)
        assert still.status == "confirmed" and still.starts_at == datetime.fromisoformat(
            slots[0]["start"]
        )
        # No calendar connected: bookings still work from working hours alone.
        own = await registry.execute(
            scope,
            conversation,
            "create_booking",
            {"service_id": service["id"], "start": slots[4]["start"]},
            run=run,
        )
        assert own.ok, own
        assert (await business_db.get(PiBooking, UUID(own.data["booking_id"]))).external_sync == (
            "none"
        )
        assert remote.count("www.googleapis.com") == 0
    finally:
        await pi.close()


async def test_booking_confirmation_email_is_customer_facing_and_sent_once(api, business_db):
    pi, remote, service, http = await _booking_setup(api, business_db)
    try:
        conversation, run = await conversation_with_run(pi, "wamid.mail-1")
        registry, scope = ToolRegistry(business_db, http), pi.scope()
        row = await business_db.get(PiBookableService, UUID(service["id"]))
        slots = await work.available_slots(business_db, scope, row, "UTC")
        booked = await registry.execute(
            scope,
            conversation,
            "create_booking",
            {"service_id": service["id"], "start": slots[0]["start"]},
            run=run,
        )
        args = {"booking_id": booked.data["booking_id"]}
        missing = await registry.execute(
            scope, conversation, "email_booking_confirmation", args, run=run
        )
        assert missing.error_code == "CUSTOMER_EMAIL_REQUIRED"
        await business_db.execute(
            Customer.__table__.update()
            .where(Customer.id == conversation.customer_id)
            .values(email="amina@example.com")
        )
        nothing = await registry.execute(
            scope, conversation, "email_booking_confirmation", args, run=run
        )
        assert nothing.error_code == "EMAIL_NOT_CONNECTED"
        await _connection(
            business_db,
            pi.app,
            pi.tenant_id,
            pi.environment_id,
            "resend",
            {"api_key": "re_test_key"},
            {"from_address": "bookings@bright.example"},
        )
        for _ in range(2):
            queued = await registry.execute(
                scope, conversation, "email_booking_confirmation", args, run=run
            )
            assert queued.ok and queued.data == {
                "status": "queued",
                "recipient": "a***@example.com",
            }
        ops = list(
            await business_db.scalars(
                select(IntegrationOperation).where(
                    IntegrationOperation.tenant_id == UUID(pi.tenant_id),
                    IntegrationOperation.kind == "notification",
                )
            )
        )
        assert len(ops) == 1  # the same booking time is confirmed once
        await business_db.commit()
        settings, outbound = http
        assert await workflows.deliver(business_db, settings, outbound, ops[0].id) == "succeeded"
        [email] = remote.emails
        assert email["to"] == ["amina@example.com"]
        assert email["subject"] == "Booking confirmed: Consultation"
        assert "[info]" not in email["subject"] and "Hello Customer" in email["text"]
        assert "your workspace" not in email["html"]
        # The calendar invitation travels with the confirmation.
        [invite] = email["attachments"]
        assert invite["filename"] == "booking.ics"
        ics = base64.b64decode(invite["content"]).decode()
        assert "BEGIN:VEVENT" in ics and f"UID:booking-{args['booking_id']}@pi.workzap" in ics
    finally:
        await pi.close()


async def test_shopify_order_status_is_bound_to_the_verified_customer(api, business_db):
    pi, remote, _service, http = await _booking_setup(api, business_db)
    try:
        conversation, run = await conversation_with_run(pi, "wamid.shop-1")
        registry, scope = ToolRegistry(business_db, http), pi.scope()
        result = await registry.execute(scope, conversation, "get_store_orders", {}, run=run)
        assert result.ok and result.data == {"connected": False, "orders": []}
        await _connection(
            business_db,
            pi.app,
            pi.tenant_id,
            pi.environment_id,
            "shopify",
            {"access_token": "shpat_store"},
            {"shop_domain": "bright.myshopify.com"},
        )
        customer = await business_db.get(Customer, conversation.customer_id)
        order = {
            "name": "#1001",
            "createdAt": "2026-09-20T10:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "FULFILLED",
            "cancelledAt": None,
            "totalPriceSet": {"shopMoney": {"amount": "40.00", "currencyCode": "USD"}},
            "lineItems": {"edges": [{"node": {"title": "Blue mug", "quantity": 2}}]},
        }
        remote.shop_customers = {customer.phone: ["77"], "+15559990000": ["88"]}
        remote.orders = {"77": [order], "88": [{**order, "name": "#2002"}]}
        result = await registry.execute(scope, conversation, "get_store_orders", {}, run=run)
        assert result.ok, result
        assert [o["name"] for o in result.data["orders"]] == ["#1001"]
        assert result.data["orders"][0]["fulfillment_status"] == "FULFILLED"
        # Two store customers share the number: nothing is shown rather than guessing.
        remote.shop_customers[customer.phone] = ["77", "88"]
        result = await registry.execute(scope, conversation, "get_store_orders", {}, run=run)
        assert result.ok and result.data["orders"] == []
    finally:
        await pi.close()


def _shopify_callback(query: dict[str, str]) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    signed = {
        **query,
        "hmac": hmac.new(SHOPIFY_SECRET.encode(), message.encode(), "sha256").hexdigest(),
    }
    return "&".join(f"{k}={v}" for k, v in signed.items())


async def test_pi_app_connects_google_and_shopify_with_bound_single_use_state(api):
    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    remote = Remote()
    async with pi_client(app) as owner, pi_client(app) as intruder:
        await pi_register(owner, "Bright Studio")
        await pi_register(intruder, "Other Shop")
        _settings(app, remote)  # after registration: provider doubles for these hosts
        listed = (await owner.get("/api/v1/pi-app/pi/connectors")).json()
        assert [(c["key"], c["state"], c["available"]) for c in listed] == [
            ("google_calendar", "not_connected", True),
            ("shopify", "not_connected", True),
        ]
        assert "client" not in json.dumps(listed) and "token" not in json.dumps(listed)

        start = await owner.post("/api/v1/pi-app/pi/connectors/google_calendar/start")
        assert start.status_code == 200, start.text
        auth = urlsplit(start.json()["authorization_url"])
        params = {k: v[0] for k, v in parse_qs(auth.query).items()}
        assert auth.netloc == "accounts.google.com" and params["code_challenge_method"] == "S256"
        assert params["redirect_uri"] == (
            "http://localhost:3200/api/v1/pi-app/pi/connectors/google_calendar/callback"
        )
        assert params["access_type"] == "offline"
        callback = "/api/v1/pi-app/pi/connectors/google_calendar/callback"
        # Another business's session cannot complete (or burn) this authorization.
        stolen = await intruder.get(f"{callback}?state={params['state']}&code=good")
        assert stolen.headers["location"] == "/my-pi/tools?google_calendar=failed"
        done = await owner.get(f"{callback}?state={params['state']}&code=good")
        assert done.headers["location"] == "/my-pi/tools?google_calendar=connected"
        replay = await owner.get(f"{callback}?state={params['state']}&code=good")
        assert replay.headers["location"] == "/my-pi/tools?google_calendar=failed"  # single use

        bad = await owner.post(
            "/api/v1/pi-app/pi/connectors/shopify/start", json={"shop": "evil.com/x"}
        )
        assert bad.status_code == 422
        start = await owner.post(
            "/api/v1/pi-app/pi/connectors/shopify/start", json={"shop": "Bright.myshopify.com"}
        )
        assert start.status_code == 200, start.text
        auth = urlsplit(start.json()["authorization_url"])
        assert auth.netloc == "bright.myshopify.com" and auth.path == "/admin/oauth/authorize"
        state = parse_qs(auth.query)["state"][0]
        callback = "/api/v1/pi-app/pi/connectors/shopify/callback"
        query = {"code": "good", "shop": "bright.myshopify.com", "state": state, "timestamp": "1"}
        forged = await owner.get(f"{callback}?{_shopify_callback(query)[:-4]}beef")
        assert forged.headers["location"] == "/my-pi/tools?shopify=failed"
        other_shop = await owner.get(
            f"{callback}?{_shopify_callback({**query, 'shop': 'evil.myshopify.com'})}"
        )
        assert other_shop.headers["location"] == "/my-pi/tools?shopify=failed"
        start = await owner.post(
            "/api/v1/pi-app/pi/connectors/shopify/start", json={"shop": "bright.myshopify.com"}
        )
        state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
        ok = await owner.get(f"{callback}?{_shopify_callback({**query, 'state': state})}")
        assert ok.headers["location"] == "/my-pi/tools?shopify=connected"

        listed = (await owner.get("/api/v1/pi-app/pi/connectors")).json()
        assert [(c["key"], c["state"]) for c in listed] == [
            ("google_calendar", "connected"),
            ("shopify", "connected"),
        ]
        assert listed[1]["detail"] == "bright.myshopify.com"
        # The other business sees none of this.
        theirs = (await intruder.get("/api/v1/pi-app/pi/connectors")).json()
        assert {c["state"] for c in theirs} == {"not_connected"}

        tested = await owner.post("/api/v1/pi-app/pi/connectors/google_calendar/test")
        assert tested.json()["ok"] is True
        gone = await owner.delete("/api/v1/pi-app/pi/connectors/google_calendar")
        assert gone.status_code == 204
        assert remote.count("oauth2.googleapis.com") >= 2  # token exchange + revoke
        listed = (await owner.get("/api/v1/pi-app/pi/connectors")).json()
        assert listed[0]["state"] == "not_connected"


async def test_connecting_requires_integration_management(business_db, api):
    from app.modules.integrations.service import Runtime

    pi = await pi_workspace(api, business_db)
    remote = Remote()
    client = _settings(pi.app, remote)
    try:
        settings = pi.app.state.settings
        rt = Runtime(settings=settings, http=OutboundClient(settings, client, resolver=public))
        viewer = WorkspaceScope.system(
            UUID(pi.tenant_id),
            UUID(pi.environment_id),
            frozenset({"pi.read", "integrations.read"}),
            "viewer",
        )
        assert [c["state"] for c in await connectors.status(business_db, settings, viewer)] == [
            "not_connected",
            "not_connected",
        ]
        for attempt in (
            connectors.start_google(business_db, viewer, rt),
            connectors.start_shopify(business_db, viewer, rt, "bright.myshopify.com"),
            connectors.disconnect(business_db, viewer, rt, "shopify"),
        ):
            with pytest.raises(PermissionDenied):
                await attempt
        nobody = WorkspaceScope.system(
            UUID(pi.tenant_id), UUID(pi.environment_id), frozenset({"pi.read"}), "x"
        )
        with pytest.raises(PermissionDenied):
            await connectors.status(business_db, settings, nobody)
        created = await business_db.scalar(
            select(func.count())
            .select_from(IntegrationConnection)
            .where(IntegrationConnection.tenant_id == UUID(pi.tenant_id))
        )
        assert created == 0 and remote.requests == []
    finally:
        await pi.close()


async def test_a_working_calendar_is_not_hidden_by_a_newer_unfinished_attempt(
    api, business_db
):
    pi, remote, _, _ = await _booking_setup(api, business_db)
    try:
        working = await _connection(
            business_db,
            pi.app,
            pi.tenant_id,
            pi.environment_id,
            "google_calendar",
            {"access_token": "ya29.ok", "refresh_token": "1//refresh"},
        )
        await business_db.commit()
        # Someone starts connecting Google again from Owner OS Integrations and stops.
        draft = await api.post(
            "/api/v1/integrations/connections",
            json={"integration_key": "google_calendar", "display_name": "Second try"},
        )
        assert draft.status_code in (200, 201), draft.text
        chosen = await connectors.current(business_db, pi.scope(), "google_calendar")
        assert chosen is not None and chosen.id == working.id
        listed = (await api.get("/api/v1/pi/connectors")).json()
        calendar = next(c for c in listed if c["key"] == "google_calendar")
        assert calendar["state"] == "connected"
    finally:
        await pi.close()
