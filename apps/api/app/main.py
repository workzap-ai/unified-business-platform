import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings, get_settings
from app.core.database import create_engine
from app.core.exceptions import install_handlers
from app.core.jobs import InlineQueue, create_queue
from app.core.logging import configure_logging
from app.core.middleware import OriginCheckMiddleware, RequestContextMiddleware
from app.health import router
from app.integrations.http_errors import install_integration_handlers
from app.modules.access.routes import router as access_router
from app.modules.audit.routes import router as audit_router
from app.modules.auth.mfa import pi_router as pi_mfa_router
from app.modules.auth.mfa import router as mfa_router
from app.modules.auth.passkeys import pi_router as pi_passkeys_router
from app.modules.auth.passkeys import router as passkeys_router
from app.modules.auth.routes import router as auth_router
from app.modules.billing.receipts import router as receipts_router
from app.modules.billing.routes import router as billing_router
from app.modules.business_settings.routes import router as business_settings_router
from app.modules.catalog.routes import router as catalog_router
from app.modules.customers.file_routes import router as customer_files_router
from app.modules.customers.routes import router as customers_router
from app.modules.environments.routes import router as environments_router
from app.modules.finance.routes import router as finance_router
from app.modules.hr.onboarding_routes import public_router as onboarding_public_router
from app.modules.hr.onboarding_routes import router as onboarding_router
from app.modules.hr.routes import router as hr_router
from app.modules.integrations.routes import router as integrations_router
from app.modules.integrations.webhook_routes import PublicWebhookOriginExemption
from app.modules.integrations.webhook_routes import router as integration_webhook_router
from app.modules.integrations.workflow_routes import router as integration_workflow_router
from app.modules.inventory.routes import router as inventory_router
from app.modules.navigation.routes import router as navigation_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.orders.routes import router as orders_router
from app.modules.pi.analytics import router as pi_analytics_router
from app.modules.pi.config_routes import router as pi_config_router
from app.modules.pi.inbox_routes import router as pi_inbox_router
from app.modules.pi.kapso_routes import router as pi_kapso_router
from app.modules.pi.read_routes import router as pi_read_router
from app.modules.pi.routes import router as pi_router
from app.modules.pi.routes import webhook_router
from app.modules.pi_customer.routes import router as pi_customer_router
from app.modules.pi_customer.second_step import router as pi_customer_second_step_router
from app.modules.pi_saas.app_routes import router as pi_app_router
from app.modules.pi_saas.assistant_routes import operator_router as pi_operator_help_router
from app.modules.pi_saas.assistant_routes import router as pi_assistant_router
from app.modules.pi_saas.campaign_routes import router as pi_campaign_router
from app.modules.pi_saas.connector_routes import router as pi_connector_router
from app.modules.pi_saas.connector_routes import web_router as pi_connector_web_router
from app.modules.pi_saas.customer_payment_routes import public_router as pi_customer_pay_link_router
from app.modules.pi_saas.customer_payment_routes import router as pi_customer_payment_router
from app.modules.pi_saas.deal_routes import public_router as pi_documents_router
from app.modules.pi_saas.deal_routes import router as pi_deals_router
from app.modules.pi_saas.digest_routes import operator_router as pi_operator_digest_router
from app.modules.pi_saas.digest_routes import router as pi_digest_router
from app.modules.pi_saas.insights_routes import router as pi_insights_router
from app.modules.pi_saas.operator_number_routes import router as pi_operator_number_router
from app.modules.pi_saas.operator_routes import router as pi_operator_router
from app.modules.pi_saas.operator_system_routes import router as pi_operator_system_router
from app.modules.pi_saas.operator_workspace_routes import router as operator_workspace_router
from app.modules.pi_saas.payment_link import router as payment_link_router
from app.modules.pi_saas.payment_routes import client_router as pi_payment_router
from app.modules.pi_saas.payment_routes import operator_router as pi_payment_operator_router
from app.modules.pi_saas.payment_routes import public_router as pi_pay_link_router
from app.modules.pi_saas.platform_config_routes import router as pi_platform_config_router
from app.modules.pi_saas.problems_routes import router as pi_problems_router
from app.modules.pi_saas.requests import router as pi_requests_router
from app.modules.pi_saas.review_routes import operator_router as pi_operator_review_router
from app.modules.pi_saas.review_routes import router as pi_review_router
from app.modules.pi_saas.setup_routes import operator_router as pi_operator_setup_router
from app.modules.pi_saas.setup_routes import router as pi_setup_router
from app.modules.pi_saas.setup_routes import web_router as setup_web_router
from app.modules.pi_saas.webhook_routes import router as pi_saas_webhook_router
from app.modules.pi_saas.whatsapp_tools import router as pi_whatsapp_tools_router
from app.modules.pi_saas.work_routes import router as pi_work_router
from app.modules.products.routes import router as products_router
from app.modules.quotes.routes import router as quotes_router
from app.modules.reports.routes import router as reports_router
from app.modules.sales.routes import router as sales_router
from app.modules.tenants.organization_routes import router as organization_router
from app.modules.tenants.routes import router as tenant_router
from app.modules.workspace_agent.routes import router as workspace_agent_router
from app.workflows.routes import router as workflows_router

ROUTERS = [
    workspace_agent_router,
    pi_payment_operator_router,
    pi_inbox_router,
    pi_work_router,
    pi_customer_payment_router,
    pi_deals_router,
    payment_link_router,
    customer_files_router,
    pi_requests_router,
    receipts_router,
    pi_operator_router,
    pi_operator_digest_router,
    pi_operator_number_router,
    pi_operator_system_router,
    pi_platform_config_router,
    pi_operator_review_router,
    pi_kapso_router,
    pi_connector_web_router,
    setup_web_router,
    pi_whatsapp_tools_router,
    pi_operator_setup_router,
    operator_workspace_router,
    pi_operator_help_router,
    pi_saas_webhook_router,
    pi_read_router,
    pi_analytics_router,
    pi_config_router,
    pi_router,
    webhook_router,
    workflows_router,
    router,
    auth_router,
    passkeys_router,
    mfa_router,
    tenant_router,
    organization_router,
    environments_router,
    access_router,
    navigation_router,
    products_router,
    notifications_router,
    audit_router,
    business_settings_router,
    reports_router,
    customers_router,
    catalog_router,
    inventory_router,
    sales_router,
    quotes_router,
    orders_router,
    billing_router,
    finance_router,
    hr_router,
    onboarding_router,
    onboarding_public_router,
    integrations_router,
    integration_workflow_router,
    # Public, signature-authenticated: /webhooks/{integration_key}/{endpoint_token}.
    integration_webhook_router,
    # PI API routers are added with the PI backend phase (schema exists in 0002).
]

# The standalone Pi app: its own routes plus the shared PI routers under /api/v1/pi-app.
# Only Pi app sessions are accepted there (see app/core/audience.py); Owner OS routes
# such as members, reports or finance are deliberately not mounted for that audience.
PI_APP_ROUTERS = [
    pi_payment_router,
    # Public, token-authenticated pay-by-link/QR (no session): /pay/{token}...
    # (PiManualPayment) and /pay/request/{token}... (PiPaymentRequest) — the token
    # itself is the credential.
    pi_pay_link_router,
    pi_customer_pay_link_router,
    pi_app_router,
    pi_read_router,
    pi_analytics_router,
    pi_config_router,
    pi_router,
    pi_inbox_router,
    pi_work_router,
    pi_customer_payment_router,
    pi_deals_router,
    payment_link_router,
    customer_files_router,
    pi_requests_router,
    receipts_router,
    pi_documents_router,
    # The deal flow in the pi app: leads, proposals and orders (core modules, pi session).
    sales_router,
    quotes_router,
    orders_router,
    # Business-owned Google Calendar / Shopify connections (Pi app only).
    pi_connector_router,
    pi_campaign_router,
    pi_digest_router,
    pi_insights_router,
    pi_problems_router,
    # Pi Assistant: in-app help and the business's own numbers, by role.
    pi_assistant_router,
    pi_setup_router,
    pi_review_router,
    pi_whatsapp_tools_router,
    notifications_router,
    # Core invoicing for the business's own customers (billing.read / billing.write).
    billing_router,
    # PI Customer: end customers see their own conversations (signed customer cookie,
    # never a business session): /customer-portal/...
    pi_customer_router,
    pi_customer_second_step_router,
    pi_passkeys_router,
    pi_mfa_router,
]


async def _platform_config_loop(app: FastAPI) -> None:
    """Apply operator-saved platform keys at start-up, then pick up changes made by other
    processes (see pi_saas.platform_config)."""
    from app.modules.pi_saas import platform_config

    first = True
    while True:
        try:
            async with app.state.sessions() as session:
                if first:
                    await platform_config.apply(session, app.state.settings)
                    first = False
                else:
                    await platform_config.refresh(session, app.state.settings)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - .env values keep working
            logging.getLogger("platform").warning("platform_config_load_failed")
        await asyncio.sleep(15)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.log_level)
        engine = create_engine(config)
        redis = Redis.from_url(
            config.redis_url.get_secret_value(),
            socket_timeout=config.dependency_timeout_seconds,
            socket_connect_timeout=config.dependency_timeout_seconds,
            max_connections=20,
        )
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=50),
            verify=config.outbound_verify_tls,
        ) as client:
            app.state.settings = config
            app.state.engine = engine
            app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
            app.state.redis = redis
            app.state.http = client
            app.state.queue = create_queue(config, app.state.sessions, client)
            config_task = None
            if config.app_env != "test":
                config_task = asyncio.create_task(_platform_config_loop(app))
            if (
                isinstance(app.state.queue, InlineQueue)
                and config.app_env != "test"
                and config.integrations_enabled
            ):
                app.state.queue.start_sweeper()
            try:
                yield
            finally:
                if config_task is not None:
                    config_task.cancel()
                try:
                    await app.state.queue.close()
                    await redis.aclose()
                finally:
                    await engine.dispose()

    app = FastAPI(
        title="Platform API",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None if config.app_env == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if config.app_env == "production" else "/openapi.json",
    )
    install_handlers(app)
    install_integration_handlers(app)
    for item in ROUTERS:
        app.include_router(item, prefix="/api/v1")
    for item in PI_APP_ROUTERS:
        if item is pi_app_router:
            prefix = "/api/v1"
        elif item is billing_router:
            # Business invoicing lives beside (not inside) the Pi subscription billing
            # routes, so no path is shadowed: /api/v1/pi-app/sales/billing/...
            prefix = "/api/v1/pi-app/sales"
        else:
            prefix = "/api/v1/pi-app"
        app.include_router(item, prefix=prefix)
    app.add_middleware(
        OriginCheckMiddleware,
        allowed_origins=config.cors_origins,
        pi_origins=config.pi_app_origins,
    )
    # Must wrap OriginCheckMiddleware: drops Origin only on public integration webhooks.
    app.add_middleware(PublicWebhookOriginExemption)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*config.cors_origins, *config.pi_app_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "X-Correlation-ID"],
    )
    return app
