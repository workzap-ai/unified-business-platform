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
from app.core.jobs import create_queue
from app.core.logging import configure_logging
from app.core.middleware import OriginCheckMiddleware, RequestContextMiddleware
from app.health import router
from app.modules.access.routes import router as access_router
from app.modules.audit.routes import router as audit_router
from app.modules.auth.routes import router as auth_router
from app.modules.billing.routes import router as billing_router
from app.modules.business_settings.routes import router as business_settings_router
from app.modules.catalog.routes import router as catalog_router
from app.modules.customers.routes import router as customers_router
from app.modules.environments.routes import router as environments_router
from app.modules.finance.routes import router as finance_router
from app.modules.hr.routes import router as hr_router
from app.modules.inventory.routes import router as inventory_router
from app.modules.navigation.routes import router as navigation_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.orders.routes import router as orders_router
from app.modules.products.routes import router as products_router
from app.modules.quotes.routes import router as quotes_router
from app.modules.reports.routes import router as reports_router
from app.modules.sales.routes import router as sales_router
from app.modules.tenants.organization_routes import router as organization_router
from app.modules.tenants.routes import router as tenant_router

ROUTERS = [
    router,
    auth_router,
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
    # PI API routers are added with the PI backend phase (schema exists in 0002).
]


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
            timeout=10, follow_redirects=False, limits=httpx.Limits(max_connections=50)
        ) as client:
            app.state.settings = config
            app.state.engine = engine
            app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
            app.state.redis = redis
            app.state.http = client
            app.state.queue = create_queue(config, app.state.sessions, client)
            try:
                yield
            finally:
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
    for item in ROUTERS:
        app.include_router(item, prefix="/api/v1")
    app.add_middleware(OriginCheckMiddleware, allowed_origins=config.cors_origins)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Correlation-ID", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "X-Correlation-ID"],
    )
    return app
