"""Kapso platform adapter (WhatsApp onboarding provider).

Endpoints and fields follow Kapso's public documentation as read on 2026-09-29:

- ``POST /platform/v1/customers`` {"customer": {"name", "external_customer_id"}}
- ``POST /platform/v1/customers/{id}/setup_links`` (success/failure redirect URLs,
  allowed_connection_types coexistence|dedicated, language, provision_phone_number,
  phone_number_country_isos, reconnect_phone_number)
- ``GET /platform/v1/customers/{id}/setup_links`` (whatsapp_setup_status)
- ``GET /platform/v1/whatsapp/phone_numbers`` (every number in the project; optional
  ``customer_id`` filter, ``page``/``per_page``)
- ``POST /platform/v1/customers/{id}/whatsapp/phone_numbers`` (connect a number the
  platform already owns, with a permanent Meta System User token)
- ``GET|POST /platform/v1/whatsapp/phone_numbers/{id}/webhooks`` (per-number message
  webhooks: url, secret_key, events)
- ``GET /platform/v1/whatsapp/phone_numbers/{phone_number_id}/health``
- ``DELETE /platform/v1/whatsapp/phone_numbers/{phone_number_id}``
- ``POST /platform/v1/whatsapp/flows`` (create and publish a WhatsApp Flow)
- Meta proxy ``GET|POST /meta/whatsapp/{version}/{waba_id}/message_templates``
- Setup links also take ``meta_billing_mode`` (partner_managed = Kapso credits) and
  ``reconnect_phone_number`` as an E.164 number.
- Authentication: ``X-API-Key`` with the server-held project key.
- Webhooks: ``X-Webhook-Signature`` = hex HMAC-SHA256(secret, raw body),
  ``X-Webhook-Event`` event name, ``X-Idempotency-Key`` for deduplication, optional
  batched envelope ``{"batch": true, "data": [...]}``.

Contract tests use an HTTP mock transport. Live behaviour (including the exact health
payload and media download host) has NOT been verified against a real Kapso project.
Kapso documents no API for buying numbers or for moving a number to another customer,
so the platform keeps its shared numbers under one pool customer and maps them to
businesses in our database; nothing is purchased automatically.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.modules.pi_saas.json_util import as_dict, as_list
from app.shared.errors import BusinessRuleViolation

PHONE_NUMBER_ID = re.compile(r"^[0-9]{5,32}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
CONNECTION_TYPES = ("coexistence", "dedicated")
SETUP_LANGUAGES = {"en", "es", "pt", "hi", "id", "ar"}


class KapsoUnavailable(BusinessRuleViolation):
    def __init__(self, code: str = "PROVIDER_UNAVAILABLE") -> None:
        super().__init__(code, "The WhatsApp provider could not be reached. Try again.", 503)


@dataclass(frozen=True)
class SetupLink:
    id: str
    url: str
    expires_at: str | None
    status: str | None


MESSAGE_EVENTS = (
    "whatsapp.message.received",
    "whatsapp.message.sent",
    "whatsapp.message.delivered",
    "whatsapp.message.read",
    "whatsapp.message.failed",
)
TEMPLATE_CATEGORIES = ("MARKETING", "UTILITY")
APPROVED_NAME_STATES = {"APPROVED", "AVAILABLE_WITHOUT_REVIEW"}


@dataclass(frozen=True)
class PhoneNumber:
    phone_number_id: str
    display_phone_number: str
    business_account_id: str
    status: str
    display_name: str
    quality_rating: str | None
    customer_id: str = ""
    is_coexistence: bool = False
    name_status: str = ""
    verified_name: str = ""
    inbound_processing_enabled: bool = True
    kind: str = "production"

    @property
    def warnings(self) -> list[str]:
        """Problems an operator should fix before giving this number to anyone."""
        out: list[str] = []
        if self.name_status and self.name_status.upper() not in APPROVED_NAME_STATES:
            out.append("display_name_not_approved")
        if self.display_phone_number.replace(" ", "").replace("-", "").startswith("+1555"):
            out.append("meta_test_number")  # Meta's display-name-only virtual numbers
        quality = (self.quality_rating or "").upper()
        if quality in {"RED", "YELLOW"}:
            out.append(f"quality_{quality.lower()}")
        if not self.inbound_processing_enabled:
            out.append("inbound_processing_off")
        if self.kind == "sandbox":
            out.append("sandbox")
        return out


def _number(item: dict[str, Any]) -> PhoneNumber | None:
    number_id = str(item.get("phone_number_id") or item.get("id") or "")
    if not PHONE_NUMBER_ID.fullmatch(number_id):
        return None
    quality = item.get("quality_rating")
    return PhoneNumber(
        phone_number_id=number_id,
        display_phone_number=str(item.get("display_phone_number") or "")[:32],
        business_account_id=re.sub(r"\D", "", str(item.get("business_account_id") or ""))[:32],
        status=str(item.get("status") or "")[:32],
        display_name=str(item.get("display_name") or item.get("verified_name") or "")[:120],
        quality_rating=str(quality)[:16] if quality else None,
        customer_id=str(item.get("customer_id") or "")[:120],
        is_coexistence=bool(item.get("is_coexistence")),
        name_status=str(item.get("name_status") or "")[:40],
        verified_name=str(item.get("verified_name") or "")[:120],
        inbound_processing_enabled=item.get("inbound_processing_enabled") is not False,
        kind=str(item.get("kind") or "production")[:16],
    )


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


class Kapso:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings, self.http = settings, http

    @property
    def configured(self) -> bool:
        return self.settings.kapso_api_key is not None

    def _headers(self) -> dict[str, str]:
        key = self.settings.kapso_api_key
        if key is None:
            raise BusinessRuleViolation(
                "PROVIDER_NOT_CONFIGURED",
                "WhatsApp onboarding is not available yet. Our team has been notified.",
                503,
            )
        return {"X-API-Key": key.get_secret_value(), "Accept": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.settings.kapso_base_url.rstrip('/')}/platform/v1{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self._headers()
        try:
            response = await self.http.request(
                method,
                self._url(path),
                headers=headers,
                json=json,
                params=params,
                timeout=15,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise KapsoUnavailable() from None
        if response.status_code in (401, 403):
            raise BusinessRuleViolation(
                "PROVIDER_REJECTED_CREDENTIALS", "The WhatsApp provider rejected our access", 502
            )
        if response.status_code == 404:
            raise BusinessRuleViolation(
                "PROVIDER_NOT_FOUND", "The provider record was not found", 404
            )
        if response.status_code >= 400:
            raise KapsoUnavailable("PROVIDER_ERROR")
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
        except ValueError:
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE") from None
        if not isinstance(data, dict):
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE")
        return data

    async def create_customer(self, name: str, external_id: str) -> str:
        data = await self._request(
            "POST",
            "/customers",
            json={"customer": {"name": name[:160], "external_customer_id": external_id}},
        )
        customer_id = str((data.get("data") or {}).get("id", ""))
        if not SAFE_ID.fullmatch(customer_id):
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE")
        return customer_id

    async def create_setup_link(
        self,
        customer_id: str,
        *,
        success_url: str,
        failure_url: str,
        connection_types: tuple[str, ...] = CONNECTION_TYPES,
        language: str | None = None,
        reconnect_phone_number: str | None = None,
        provision_country: str | None = None,
        billing_mode: str | None = None,
    ) -> SetupLink:
        if not SAFE_ID.fullmatch(customer_id):
            raise BusinessRuleViolation("PROVIDER_NOT_FOUND", "The provider record was not found")
        body: dict[str, Any] = {
            "success_redirect_url": success_url,
            "failure_redirect_url": failure_url,
            "allowed_connection_types": [t for t in connection_types if t in CONNECTION_TYPES],
        }
        if language in SETUP_LANGUAGES:
            body["language"] = language
        e164 = "+" + re.sub(r"\D", "", reconnect_phone_number or "")
        if reconnect_phone_number and re.fullmatch(r"\+[1-9][0-9]{6,14}", e164):
            body["reconnect_phone_number"] = e164  # Kapso expects E.164, not the Meta id
        mode = billing_mode or self.settings.kapso_meta_billing_mode
        if mode in {"partner_managed", "customer_managed"}:
            body["meta_billing_mode"] = mode
        if provision_country and re.fullmatch(r"[A-Z]{2}", provision_country):
            # Only after the business confirmed the quoted price (see operator routes).
            body["provision_phone_number"] = True
            body["phone_number_country_isos"] = [provision_country]
        data = (
            await self._request(
                "POST", f"/customers/{customer_id}/setup_links", json={"setup_link": body}
            )
        ).get("data") or {}
        link_id, url = str(data.get("id", "")), str(data.get("url", ""))
        if not SAFE_ID.fullmatch(link_id) or not url.startswith("https://"):
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE")
        return SetupLink(
            link_id, url[:1000], data.get("expires_at"), data.get("whatsapp_setup_status")
        )

    async def phone_numbers(self, customer_id: str) -> list[PhoneNumber]:
        if not SAFE_ID.fullmatch(customer_id):
            return []
        return await self.list_numbers(customer_id)

    async def list_numbers(
        self, customer_id: str | None = None, max_pages: int = 10
    ) -> list[PhoneNumber]:
        """Numbers in the project (every customer unless ``customer_id`` is given)."""
        numbers: list[PhoneNumber] = []
        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {"page": page, "per_page": 100}
            if customer_id:
                params["customer_id"] = customer_id
            data = await self._request("GET", "/whatsapp/phone_numbers", params=params)
            items = [i for i in as_list(data.get("data")) if isinstance(i, dict)]
            numbers += [n for n in (_number(i) for i in items) if n is not None]
            total_pages = as_dict(data.get("meta")).get("total_pages")
            if len(items) < 100 or (isinstance(total_pages, int) and page >= total_pages):
                break
        return numbers

    async def connect_number(
        self,
        customer_id: str,
        *,
        name: str,
        phone_number_id: str,
        business_account_id: str,
        access_token: str,
    ) -> PhoneNumber:
        """Attach a number the platform already owns to a Kapso customer. The permanent
        Meta token goes straight to Kapso and is never stored by us."""
        if not SAFE_ID.fullmatch(customer_id) or not PHONE_NUMBER_ID.fullmatch(phone_number_id):
            raise BusinessRuleViolation("INVALID_NUMBER", "Check the phone number ID")
        if not re.fullmatch(r"[0-9]{5,32}", business_account_id):
            raise BusinessRuleViolation("INVALID_ACCOUNT", "Check the WhatsApp Business Account ID")
        token = access_token.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,600}", token):
            raise BusinessRuleViolation(
                "INVALID_TOKEN", "Paste a permanent System User access token from Meta"
            )
        try:
            data = await self._request(
                "POST",
                f"/customers/{customer_id}/whatsapp/phone_numbers",
                json={
                    "whatsapp_phone_number": {
                        "name": name[:120] or phone_number_id,
                        "phone_number_id": phone_number_id,
                        "business_account_id": business_account_id,
                        "access_token": token,
                        "inbound_processing_enabled": True,
                    }
                },
            )
        except KapsoUnavailable as exc:
            if exc.code == "PROVIDER_ERROR":
                raise BusinessRuleViolation(
                    "NUMBER_NOT_CONNECTED",
                    "Kapso couldn't connect this number. It may already be connected, or the "
                    "Kapso plan's number limit is reached.",
                    409,
                ) from None
            raise
        number = _number(as_dict(data.get("data")) or data)
        if number is None:
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE")
        return number

    async def ensure_webhook(self, phone_number_id: str, url: str, secret: str) -> str:
        """Make sure this number sends message events to us (created once)."""
        if not PHONE_NUMBER_ID.fullmatch(phone_number_id) or not url.startswith("https://"):
            raise BusinessRuleViolation(
                "WEBHOOK_URL_REQUIRED", "Set a public HTTPS API address for webhooks first"
            )
        path = f"/whatsapp/phone_numbers/{phone_number_id}/webhooks"
        for hook in as_list((await self._request("GET", path)).get("data")):
            if isinstance(hook, dict) and hook.get("url") == url:
                return "exists"
        await self._request(
            "POST",
            path,
            json={
                "whatsapp_webhook": {
                    "url": url,
                    "secret_key": secret,
                    "kind": "kapso",
                    "events": list(MESSAGE_EVENTS),
                    "active": True,
                }
            },
        )
        return "created"

    async def create_flow(
        self, phone_number_id: str, name: str, flow_json: dict[str, Any], publish: bool = True
    ) -> str:
        if not PHONE_NUMBER_ID.fullmatch(phone_number_id):
            raise BusinessRuleViolation("INVALID_NUMBER", "Unknown WhatsApp number")
        data = await self._request(
            "POST",
            "/whatsapp/flows",
            json={
                "whatsapp_flow": {
                    "phone_number_id": phone_number_id,
                    "name": name[:100],
                    "flow_json": flow_json,
                    "publish": publish,
                }
            },
        )
        body = as_dict(data.get("data")) or data
        flow_id = str(body.get("meta_flow_id") or body.get("flow_id") or body.get("id") or "")
        if not re.fullmatch(r"[0-9]{5,32}", flow_id):
            raise KapsoUnavailable("PROVIDER_BAD_RESPONSE")
        return flow_id

    # ---------------------------------------------------- Meta proxy (templates)

    def _meta_url(self, path: str) -> str:
        base = self.settings.kapso_base_url.rstrip("/")
        return f"{base}/meta/whatsapp/{self.settings.kapso_meta_api_version}{path}"

    async def _meta(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = self._headers()
        try:
            response = await self.http.request(
                method,
                self._meta_url(path),
                headers=headers,
                timeout=15,
                follow_redirects=False,
                **kwargs,
            )
        except httpx.HTTPError:
            raise KapsoUnavailable() from None
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        if response.status_code == 400:
            detail = as_dict(as_dict(data).get("error"))
            message = detail.get("error_user_msg") or detail.get("message") or "Meta rejected it"
            raise BusinessRuleViolation("TEMPLATE_REJECTED", str(message)[:300])
        if response.status_code in (401, 403):
            raise BusinessRuleViolation(
                "PROVIDER_REJECTED_CREDENTIALS", "The WhatsApp provider rejected our access", 502
            )
        if response.status_code >= 400:
            raise KapsoUnavailable("PROVIDER_ERROR")
        return data if isinstance(data, dict) else {}

    async def list_templates(self, business_account_id: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"[0-9]{5,32}", business_account_id):
            return []
        data = await self._meta(
            "GET",
            f"/{business_account_id}/message_templates",
            params={"fields": "name,status,language,category,components", "limit": 100},
        )
        out = []
        for item in as_list(data.get("data")):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            components = [c for c in as_list(item.get("components")) if isinstance(c, dict)]
            body = next((str(c.get("text", "")) for c in components if c.get("type") == "BODY"), "")
            out.append(
                {
                    "name": str(item["name"])[:512],
                    "language": str(item.get("language") or "")[:16],
                    "status": str(item.get("status") or "")[:24],
                    "category": str(item.get("category") or "")[:24],
                    "body": body[:1024],
                    # Campaigns and reminders can only send plain text templates.
                    "sendable": "{{" not in body
                    and not any(c.get("type") == "BUTTONS" for c in components)
                    and all(
                        c.get("format", "TEXT") == "TEXT"
                        for c in components
                        if c.get("type") == "HEADER"
                    ),
                }
            )
        return out

    async def create_template(
        self, business_account_id: str, name: str, language: str, category: str, body: str
    ) -> str:
        if not re.fullmatch(r"[0-9]{5,32}", business_account_id):
            raise BusinessRuleViolation("WHATSAPP_NOT_CONNECTED", "Connect WhatsApp first")
        if (
            not re.fullmatch(r"[a-z0-9_]{1,512}", name)
            or not re.fullmatch(r"[a-z]{2,3}(_[A-Z]{2})?", language)
            or category not in TEMPLATE_CATEGORIES
            or not 1 <= len(body) <= 1024
            or "{{" in body
        ):
            raise BusinessRuleViolation(
                "INVALID_TEMPLATE",
                "Use a lowercase name, a language code and plain text without variables",
            )
        data = await self._meta(
            "POST",
            f"/{business_account_id}/message_templates",
            json={
                "name": name,
                "language": language,
                "category": category,
                "components": [{"type": "BODY", "text": body}],
            },
        )
        return str(data.get("status") or "PENDING")[:24]

    async def health(self, phone_number_id: str) -> dict[str, Any]:
        if not PHONE_NUMBER_ID.fullmatch(phone_number_id):
            raise BusinessRuleViolation("INVALID_NUMBER", "Unknown WhatsApp number")
        data = await self._request("GET", f"/whatsapp/phone_numbers/{phone_number_id}/health")
        body = as_dict(data.get("data")) or data
        checks = as_dict(body.get("checks"))
        # Keep only statuses; provider error text stays out of customer views.
        return {
            "status": str(body.get("status", "unknown"))[:16],
            "checks": {
                str(k)[:40]: str(as_dict(v).get("status", v) if isinstance(v, dict) else v)[:16]
                for k, v in list(checks.items())[:10]
            },
        }

    async def delete_number(self, phone_number_id: str) -> None:
        if not PHONE_NUMBER_ID.fullmatch(phone_number_id):
            raise BusinessRuleViolation("INVALID_NUMBER", "Unknown WhatsApp number")
        await self._request("DELETE", f"/whatsapp/phone_numbers/{phone_number_id}")


def split_events(payload: Any, header_event: str) -> list[tuple[str, dict[str, Any]]]:
    """Return (event_type, event) pairs for a direct or batched webhook body."""
    if isinstance(payload, dict) and payload.get("batch") is True:
        event_type = str(payload.get("type") or header_event)
        items = as_list(payload.get("data"))
        return [(event_type, item) for item in items[:100] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [(str(payload.get("event") or header_event), payload)]
    return []
