"""Platform settings the operator manages from the dashboard.

Every key the platform needs is listed in ``KEYS``: what it is for, where to get it and
whether it is set. An operator owner can save a value in the dashboard; it is stored in
``pi_platform_settings`` (secrets Fernet-encrypted with SECRETS_ENCRYPTION_KEY) and
overrides the server's .env. Deleting it brings the .env value back.

How values take effect: the saved values are applied onto the running ``Settings``
object (the one shared as ``app.state.settings``/``ctx["settings"]``), so every module
sees them without code changes. Other processes (workers, more API servers) notice a
change through a version number in ``pi_platform_state`` and reload.

Some keys can never live in the database, because the database needs them first
(DATABASE_URL, REDIS_URL, SECRETS_ENCRYPTION_KEY). They are listed as "server only".
Secret values are never returned, logged or audited; only a hint (last four).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import SecretStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.probe import probe
from app.core.config import Settings
from app.integrations.crypto import CredentialManager, hint
from app.modules.pi_saas.models import PiPlatformSetting, PiPlatformState
from app.shared.errors import BusinessRuleViolation, ResourceNotFound

logger = logging.getLogger("platform")
VERSION_KEY = "platform_config"
Kind = Literal["secret", "text", "url", "choice", "number", "bool", "models", "list"]


@dataclass(frozen=True)
class Key:
    name: str  # the .env name
    group: str
    label: str
    kind: Kind
    purpose: str
    where: str = ""
    required: bool = False
    choices: tuple[str, ...] = ()
    test: str | None = None  # which connection test covers it
    server_only: bool = False
    placeholder: str = ""

    @property
    def field(self) -> str:
        return self.name.lower()


GROUPS = (
    ("whatsapp", "WhatsApp (Kapso)"),
    ("addresses", "Public addresses"),
    ("ai", "AI providers and models"),
    ("payments", "Subscription payments (Stripe)"),
    ("email", "Platform email"),
    ("google", "Google Calendar app"),
    ("shopify", "Shopify app"),
    ("meta", "Meta WhatsApp app (advanced)"),
    ("signup", "Sign-up and trial"),
    ("server", "Server only"),
)
PROVIDERS = ("", "anthropic", "openai", "gemini", "groq")

KEYS: tuple[Key, ...] = (
    Key(
        "KAPSO_API_KEY",
        "whatsapp",
        "Kapso project API key",
        "secret",
        "Connects every WhatsApp number, fills the number pool, sends messages.",
        "Kapso dashboard → Project settings → API keys.",
        required=True,
        test="kapso",
    ),
    Key(
        "KAPSO_WEBHOOK_SECRET",
        "whatsapp",
        "Kapso webhook secret",
        "secret",
        "Proves incoming WhatsApp messages really come from Kapso. Choose any long random "
        "value; Pi registers it on each number's webhook for you.",
        "Generate one (40+ random characters).",
        required=True,
    ),
    Key(
        "KAPSO_META_BILLING_MODE",
        "whatsapp",
        "Who pays Meta message fees",
        "choice",
        "partner_managed: the platform's Kapso credits pay (recovered through Pi plans). "
        "customer_managed: each business adds its own card in Meta.",
        choices=("partner_managed", "customer_managed"),
    ),
    Key(
        "KAPSO_POOL_CUSTOMER_NAME",
        "whatsapp",
        "Number pool name in Kapso",
        "text",
        "The Kapso customer that holds the numbers you give to businesses.",
    ),
    Key(
        "INTEGRATIONS_PUBLIC_BASE_URL",
        "addresses",
        "Public API address",
        "url",
        "The https:// address Kapso, Stripe and others use to reach this API (webhooks).",
        "Your API domain, e.g. https://api.example.com.",
        required=True,
        placeholder="https://api.example.com",
    ),
    Key(
        "PI_APP_PUBLIC_URL",
        "addresses",
        "Pi app address",
        "url",
        "Where businesses open the Pi app; used in emails and setup return links.",
        required=True,
        placeholder="https://app.example.com",
    ),
    Key(
        "OAUTH_REDIRECT_BASE_URL",
        "addresses",
        "OAuth return address",
        "url",
        "Base of the Google/Shopify return URL registered in their consoles.",
        placeholder="https://api.example.com",
    ),
    Key(
        "PRIMARY_LLM_PROVIDER",
        "ai",
        "Main AI provider",
        "choice",
        "Answers customers first.",
        choices=PROVIDERS,
        required=True,
    ),
    Key(
        "FALLBACK_LLM_PROVIDER",
        "ai",
        "Backup AI provider",
        "choice",
        "Used when the main provider is down or rate limited.",
        choices=PROVIDERS,
    ),
    Key(
        "SECONDARY_FALLBACK_LLM_PROVIDER",
        "ai",
        "Second backup AI provider",
        "choice",
        "Last resort.",
        choices=PROVIDERS,
    ),
    Key(
        "ANTHROPIC_API_KEY",
        "ai",
        "Anthropic (Claude) API key",
        "secret",
        "Claude models for replies, routing and summaries.",
        "console.anthropic.com → API keys.",
        test="anthropic",
    ),
    Key(
        "OPENAI_API_KEY",
        "ai",
        "OpenAI API key",
        "secret",
        "GPT models, embeddings (search) and voice-note transcription.",
        "platform.openai.com → API keys.",
        test="openai",
    ),
    Key(
        "GEMINI_API_KEY",
        "ai",
        "Google Gemini API key",
        "secret",
        "Gemini models, embeddings, video and voice notes.",
        "aistudio.google.com → Get API key.",
        test="gemini",
    ),
    Key(
        "GROQ_API_KEY",
        "ai",
        "Groq API key",
        "secret",
        "Fast, low-cost open models; good as a backup.",
        "console.groq.com → API keys.",
        test="groq",
    ),
    Key(
        "ANTHROPIC_MODELS",
        "ai",
        "Claude models",
        "models",
        "Model per job. Empty uses the recommended defaults.",
    ),
    Key("OPENAI_MODELS", "ai", "OpenAI models", "models", "Model per job."),
    Key("GEMINI_MODELS", "ai", "Gemini models", "models", "Model per job."),
    Key("GROQ_MODELS", "ai", "Groq models", "models", "Model per job."),
    Key(
        "AI_FAILOVER_ALL_CONFIGURED",
        "ai",
        "Try every configured provider",
        "bool",
        "After the main and backup providers, also use any other provider that has a key, "
        "so customers still get answers when credits run out.",
    ),
    Key(
        "LLM_CIRCUIT_QUOTA_COOLDOWN_SECONDS",
        "ai",
        "Pause a provider with no credits (seconds)",
        "number",
        "When a key is refused or its credits/quota are finished, that provider is skipped "
        "this long (default 600). Saving a new key or a passing test ends the pause.",
    ),
    Key(
        "AI_TENANT_DAILY_TOKEN_LIMIT",
        "ai",
        "Daily AI tokens per business",
        "number",
        "Stops runaway AI use for one business. Empty = no limit.",
    ),
    Key(
        "AI_TENANT_DAILY_COST_LIMIT",
        "ai",
        "Daily AI cost per business (USD)",
        "number",
        "Empty = no limit.",
    ),
    Key(
        "PI_BILLING_STRIPE_SECRET_KEY",
        "payments",
        "Stripe secret key",
        "secret",
        "Card payments for Pi plans. Bank transfer and cash work without it.",
        "dashboard.stripe.com → Developers → API keys (use a restricted key).",
        test="stripe",
    ),
    Key(
        "PI_BILLING_STRIPE_WEBHOOK_SECRET",
        "payments",
        "Stripe webhook signing secret",
        "secret",
        "Confirms payments; add the endpoint /api/v1/webhooks/pi-billing/stripe in Stripe.",
        "Stripe → Developers → Webhooks → Signing secret (whsec_…).",
    ),
    Key(
        "PLATFORM_SMTP_HOST",
        "email",
        "SMTP server",
        "text",
        "Sends verification, payment and account emails to businesses.",
        "Your email provider (e.g. smtp.gmail.com, smtp.resend.com).",
        required=True,
        test="smtp",
    ),
    Key("PLATFORM_SMTP_PORT", "email", "SMTP port", "number", "Usually 587 (STARTTLS)."),
    Key("PLATFORM_SMTP_USERNAME", "email", "SMTP username", "text", "Login for the server."),
    Key("PLATFORM_SMTP_PASSWORD", "email", "SMTP password", "secret", "App password or key."),
    Key(
        "PLATFORM_SMTP_FROM",
        "email",
        "From address",
        "text",
        "e.g. Pi <hello@example.com>.",
        required=True,
    ),
    Key(
        "PLATFORM_SMTP_SECURITY",
        "email",
        "Connection security",
        "choice",
        "starttls for 587, ssl for 465.",
        choices=("starttls", "ssl", "none"),
    ),
    Key(
        "GOOGLE_OAUTH_CLIENT_ID",
        "google",
        "Google OAuth client ID",
        "text",
        "Lets businesses connect Google Calendar for bookings.",
        "console.cloud.google.com → APIs & Services → Credentials.",
    ),
    Key("GOOGLE_OAUTH_CLIENT_SECRET", "google", "Google OAuth client secret", "secret", ""),
    Key(
        "SHOPIFY_CLIENT_ID",
        "shopify",
        "Shopify app client ID",
        "text",
        "Lets stores connect Shopify products and orders.",
        "Shopify Dev Dashboard → your app → Settings.",
    ),
    Key("SHOPIFY_CLIENT_SECRET", "shopify", "Shopify app client secret", "secret", ""),
    Key(
        "WHATSAPP_APP_SECRET",
        "meta",
        "Meta app secret",
        "secret",
        "Only for workspaces that connect Meta directly instead of Kapso.",
        "developers.facebook.com → your app → Settings → Basic.",
    ),
    Key(
        "WHATSAPP_VERIFY_TOKEN",
        "meta",
        "Meta webhook verify token",
        "secret",
        "Only for direct Meta connections.",
    ),
    Key(
        "PI_TRIAL_PLAN",
        "signup",
        "Plan new businesses start on",
        "text",
        "The plan key a new business gets (as a trial).",
    ),
    Key(
        "PI_ALLOW_REGISTRATION",
        "signup",
        "Allow new businesses to sign up",
        "bool",
        "Turn off to accept only businesses you invite.",
    ),
    Key(
        "SECRETS_ENCRYPTION_KEY",
        "server",
        "Encryption key",
        "secret",
        "Encrypts every stored secret, including the keys on this page.",
        'Generate with: python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())"',
        required=True,
        server_only=True,
    ),
    Key("DATABASE_URL", "server", "Database", "secret", "PostgreSQL.", server_only=True),
    Key("REDIS_URL", "server", "Redis", "secret", "Rate limits and jobs.", server_only=True),
    Key(
        "JOB_QUEUE_MODE",
        "server",
        "Background jobs",
        "text",
        "arq (workers) in production.",
        server_only=True,
    ),
)
BY_NAME = {k.name: k for k in KEYS}


# ------------------------------------------------------------------ overlay state


@dataclass
class _State:
    env: dict[str, Any] = field(default_factory=dict)  # the .env value of each key
    version: int = -1
    checked: float = 0.0
    saved: set[str] = field(default_factory=set)


_states: dict[int, _State] = {}


def _state(settings: Settings) -> _State:
    state = _states.get(id(settings))
    if state is None:
        state = _State(env={k.field: getattr(settings, k.field, None) for k in KEYS})
        _states[id(settings)] = state
    return state


def _adapter(key: Key) -> TypeAdapter[Any]:
    return TypeAdapter(Settings.model_fields[key.field].annotation)


def parse(key: Key, raw: Any) -> Any:
    """Validate a value the way the .env loader would, or raise a clear error."""
    if key.kind == "number" and isinstance(raw, str):
        raw = raw.strip() or None
    if key.kind == "list" and isinstance(raw, str):
        raw = [p.strip() for p in raw.split(",") if p.strip()]
    if key.kind == "url" and isinstance(raw, str):
        raw = raw.strip().rstrip("/")
        if raw and not raw.startswith(("https://", "http://")):
            raise BusinessRuleViolation("INVALID_VALUE", f"{key.label} must start with https://")
    if key.kind == "choice" and raw not in key.choices:
        raise BusinessRuleViolation("INVALID_VALUE", f"Choose one of: {', '.join(key.choices)}")
    if key.kind == "models":
        if not isinstance(raw, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) <= 120 for k, v in raw.items()
        ):
            raise BusinessRuleViolation("INVALID_VALUE", "Models must map each job to a model id")
        raw = {k: v.strip() for k, v in raw.items() if v.strip()}
    try:
        return _adapter(key).validate_python(raw)
    except ValidationError:
        raise BusinessRuleViolation("INVALID_VALUE", f"{key.label} isn't valid") from None


def _is_set(value: Any) -> bool:
    if isinstance(value, SecretStr):
        return bool(value.get_secret_value())
    return value not in (None, "", {}, [])


async def _version(session: AsyncSession) -> int:
    row = await session.get(PiPlatformState, VERSION_KEY)
    return int(row.value.get("version", 0)) if row is not None else 0


async def apply(session: AsyncSession, settings: Settings) -> None:
    """Put the saved values onto ``settings`` (and restore .env values of removed ones)."""
    state = _state(settings)
    crypto = CredentialManager(settings)
    rows = {r.key: r for r in await session.scalars(select(PiPlatformSetting))}
    saved: set[str] = set()
    for key in KEYS:
        if key.server_only:
            continue
        row = rows.get(key.name)
        value = state.env.get(key.field)
        if row is not None:
            try:
                raw = crypto.decrypt(row.value_encrypted) if row.value_encrypted else row.value
                value = parse(key, raw)
                saved.add(key.name)
            except Exception:  # noqa: BLE001 - a bad row never takes the platform down
                logger.warning("platform_setting_unreadable", extra={"key": key.name})
                value = state.env.get(key.field)
        setattr(settings, key.field, value)
    state.saved = saved
    state.version = await _version(session)
    state.checked = time.monotonic()


async def refresh(session: AsyncSession, settings: Settings, *, max_age: float = 15) -> bool:
    """Reload when another process changed a setting (checked at most every ``max_age``)."""
    state = _state(settings)
    if time.monotonic() - state.checked < max_age:
        return False
    state.checked = time.monotonic()
    if await _version(session) == state.version:
        return False
    await apply(session, settings)
    return True


async def _bump(session: AsyncSession) -> None:
    row = await session.get(PiPlatformState, VERSION_KEY, with_for_update=True)
    if row is None:
        session.add(PiPlatformState(key=VERSION_KEY, value={"version": 1}))
    else:
        row.value = {"version": int(row.value.get("version", 0)) + 1}
    await session.flush()


# ------------------------------------------------------------------ views and changes


def listing(settings: Settings) -> dict[str, Any]:
    state = _state(settings)
    items = []
    for key in KEYS:
        current = getattr(settings, key.field, None)
        is_set = _is_set(current)
        source = "dashboard" if key.name in state.saved else ("env" if is_set else None)
        item: dict[str, Any] = {
            "key": key.name,
            "group": key.group,
            "label": key.label,
            "kind": key.kind,
            "purpose": key.purpose,
            "where": key.where,
            "required": key.required,
            "choices": list(key.choices),
            "placeholder": key.placeholder,
            "server_only": key.server_only,
            "testable": key.test is not None,
            "set": is_set,
            "source": source,
            "env_set": _is_set(state.env.get(key.field)),
        }
        if key.kind == "secret":
            item["hint"] = (
                hint(current.get_secret_value()) if isinstance(current, SecretStr) else ""
            )
        elif not key.server_only:
            item["value"] = current
        items.append(item)
    missing = [i["key"] for i in items if i["required"] and not i["set"]]
    return {
        "groups": [{"key": g, "label": label} for g, label in GROUPS],
        "items": items,
        "missing_required": missing,
        "encryption_ready": CredentialManager(settings).configured,
    }


def env_template(settings: Settings, *, only_missing: bool = True) -> str:
    """A .env block for the keys that aren't set anywhere yet (no values)."""
    lines = ["# Pi platform settings missing on this server", ""]
    for group, label in GROUPS:
        keys = [
            k
            for k in KEYS
            if k.group == group and (not only_missing or not _is_set(getattr(settings, k.field)))
        ]
        if not keys:
            continue
        lines.append(f"# {label}")
        for key in keys:
            if key.where:
                lines.append(f"# {key.label}: {key.where}")
            lines.append(f"{key.name}=")
        lines.append("")
    return "\n".join(lines)


def _key(name: str) -> Key:
    key = BY_NAME.get(name.upper())
    if key is None:
        raise ResourceNotFound
    if key.server_only:
        raise BusinessRuleViolation(
            "SERVER_ONLY", "This value must stay in the server's .env (the database needs it)."
        )
    return key


async def save(session: AsyncSession, settings: Settings, name: str, raw: Any, user_id: Any) -> Key:
    key = _key(name)
    if key.kind == "secret":
        if not isinstance(raw, str) or len(raw.strip()) < 8:
            raise BusinessRuleViolation("INVALID_VALUE", "Paste the full value")
        raw = raw.strip()
    value = parse(key, raw)
    row = await session.get(PiPlatformSetting, key.name, with_for_update=True)
    if row is None:
        row = PiPlatformSetting(key=key.name)
        session.add(row)
    if key.kind == "secret":
        row.value_encrypted = CredentialManager(settings).encrypt(raw)  # 503 without a key
        row.value, row.hint = None, hint(raw)
    else:
        row.value_encrypted, row.hint = None, ""
        row.value = _adapter(key).dump_python(value, mode="json")
    row.updated_by_user_id = user_id
    await _bump(session)
    await apply(session, settings)
    return key


async def remove(session: AsyncSession, settings: Settings, name: str) -> Key:
    key = _key(name)
    row = await session.get(PiPlatformSetting, key.name, with_for_update=True)
    if row is not None:
        await session.delete(row)
        await _bump(session)
    await apply(session, settings)
    return key


# ------------------------------------------------------------------ connection tests


async def test(settings: Settings, http: httpx.AsyncClient, name: str) -> dict[str, Any]:
    """Check one key against its service. Never returns provider messages or secrets."""
    key = _key(name)
    if key.test is None:
        raise BusinessRuleViolation("NOT_TESTABLE", "This setting has no connection test")
    if not _is_set(getattr(settings, key.field)):
        return {"ok": False, "message": "Not set yet"}
    try:
        result: dict[str, Any] = await TESTS[key.test](settings, http)
    except httpx.HTTPError:
        return {"ok": False, "message": "Couldn't reach the service"}
    except BusinessRuleViolation as exc:
        return {"ok": False, "message": exc.message}
    except Exception as exc:  # noqa: BLE001 - reported as a failed test, never raised
        return {"ok": False, "message": f"Failed ({getattr(exc, 'code', type(exc).__name__)})"}
    return result


def _secret(value: SecretStr | None) -> str:
    return value.get_secret_value() if value is not None else ""


def _result(response: httpx.Response, good: str = "Connected") -> dict[str, Any]:
    if response.status_code < 300:
        return {"ok": True, "message": good}
    if response.status_code in (401, 403):
        return {"ok": False, "message": "The key was refused. Check it and save again."}
    return {"ok": False, "message": f"The service answered {response.status_code}"}


async def _kapso(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    from app.modules.pi_saas.kapso import Kapso

    numbers = await Kapso(settings, http).list_numbers(max_pages=1)
    return {"ok": True, "message": f"Connected · {len(numbers)} number(s) in the project"}


# AI keys: a real one-word completion per chosen model (app.ai.probe). A models list
# passes even with zero credits, which is exactly the failure operators need to see.
async def _anthropic(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    return await probe(settings, http, "anthropic")


async def _openai(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    return await probe(settings, http, "openai")


async def _groq(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    return await probe(settings, http, "groq")


async def _gemini(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    return await probe(settings, http, "gemini")


async def _stripe(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    return _result(
        await http.get(
            f"{settings.stripe_api_base_url.rstrip('/')}/v1/balance",
            headers={"Authorization": f"Bearer {_secret(settings.pi_billing_stripe_secret_key)}"},
            timeout=10,
        )
    )


async def _smtp(settings: Settings, http: httpx.AsyncClient) -> dict[str, Any]:
    import asyncio
    import smtplib
    import ssl

    from app.integrations.providers.smtp import check_smtp_host

    host = (settings.platform_smtp_host or "").strip().lower()
    port, security = settings.platform_smtp_port, settings.platform_smtp_security
    timeout = settings.platform_smtp_timeout_seconds
    await check_smtp_host(host, port, settings)

    def work() -> None:
        context = ssl.create_default_context()
        client = (
            smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
            if security == "ssl"
            else smtplib.SMTP(host, port, timeout=timeout)
        )
        try:
            client.ehlo()
            if security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            if settings.platform_smtp_username:
                client.login(
                    settings.platform_smtp_username, _secret(settings.platform_smtp_password)
                )
        finally:
            try:
                client.quit()
            except smtplib.SMTPException:
                client.close()

    try:
        async with asyncio.timeout(timeout * 3):
            await asyncio.to_thread(work)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "message": "The username or password was refused"}
    except (smtplib.SMTPException, OSError, TimeoutError):
        return {"ok": False, "message": "Couldn't connect to the SMTP server"}
    return {"ok": True, "message": "Signed in to the SMTP server"}


TESTS: dict[str, Any] = {
    "kapso": _kapso,
    "anthropic": _anthropic,
    "openai": _openai,
    "gemini": _gemini,
    "groq": _groq,
    "stripe": _stripe,
    "smtp": _smtp,
}
