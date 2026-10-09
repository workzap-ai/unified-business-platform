"""WhatsApp connection lifecycle through Kapso, for standalone Pi businesses and for
Owner OS workspaces alike (a ``Target`` is one tenant environment of either kind).

The business authorizes its own number on Kapso's hosted setup page (Meta embedded
signup, existing numbers incl. Business App coexistence), or takes a number from the
platform's pool (see ``number_pool``). Redirect query parameters are
never trusted: a number is linked only after the provider API confirms it belongs to
this business's own Kapso customer record. Each linked number maps to exactly one
business environment; a number already mapped elsewhere is never silently re-bound.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.audit.service import record
from app.modules.notifications.service import notify
from app.modules.pi.models import WhatsAppConnection, WhatsAppWebhookEvent
from app.modules.pi_saas.json_util import as_dict, as_list
from app.modules.pi_saas.kapso import PHONE_NUMBER_ID, Kapso, PhoneNumber
from app.modules.pi_saas.models import PiBusinessAccount, PiProviderConnection, PiProviderEvent
from app.modules.pi_saas.onboarding import env_scope, refresh_state
from app.shared.errors import BusinessRuleViolation, Conflict
from app.shared.scope import WorkspaceScope

Environment = Literal["production", "test"]


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment = "production"
    # coexistence keeps using the WhatsApp Business App on the same number.
    connection_types: list[Literal["coexistence", "dedicated"]] = Field(
        default=["coexistence", "dedicated"], min_length=1, max_length=2
    )


class NumberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    environment: Environment = "production"
    country: str = Field(pattern=r"^[A-Z]{2}$")
    notes: str = Field(default="", max_length=500)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Environment = "production"
    phone_number_id: str | None = Field(default=None, pattern=r"^[0-9]{5,32}$")


def _environment_id(account: PiBusinessAccount, environment: Environment) -> UUID:
    return (
        account.test_environment_id if environment == "test" else account.production_environment_id
    )


@dataclass(frozen=True)
class Target:
    """One tenant environment that connects WhatsApp: a Pi business (``account`` set)
    or an Owner OS workspace (no account). ``app`` decides where Kapso sends people
    back after setup."""

    tenant_id: UUID
    environment_id: UUID
    environment: str  # "production" / "test" (used in the Kapso customer name and id)
    name: str
    language: str
    app: Literal["pi", "web"]
    account: PiBusinessAccount | None = None


def pi_target(account: PiBusinessAccount, environment: Environment) -> Target:
    return Target(
        account.tenant_id,
        _environment_id(account, environment),
        environment,
        account.name,
        account.language,
        "pi",
        account,
    )


async def workspace_target(session: AsyncSession, tenant_id: UUID, environment_id: UUID) -> Target:
    """An Owner OS workspace environment (or a Pi business reached by tenant id)."""
    from app.modules.environments.models import Environment as EnvironmentRow
    from app.modules.tenants.models import Tenant

    account = await session.scalar(
        select(PiBusinessAccount).where(PiBusinessAccount.tenant_id == tenant_id)
    )
    if account is not None:
        env: Environment = "test" if environment_id == account.test_environment_id else "production"
        return pi_target(account, env)
    tenant = await session.get(Tenant, tenant_id)
    environment = await session.get(EnvironmentRow, environment_id)
    if tenant is None or environment is None or environment.tenant_id != tenant_id:
        raise BusinessRuleViolation("WORKSPACE_NOT_FOUND", "Workspace not found", 404)
    return Target(tenant_id, environment_id, environment.key[:40], tenant.name, "en", "web", None)


Subject = PiBusinessAccount | Target


def _target(subject: Subject, environment: Environment = "production") -> Target:
    return subject if isinstance(subject, Target) else pi_target(subject, environment)


def return_url(settings: Settings, target: Target) -> str:
    """Where Kapso sends the person back after setup (the app they came from)."""
    if target.app == "pi":
        base = settings.pi_app_public_url.rstrip("/")
        return f"{base}/settings/whatsapp/connected" if base else ""
    base = (settings.cors_origins[0] if settings.cors_origins else "").rstrip("/")
    return f"{base}/pi/whatsapp/connected" if base else ""


def _audit_scope(target: Target, scope: WorkspaceScope) -> WorkspaceScope:
    if target.account is not None:
        return env_scope(target.account, scope, target.environment)
    return scope


async def _refresh(session: AsyncSession, scope: WorkspaceScope | None, target: Target) -> None:
    if target.account is not None:
        await refresh_state(session, scope, target.account)


async def connection_for(
    session: AsyncSession, subject: Subject, environment: Environment = "production"
) -> PiProviderConnection:
    """The single provider record for one tenant environment (created on demand)."""
    target = _target(subject, environment)
    environment_id = target.environment_id
    row = await session.scalar(
        select(PiProviderConnection)
        .where(
            PiProviderConnection.tenant_id == target.tenant_id,
            PiProviderConnection.environment_id == environment_id,
        )
        .order_by(PiProviderConnection.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None:
        row = PiProviderConnection(
            tenant_id=target.tenant_id, environment_id=environment_id, provider="kapso"
        )
        session.add(row)
        await session.flush()
    return row


async def _ensure_customer(
    kapso: Kapso, subject: Subject, row: PiProviderConnection, environment: str
) -> str:
    if row.external_customer_id:
        return row.external_customer_id
    target = _target(subject, environment)  # type: ignore[arg-type]
    # Test and production numbers are separate Kapso customers so they never mix.
    suffix = "" if target.environment == "production" else f" ({target.environment})"
    row.external_customer_id = await kapso.create_customer(
        target.name + suffix, f"{target.tenant_id}:{target.environment}"
    )
    return row.external_customer_id


async def start_setup(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    subject: Subject,
    data: SetupRequest,
) -> PiProviderConnection:
    """Create (or refresh) the hosted setup link the business opens to authorize."""
    scope.require("pi.whatsapp.manage")
    target = _target(subject, data.environment)
    if target.account is not None:
        from app.modules.pi_saas.access_gate import require_whatsapp

        await require_whatsapp(session, settings, target.tenant_id)
    kapso = Kapso(settings, http)
    row = await connection_for(session, target)
    if row.status == "connected":
        raise Conflict("This WhatsApp number is already connected")
    customer_id = await _ensure_customer(kapso, target, row, target.environment)
    back = return_url(settings, target)
    if not back:
        raise BusinessRuleViolation(
            "PI_APP_NOT_CONFIGURED", "WhatsApp setup isn't available yet. Contact support.", 503
        )
    link = await kapso.create_setup_link(
        customer_id,
        success_url=f"{back}?environment={data.environment}",
        failure_url=f"{back}?environment={data.environment}&failed=1",
        connection_types=tuple(data.connection_types),
        language=target.language
        if target.language in {"en", "es", "pt", "hi", "id", "ar"}
        else None,
        reconnect_phone_number=row.display_phone_number if row.status == "disconnected" else None,
    )
    row.setup_link_id, row.setup_link_url = link.id, link.url
    row.setup_expires_at = _parse_time(link.expires_at)
    row.setup_status = (link.status or "pending")[:20]
    row.status = "setup_pending"
    row.last_error_code = None
    await record(
        session,
        "pi_saas.whatsapp_setup_started",
        scope=_audit_scope(target, scope),
        entity_type="pi_provider_connection",
        entity_id=row.id,
        details={"connection_types": data.connection_types},
    )
    await _refresh(session, scope, target)
    return row


async def request_number(
    session: AsyncSession, scope: WorkspaceScope, account: PiBusinessAccount, data: NumberRequest
) -> PiProviderConnection:
    """Record a request for a new number. Availability, monthly price and any deposit
    come from the provider/operator and must be confirmed by the business before any
    purchase; nothing is bought here."""
    scope.require("pi.whatsapp.manage")
    row = await connection_for(session, account, data.environment)
    row.number_request = {
        "country": data.country,
        "notes": data.notes,
        "status": "requested",
        "requested_at": datetime.now(UTC).isoformat(),
        "requested_by": str(scope.user_id),
        "quote": None,
        "customer_confirmed_at": None,
    }
    if row.status in {"draft", "disconnected"}:
        row.status = "setup_pending"
    await record(
        session,
        "pi_saas.number_requested",
        scope=env_scope(account, scope, data.environment),
        entity_type="pi_provider_connection",
        entity_id=row.id,
        details={"country": data.country},
    )
    await refresh_state(session, scope, account)
    return row


async def confirm_number_quote(
    session: AsyncSession,
    scope: WorkspaceScope,
    account: PiBusinessAccount,
    environment: Environment,
) -> PiProviderConnection:
    """The business explicitly accepts the quoted rental/deposit for a new number."""
    scope.require("pi.whatsapp.manage")
    scope.require("pi.billing.manage")
    row = await connection_for(session, account, environment)
    request = dict(row.number_request or {})
    if request.get("status") != "quoted" or not request.get("quote"):
        raise BusinessRuleViolation(
            "NO_QUOTE", "There is no price to confirm yet. We'll notify you when there is.", 409
        )
    request.update(status="confirmed", customer_confirmed_at=datetime.now(UTC).isoformat())
    request["confirmed_by"] = str(scope.user_id)
    row.number_request = request
    await record(
        session,
        "pi_saas.number_quote_confirmed",
        scope=env_scope(account, scope, environment),
        entity_type="pi_provider_connection",
        entity_id=row.id,
        details={"quote": request["quote"]},
    )
    return row


async def confirm_setup(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope | None,
    subject: Subject,
    environment: Environment,
    phone_number_id: str | None = None,
) -> PiProviderConnection:
    """Verify with the provider which numbers this business's customer record owns and
    link one. Called after the redirect and from webhook processing."""
    target = _target(subject, environment)
    row = await connection_for(session, target)
    if not row.external_customer_id:
        raise BusinessRuleViolation("SETUP_NOT_STARTED", "Start WhatsApp setup first", 409)
    numbers = await Kapso(settings, http).phone_numbers(row.external_customer_id)
    chosen = next(
        (n for n in numbers if phone_number_id is None or n.phone_number_id == phone_number_id),
        None,
    )
    if chosen is None:
        # Still processing on the provider side, or a forged/foreign number id.
        row.setup_status = "processing"
        return row
    await link_number(session, target, row, chosen)
    await _ensure_webhook_registered(settings, http, row, chosen.phone_number_id)
    await _refresh(session, scope, target)
    return row


async def _ensure_webhook_registered(
    settings: Settings, http: httpx.AsyncClient, row: PiProviderConnection, phone_number_id: str
) -> str:
    """Register (or confirm) the number's webhook and record whether it worked.

    A number can look "connected" while Kapso has nowhere to send its messages — the
    public URL or secret was missing, or the provider call failed — and nothing else
    ever retries it. Surface that as ``last_error_code`` so the operator sees it and
    ``check_health`` can self-heal it.
    """
    result = await register_webhook(settings, http, phone_number_id)
    row.last_error_code = None if result in {"created", "exists"} else "WEBHOOK_NOT_REGISTERED"
    return result


def webhook_url(settings: Settings) -> str:
    base = (settings.integrations_public_base_url or "").rstrip("/")
    return f"{base}/api/v1/webhooks/kapso" if base.startswith("https://") else ""


async def register_webhook(
    settings: Settings, http: httpx.AsyncClient, phone_number_id: str
) -> str:
    """Point the number's message events at us, so nobody has to set webhooks by hand in
    Kapso. Returns created / exists / skipped (no public URL or secret configured)."""
    url, secret = webhook_url(settings), settings.kapso_webhook_secret
    if not url or secret is None:
        return "skipped"
    try:
        return await Kapso(settings, http).ensure_webhook(
            phone_number_id, url, secret.get_secret_value()
        )
    except BusinessRuleViolation:
        return "failed"  # The number still works; the operator sees it in the numbers view.


async def link_number(
    session: AsyncSession,
    subject: Subject | None,
    row: PiProviderConnection,
    number: PhoneNumber,
) -> None:
    existing = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.provider == "kapso",
            WhatsAppConnection.phone_number_id == number.phone_number_id,
        )
    )
    if existing is not None and (
        existing.tenant_id != row.tenant_id or existing.environment_id != row.environment_id
    ):
        row.status, row.last_error_code = "action_required", "NUMBER_MAPPED_ELSEWHERE"
        await record(
            session,
            "pi_saas.number_conflict",
            tenant_id=row.tenant_id,
            environment_id=row.environment_id,
            entity_type="pi_provider_connection",
            entity_id=row.id,
            outcome="denied",
        )
        return
    # One active number per business environment for the shared inbox.
    other = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.tenant_id == row.tenant_id,
            WhatsAppConnection.environment_id == row.environment_id,
            WhatsAppConnection.phone_number_id != number.phone_number_id,
            WhatsAppConnection.status == "active",
        )
    )
    if other is not None:
        other.status = "disabled"
    if existing is None:
        existing = WhatsAppConnection(
            tenant_id=row.tenant_id,
            environment_id=row.environment_id,
            provider="kapso",
            phone_number_id=number.phone_number_id,
            display_phone_number=number.display_phone_number or number.phone_number_id,
            business_account_id=number.business_account_id,
            display_name=number.display_name,
            status="active",
            verified_at=datetime.now(UTC),
        )
        session.add(existing)
        await session.flush()
    else:
        existing.status = "active"
        existing.display_phone_number = number.display_phone_number or existing.display_phone_number
        existing.business_account_id = number.business_account_id or existing.business_account_id
    row.whatsapp_connection_id = existing.id
    row.phone_number_id = number.phone_number_id
    row.display_phone_number = number.display_phone_number
    row.business_account_id = number.business_account_id
    row.status, row.setup_status, row.last_error_code = "connected", "completed", None
    row.setup_link_url = None  # Single-use: never show a stale setup link again.
    await record(
        session,
        "pi_saas.whatsapp_connected",
        tenant_id=row.tenant_id,
        environment_id=row.environment_id,
        entity_type="pi_provider_connection",
        entity_id=row.id,
    )


async def disconnect(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    scope: WorkspaceScope,
    subject: Subject,
    environment: Environment,
    remove_from_provider: bool,
) -> PiProviderConnection:
    scope.require("pi.whatsapp.manage")
    target = _target(subject, environment)
    row = await connection_for(session, target)
    if row.whatsapp_connection_id is not None:
        connection = await session.get(WhatsAppConnection, row.whatsapp_connection_id)
        if connection is not None:
            connection.status = "disabled"
    if remove_from_provider and row.phone_number_id:
        await Kapso(settings, http).delete_number(row.phone_number_id)
    row.status = "disconnected"
    await record(
        session,
        "pi_saas.whatsapp_disconnected",
        scope=_audit_scope(target, scope),
        entity_type="pi_provider_connection",
        entity_id=row.id,
        details={"removed_from_provider": remove_from_provider},
    )
    from app.modules.pi_saas.number_pool import release_for

    await release_for(session, row)
    await _refresh(session, scope, target)
    return row


async def check_health(
    session: AsyncSession,
    settings: Settings,
    http: httpx.AsyncClient,
    subject: Subject,
    environment: Environment,
) -> PiProviderConnection:
    row = await connection_for(session, _target(subject, environment))
    if row.status != "connected" or not row.phone_number_id:
        return row
    row.health = await Kapso(settings, http).health(row.phone_number_id)
    row.health_checked_at = datetime.now(UTC)
    if row.last_error_code == "WEBHOOK_NOT_REGISTERED":
        await _ensure_webhook_registered(settings, http, row, row.phone_number_id)
    return row


async def retry_unregistered_webhooks(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient
) -> int:
    """Self-heal connections whose webhook never registered (e.g. a public URL or
    secret added after setup, or a transient provider failure). Called from the
    periodic sweep so nobody has to click "Check health" to fix it."""
    rows = list(
        await session.scalars(
            select(PiProviderConnection).where(
                PiProviderConnection.status == "connected",
                PiProviderConnection.last_error_code == "WEBHOOK_NOT_REGISTERED",
                PiProviderConnection.phone_number_id.is_not(None),
            )
        )
    )
    healed = 0
    for row in rows:
        assert row.phone_number_id is not None
        result = await _ensure_webhook_registered(settings, http, row, row.phone_number_id)
        if result in {"created", "exists"}:
            healed += 1
    return healed


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- webhook processing

MEDIA = frozenset({"audio", "image", "video"})
MESSAGE_EVENTS = {
    "whatsapp.message.received",
    "whatsapp.message.sent",
    "whatsapp.message.delivered",
    "whatsapp.message.read",
    "whatsapp.message.failed",
}
LIFECYCLE_EVENTS = {
    "whatsapp.phone_number.created",
    "whatsapp.phone_number.reconnected",
    "whatsapp.phone_number.deleted",
    "whatsapp.phone_number.offboarded",
    "whatsapp.phone_number.disconnected",
    "whatsapp.account.disabled",
    "whatsapp.account.restricted",
    "whatsapp.account.reinstated",
    "whatsapp.account.violation",
}


async def store_event(
    session: AsyncSession, idempotency_key: str, event_type: str, event: dict[str, Any]
) -> UUID | None:
    """Persist a verified provider event once. Returns the id of a *new* receipt."""
    key = (
        idempotency_key[:128]
        or hashlib.sha256(json.dumps(event, sort_keys=True, default=str).encode()).hexdigest()
    )
    return await session.scalar(
        insert(PiProviderEvent)
        .values(
            provider="kapso",
            idempotency_key=key,
            event_type=event_type[:80],
            payload=_redact(event),
        )
        .on_conflict_do_update(
            constraint="uq_pi_provider_events_key",
            set_={"duplicate_count": PiProviderEvent.duplicate_count + 1},
        )
        .returning(PiProviderEvent.id)
    )


def _interactive(message: dict[str, Any]) -> dict[str, Any]:
    """Bounded copy of an interactive reply: a form's answers or the tapped option."""
    interactive = as_dict(message.get("interactive"))
    kind = str(interactive.get("type") or "")[:20]
    if kind == "nfm_reply":
        reply = as_dict(interactive.get("nfm_reply"))
        answers = reply.get("response_json")
        kept = answers if isinstance(answers, str) and len(answers) <= 16384 else ""
        return {"type": kind, "nfm_reply": {"response_json": kept}}
    if kind in {"button_reply", "list_reply"}:
        choice = as_dict(interactive.get(kind))
        return {
            "type": kind,
            kind: {
                "id": str(choice.get("id") or "")[:200],
                "title": str(choice.get("title") or "")[:200],
            },
        }
    return {"type": kind}


def _redact(event: dict[str, Any]) -> dict[str, Any]:
    """Keep routing fields; message content is stored by the PI pipeline, not here."""
    message = as_dict(event.get("message"))
    customer = as_dict(event.get("customer"))
    return {
        "phone_number_id": str(event.get("phone_number_id") or "")[:32],
        "business_account_id": str(event.get("business_account_id") or "")[:32],
        "customer_id": str(customer.get("id") or "")[:120],
        "status": str(event.get("status") or "")[:32],
        "message": {
            "id": str(message.get("id") or "")[:160],
            "from": str(message.get("from") or "")[:20],
            "type": str(message.get("type") or "")[:20],
            "timestamp": str(message.get("timestamp") or "")[:16],
            "text": str(as_dict(message.get("text")).get("body") or "")[:4096],
            "caption": _media(message).get("caption", ""),
            "media_id": _media(message).get("id", ""),
            "filename": _media(message).get("filename", ""),
            "statuses": [
                {"status": str(s.get("status") or "")[:16]}
                for s in as_list(message.get("statuses"))[:10]
                if isinstance(s, dict)
            ],
            "kapso_status": str(as_dict(message.get("kapso")).get("status") or "")[:16],
            **_kapso_media(message),
            **({"interactive": _interactive(message)} if message.get("interactive") else {}),
        }
        if message
        else {},
        "profile_name": str(as_dict(event.get("conversation")).get("contact_name", ""))[:160],
    }


def _kapso_media(message: dict[str, Any]) -> dict[str, str]:
    """What Kapso already did for a media message: its own download URL, the file type
    and, for voice notes, a transcript. Saves downloading and re-transcribing."""
    kapso = as_dict(message.get("kapso"))
    data = as_dict(kapso.get("media_data"))
    url = str(kapso.get("media_url") or data.get("url") or "")
    out: dict[str, str] = {}
    if url.startswith("https://") and len(url) <= 1000:
        out["media_url"] = url
    mime = str(data.get("content_type") or "")
    if re.fullmatch(r"[a-z]+/[a-z0-9.+-]+(;.*)?", mime):
        out["media_mime"] = mime[:80]
    transcript = as_dict(kapso.get("transcript")).get("text")
    if isinstance(transcript, str) and transcript.strip():
        out["transcript"] = transcript.strip()[:4000]
    return out


def _media(message: dict[str, Any]) -> dict[str, str]:
    kind = str(message.get("type") or "")
    part = as_dict(message.get(kind))
    return {
        "id": str(part.get("id") or "")[:64],
        "caption": str(part.get("caption") or "")[:1024],
        "filename": str(part.get("filename") or "")[:200],
    }


async def process_event(
    session: AsyncSession, settings: Settings, http: httpx.AsyncClient, row: PiProviderEvent
) -> list[str]:
    """Apply one stored event. Returns PI webhook-event ids to enqueue for processing."""
    data = row.payload
    number = data.get("phone_number_id", "")
    if row.event_type in MESSAGE_EVENTS:
        return await _message_event(session, row, data, number)
    if row.event_type not in LIFECYCLE_EVENTS:
        row.status = "ignored"
        return []
    provider_row = None
    if data.get("customer_id"):
        provider_row = await session.scalar(
            select(PiProviderConnection).where(
                PiProviderConnection.provider == "kapso",
                PiProviderConnection.external_customer_id == data["customer_id"],
            )
        )
    if provider_row is None and PHONE_NUMBER_ID.fullmatch(number):
        provider_row = await session.scalar(
            select(PiProviderConnection).where(
                PiProviderConnection.provider == "kapso",
                PiProviderConnection.phone_number_id == number,
            )
        )
    if provider_row is None:
        row.status = "ignored"
        return []
    row.tenant_id, row.environment_id = provider_row.tenant_id, provider_row.environment_id
    provider_row.last_event_at = datetime.now(UTC)
    try:
        target = await workspace_target(
            session, provider_row.tenant_id, provider_row.environment_id
        )
    except BusinessRuleViolation:
        row.status = "ignored"
        return []
    account = target.account
    environment: Environment = "test" if target.environment == "test" else "production"
    if row.event_type in {"whatsapp.phone_number.created", "whatsapp.phone_number.reconnected"}:
        if provider_row.external_customer_id:
            await confirm_setup(
                session, settings, http, None, target, environment, number if number else None
            )
    elif row.event_type in {
        "whatsapp.phone_number.deleted",
        "whatsapp.phone_number.offboarded",
        "whatsapp.phone_number.disconnected",
        "whatsapp.account.disabled",
        "whatsapp.account.restricted",
        "whatsapp.account.violation",
    }:
        disconnected = row.event_type.startswith("whatsapp.phone_number.")
        provider_row.status = "disconnected" if disconnected else "action_required"
        provider_row.last_error_code = row.event_type.rsplit(".", 1)[-1].upper()[:64]
        if disconnected and provider_row.whatsapp_connection_id:
            connection = await session.get(WhatsAppConnection, provider_row.whatsapp_connection_id)
            if connection is not None:
                connection.status = "disabled"
        scope = WorkspaceScope.system(
            provider_row.tenant_id, provider_row.environment_id, frozenset(), "Pi"
        )
        await notify(
            session,
            scope,
            "pi.whatsapp_attention",
            "Your WhatsApp number needs attention",
            "Pi has stopped replying on this number until it is reconnected.",
            link="/settings/whatsapp" if account is not None else "/pi/whatsapp",
            permission="pi.whatsapp.manage",
            dedupe_key=f"pi-wa:{provider_row.id}:{row.event_type}",
        )
        await _refresh(session, None, target)
    elif row.event_type == "whatsapp.account.reinstated":
        if provider_row.status == "action_required" and provider_row.whatsapp_connection_id:
            provider_row.status = "connected"
            provider_row.last_error_code = None
        await _refresh(session, None, target)
    row.status = "processed"
    return []


async def _message_event(
    session: AsyncSession, row: PiProviderEvent, data: dict[str, Any], number: str
) -> list[str]:
    connection = await session.scalar(
        select(WhatsAppConnection).where(
            WhatsAppConnection.provider == "kapso",
            WhatsAppConnection.phone_number_id == number,
            WhatsAppConnection.status == "active",
        )
    )
    message = data.get("message") or {}
    mid = str(message.get("id", ""))
    if connection is None or not mid:
        row.status = "ignored"
        return []
    row.tenant_id, row.environment_id = connection.tenant_id, connection.environment_id
    if row.event_type == "whatsapp.message.received":
        if not re.fullmatch(r"[0-9]{6,15}", str(message.get("from", ""))):
            row.status = "ignored"
            return []
        kind = message.get("type") or "text"
        text, form = None, None
        if kind == "interactive":
            from app.modules.pi_saas.flows import interactive_reply

            kind, text, form = interactive_reply(message)
        # A document (PDF, Word…) is stored as "other" but keeps its file for pi to read.
        document = kind == "document"
        kind = kind if kind in {"text", "interactive", *MEDIA} else "other"
        has_file = kind in MEDIA or document
        payload = {
            "key": f"{number}:{mid}",
            "kind": "message",
            "number": number,
            "message_id": mid,
            "sender": message.get("from", ""),
            "profile": data.get("profile_name") or None,
            "message_type": kind,
            "body": text
            if text is not None
            else message.get("text")
            if kind == "text"
            else message.get("caption", ""),
            "form": form,
            "media_id": message.get("media_id") or None if has_file else None,
            **(
                {k: message[k] for k in ("media_url", "media_mime", "transcript") if message.get(k)}
                if has_file
                else {}
            ),
            **(
                {"file_kind": "document", "filename": str(message.get("filename") or "")[:200]}
                if document
                else {}
            ),
        }
    else:
        state = row.event_type.rsplit(".", 1)[-1]
        payload = {
            "key": f"{number}:{mid}:{state}",
            "kind": "status",
            "number": number,
            "message_id": mid,
            "state": state,
        }
    event_id = await session.scalar(
        insert(WhatsAppWebhookEvent)
        .values(
            tenant_id=connection.tenant_id,
            environment_id=connection.environment_id,
            provider="kapso",
            connection_id=connection.id,
            phone_number_id=number,
            event_key=hashlib.sha256(payload["key"].encode()).hexdigest(),
            kind=payload["kind"],
            payload=payload,
        )
        .on_conflict_do_update(
            constraint="uq_whatsapp_webhook_events_key",
            set_={"duplicate_count": WhatsAppWebhookEvent.duplicate_count + 1},
        )
        .returning(WhatsAppWebhookEvent.id)
    )
    connection.last_inbound_at = datetime.now(UTC)
    row.status = "processed"
    return [str(event_id)] if event_id else []
