import socket
import ssl
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:
    from app.core.config import Settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
# libpq-only parameters that asyncpg does not accept; SSL is applied via connect args.
_LIBPQ_ONLY = ("sslmode", "ssl", "channel_binding", "sslrootcert", "options")


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    url: URL
    ssl_mode: str | None
    pooled: bool
    remote: bool
    neon: bool


def resolve_database(settings: "Settings", raw_url: str) -> DatabaseTarget:
    """Accept asyncpg URLs and provider strings such as Neon's `postgresql://…?sslmode=`."""
    url = make_url(raw_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+asyncpg")
    if url.drivername != "postgresql+asyncpg" or not url.host or not url.database:
        raise ValueError("Use a PostgreSQL connection URL")
    query = dict(url.query)
    url_ssl = query.get("sslmode") or query.get("ssl")
    url = url.set(query={k: v for k, v in query.items() if k not in _LIBPQ_ONLY})
    host = url.host or ""
    neon = host.endswith(".neon.tech")
    remote = host not in _LOCAL_HOSTS and "." in host
    ssl_mode = settings.database_ssl or (str(url_ssl) if url_ssl else None)
    if ssl_mode is None and neon:
        ssl_mode = "require"
    if ssl_mode not in (None, "disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
        raise ValueError("Unsupported database SSL mode")
    pooled = settings.database_pooled
    if pooled is None:
        pooled = "-pooler." in host
    return DatabaseTarget(url, ssl_mode, pooled, remote, neon)


def _ssl_argument(settings: "Settings", mode: str | None) -> Any:
    if mode in (None, "disable"):
        return False
    if mode in ("allow", "prefer"):
        return "prefer"
    # require / verify-ca / verify-full: always verify the certificate chain and host.
    # Neon presents publicly trusted certificates; private CAs use DATABASE_SSL_ROOT_CERT.
    return ssl.create_default_context(cafile=settings.database_ssl_root_cert)


_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_IPV4_ONLY_HOSTS: set[str] = set()


def _getaddrinfo(host: Any, port: Any, family: int = 0, *args: Any, **kwargs: Any) -> Any:
    if host in _IPV4_ONLY_HOSTS and family in (0, socket.AF_UNSPEC):
        family = socket.AF_INET
    return _ORIGINAL_GETADDRINFO(host, port, family, *args, **kwargs)


def restrict_to_ipv4(host: str) -> None:
    """Resolve only A records for this host. The hostname is still used for TLS (SNI and
    certificate verification); only the address family changes."""
    _IPV4_ONLY_HOSTS.add(host)
    socket.getaddrinfo = _getaddrinfo


def create_engine(settings: "Settings", url: str | None = None) -> AsyncEngine:
    target = resolve_database(settings, url or settings.database_url.get_secret_value())
    if settings.database_ip_family == "ipv4" and target.url.host:
        restrict_to_ipv4(target.url.host)
    connect_args: dict[str, Any] = {
        "timeout": settings.db_connect_timeout_seconds,
        "command_timeout": 10,
        "ssl": _ssl_argument(settings, target.ssl_mode),
    }
    prepared = settings.database_pooler_prepared_statements
    if prepared is None:
        prepared = target.neon
    if target.pooled and not prepared:
        # Generic PgBouncer transaction pooling: no cached prepared statements, unique
        # statement names, and no startup parameters. Configure the statement timeout on
        # the role instead: ALTER ROLE <app_role> SET statement_timeout = '10s';
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"
    else:
        connect_args["server_settings"] = {"statement_timeout": "10000"}
    return create_async_engine(
        target.url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        # Serverless databases close idle connections; recycle before they do.
        pool_recycle=settings.db_pool_recycle_seconds,
        connect_args=connect_args,
        hide_parameters=True,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Services explicitly own commits; closing an uncommitted session rolls back.
    async with request.app.state.sessions() as session:
        yield session
