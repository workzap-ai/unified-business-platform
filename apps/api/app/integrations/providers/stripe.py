"""Stripe (https://docs.stripe.com/api).

* Test connection: GET /v1/balance (read-only).
* Payments: POST /v1/payment_intents (form-encoded) with an Idempotency-Key header;
  GET /v1/payment_intents/{id}. Client secrets are never returned by this platform API.
* Webhooks: Stripe-Signature "t=<ts>,v1=<hex HMAC-SHA256(whsec, '<ts>.' + body)>" with a
  replay window (settings.webhook_replay_window_seconds).
* Sync: customers pull (GET /v1/customers, cursor = starting_after). Platform CRM stays
  the source of truth: pulled customers are linked by email, never overwrite CRM data.
Mode: sandbox connections require sk_test_/rk_test_ keys, production sk_live_/rk_live_.
"""

import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.integrations.errors import IntegrationError
from app.integrations.providers.base import credential, hmac_sha256_hex, ok, within_window
from app.integrations.registry import (
    ConfigField,
    ConfigurationInvalid,
    CustomerSyncSource,
    ExternalCustomer,
    HealthResult,
    IntegrationDefinition,
    NormalizedEvent,
    PaymentIntent,
    PaymentProvider,
    ProviderContext,
    SyncEntityPolicy,
    SyncPage,
    WebhookReceiver,
)

KEY = re.compile(r"^(sk|rk)_(test|live)_[A-Za-z0-9]{10,}$")
ID = re.compile(r"^[a-z]{2,8}_[A-Za-z0-9]{6,64}$")
CHECKOUT_ID = re.compile(r"^cs_(?:test_|live_)?[A-Za-z0-9]{6,200}$")
CURRENCY = re.compile(r"^[a-z]{3}$")

DEFINITION = IntegrationDefinition(
    key="stripe",
    name="Stripe",
    description="Accept card payments with Stripe and link Stripe customers to your CRM.",
    category="payments",
    provider="Stripe",
    auth_type="api_key",
    capabilities=("payment_intents", "receive_events", "customer_sync"),
    webhook_support=True,
    sync_support=("pull",),
    sync_entities=(
        SyncEntityPolicy(
            "customers",
            "pull",
            "platform",
            "Stripe customers are linked to CRM customers by email; CRM data is never "
            "overwritten and ambiguous matches become conflicts.",
        ),
    ),
    supports_sandbox=True,
    documentation_url="https://docs.stripe.com/api",
    config_schema=(
        ConfigField(
            "secret_key",
            "Secret or restricted key",
            "password",
            secret=True,
            help="sk_test_… for sandbox, sk_live_… for production",
        ),
        ConfigField(
            "webhook_secret",
            "Webhook signing secret",
            "password",
            secret=True,
            required=False,
            help="whsec_… from the Stripe webhook endpoint",
        ),
    ),
)


class StripeProvider(PaymentProvider, WebhookReceiver, CustomerSyncSource):
    async def checkout(
        self, ctx: ProviderContext, data: dict[str, str], key: str
    ) -> dict[str, Any]:
        response = await ctx.http.request(
            "POST",
            f"{ctx.settings.stripe_api_base_url}/v1/checkout/sessions",
            headers={**self._headers(ctx), "Idempotency-Key": key},
            form=data,
            context=ctx.call,
        )
        return response.ensure_success().json_object()

    async def checkout_status(self, ctx: ProviderContext, session_id: str) -> dict[str, Any]:
        if not CHECKOUT_ID.fullmatch(session_id):
            raise IntegrationError("INVALID_CHECKOUT", "Invalid payment session")
        response = await ctx.http.request(
            "GET",
            f"{ctx.settings.stripe_api_base_url}/v1/checkout/sessions/{session_id}",
            headers=self._headers(ctx),
            context=ctx.call,
        )
        return response.ensure_success().json_object()

    key = "stripe"
    capabilities = frozenset(DEFINITION.capabilities)

    def validate_configuration(
        self, config: Mapping[str, Any], credentials: Mapping[str, str], settings: Settings
    ) -> None:
        secret = credentials.get("secret_key")
        if secret is not None and not KEY.fullmatch(secret):
            raise ConfigurationInvalid("Enter a Stripe secret or restricted key", "secret_key")
        hook = credentials.get("webhook_secret")
        if hook and not hook.startswith("whsec_"):
            raise ConfigurationInvalid("Webhook secrets start with whsec_", "webhook_secret")

    @staticmethod
    def check_mode(secret: str, mode: str) -> None:
        live = "_live_" in secret
        if (mode == "production") != live:
            raise ConfigurationInvalid(
                "Use a live key for production and a test key for sandbox", "secret_key"
            )

    def _base(self, ctx: ProviderContext) -> str:
        return ctx.settings.stripe_api_base_url.rstrip("/")

    def _headers(self, ctx: ProviderContext) -> dict[str, str]:
        secret = credential(ctx.credentials, "secret_key")
        self.check_mode(secret, ctx.mode)
        return {"authorization": f"Bearer {secret}"}

    async def health_check(self, ctx: ProviderContext) -> HealthResult:
        started = time.perf_counter()
        response = await ctx.http.request(
            "GET",
            f"{self._base(ctx)}/v1/balance",
            headers=self._headers(ctx),
            max_bytes=128 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        data = response.json_object()
        if data.get("object") != "balance":
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Stripe returned an unexpected response",
                kind="invalid_response",
            )
        mode = "live" if data.get("livemode") else "test"
        return ok(
            f"Stripe account reachable ({mode} mode)", int((time.perf_counter() - started) * 1000)
        )

    @staticmethod
    def _intent(data: Mapping[str, Any]) -> PaymentIntent:
        try:
            return PaymentIntent(
                id=str(data["id"])[:80],
                status=str(data["status"])[:40],
                amount_minor=int(data["amount"]),
                currency=str(data["currency"])[:3],
                client_secret_available=bool(data.get("client_secret")),
            )
        except (KeyError, TypeError, ValueError):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Stripe returned an unexpected response",
                kind="invalid_response",
            ) from None

    async def create_payment_intent(
        self,
        ctx: ProviderContext,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
        metadata: Mapping[str, str] | None = None,
    ) -> PaymentIntent:
        currency = currency.lower()
        if amount_minor <= 0 or not CURRENCY.fullmatch(currency):
            raise IntegrationError("INVALID_AMOUNT", "Amount or currency is invalid")
        form: dict[str, str] = {
            "amount": str(int(amount_minor)),
            "currency": currency,
            "automatic_payment_methods[enabled]": "true",
        }
        for k, v in list((metadata or {}).items())[:20]:
            form[f"metadata[{str(k)[:40]}]"] = str(v)[:500]
        headers = self._headers(ctx) | {"idempotency-key": idempotency_key[:255]}
        response = await ctx.http.request(
            "POST",
            f"{self._base(ctx)}/v1/payment_intents",
            form=form,
            headers=headers,
            max_bytes=128 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        return self._intent(response.json_object())

    async def retrieve_payment_intent(self, ctx: ProviderContext, intent_id: str) -> PaymentIntent:
        if not ID.fullmatch(intent_id):
            raise IntegrationError("INVALID_ID", "The payment reference is invalid")
        response = await ctx.http.request(
            "GET",
            f"{self._base(ctx)}/v1/payment_intents/{intent_id}",
            headers=self._headers(ctx),
            max_bytes=128 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        return self._intent(response.json_object())

    async def list_customers(
        self, ctx: ProviderContext, cursor: str | None, limit: int
    ) -> SyncPage[ExternalCustomer]:
        params = {"limit": str(max(1, min(limit, 100)))}
        if cursor:
            if not ID.fullmatch(cursor):
                raise IntegrationError("INVALID_CURSOR", "The sync cursor is invalid")
            params["starting_after"] = cursor
        response = await ctx.http.request(
            "GET",
            f"{self._base(ctx)}/v1/customers",
            params=params,
            headers=self._headers(ctx),
            max_bytes=2 * 1024 * 1024,
            context=ctx.call,
        )
        response.ensure_success()
        data = response.json_object()
        rows = data.get("data")
        if not isinstance(rows, list):
            raise IntegrationError(
                "INVALID_RESPONSE",
                "Stripe returned an unexpected response",
                kind="invalid_response",
            )
        items: list[ExternalCustomer] = []
        for row in rows:
            if not isinstance(row, dict) or not ID.fullmatch(str(row.get("id", ""))):
                continue
            email = row.get("email")
            name = row.get("name")
            phone = row.get("phone")
            fingerprint = hashlib.sha256(
                json.dumps([row.get("id"), email, name, phone], default=str).encode()
            ).hexdigest()
            created = row.get("created")
            items.append(
                ExternalCustomer(
                    external_id=str(row["id"]),
                    email=str(email).strip().lower()[:254] if email else None,
                    name=str(name)[:160] if name else None,
                    phone=str(phone)[:32] if phone else None,
                    updated_at=datetime.fromtimestamp(int(created), UTC)
                    if isinstance(created, int)
                    else None,
                    fingerprint=fingerprint,
                )
            )
        next_cursor = items[-1].external_id if data.get("has_more") and items else None
        return SyncPage(items, next_cursor)

    # --- webhooks ---------------------------------------------------------------------

    def verify_webhook(
        self,
        headers: Mapping[str, str],
        body: bytes,
        credentials: Mapping[str, str],
        settings: Settings,
        now: float,
    ) -> bool:
        secret = credentials.get("webhook_secret")
        header = headers.get("stripe-signature", "")
        if not secret or not header:
            return False
        parts: dict[str, list[str]] = {}
        for item in header.split(","):
            key, _, value = item.strip().partition("=")
            parts.setdefault(key, []).append(value)
        timestamp = (parts.get("t") or [""])[0]
        if not within_window(timestamp, now, settings.webhook_replay_window_seconds):
            return False
        expected = hmac_sha256_hex(secret, f"{timestamp}.".encode() + body)
        return any(hmac.compare_digest(expected, sig) for sig in parts.get("v1", []))

    def parse_webhook(self, body: bytes) -> list[NormalizedEvent]:
        event = json.loads(body)
        if not isinstance(event, dict) or event.get("object") != "event":
            raise ValueError("Not a Stripe event")
        event_id, event_type = str(event.get("id", "")), str(event.get("type", ""))
        if not ID.fullmatch(event_id) or not re.fullmatch(r"[a-z0-9_.]{3,100}", event_type):
            raise ValueError("Invalid Stripe event")
        obj = event.get("data", {}).get("object", {}) if isinstance(event.get("data"), dict) else {}
        created = event.get("created")
        return [
            NormalizedEvent(
                provider_event_id=event_id,
                event_type=event_type,
                occurred_at=datetime.fromtimestamp(created, UTC)
                if isinstance(created, int)
                else None,
                data={
                    "object_id": str(obj.get("id", ""))[:80] if isinstance(obj, dict) else "",
                    "object_type": str(obj.get("object", ""))[:40] if isinstance(obj, dict) else "",
                    "livemode": bool(event.get("livemode")),
                },
            )
        ]
