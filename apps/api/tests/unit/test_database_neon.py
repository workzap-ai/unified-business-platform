import ssl

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.database import create_engine, resolve_database

POOLED = (
    "postgresql://app:secret@ep-cool-name-a1b2c3-pooler.eu-central-1.aws.neon.tech/"
    "platform?sslmode=require&channel_binding=require"
)
DIRECT = "postgresql://app:secret@ep-cool-name-a1b2c3.eu-central-1.aws.neon.tech/platform"


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "database_url": POOLED,
        "redis_url": "redis://127.0.0.1:6379/0",
        "allowed_hosts": ["testserver"],
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_neon_console_string_is_normalized_for_asyncpg():
    target = resolve_database(settings(), POOLED)
    assert target.url.drivername == "postgresql+asyncpg"
    assert dict(target.url.query) == {}  # libpq-only sslmode/channel_binding removed
    assert target.neon and target.pooled and target.remote
    assert target.ssl_mode == "require"


def test_direct_endpoint_is_not_pooled_and_ssl_defaults_on_for_neon():
    target = resolve_database(settings(), DIRECT)
    assert not target.pooled
    assert target.ssl_mode == "require"


def test_connect_arguments_for_pooled_and_direct(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, dict[str, object]] = {}

    def fake(url: object, **kwargs: object) -> object:
        captured[str(getattr(url, "host", ""))] = kwargs  # type: ignore[assignment]
        return object()

    monkeypatch.setattr("app.core.database.create_async_engine", fake)
    s = settings(migration_database_url=DIRECT)
    create_engine(s)
    create_engine(s, DIRECT)
    pooled, direct = captured.values()
    pooled_args = pooled["connect_args"]
    direct_args = direct["connect_args"]
    assert isinstance(pooled_args, dict) and isinstance(direct_args, dict)
    # Neon's pooler supports prepared statements and startup parameters.
    assert "statement_cache_size" not in pooled_args
    assert pooled_args["server_settings"] == {"statement_timeout": "10000"}
    assert direct_args["server_settings"] == {"statement_timeout": "10000"}
    for args in (pooled_args, direct_args):
        context = args["ssl"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert pooled["pool_recycle"] == s.db_pool_recycle_seconds


def test_local_database_keeps_plain_connections():
    local = "postgresql+asyncpg://u:p@127.0.0.1:55432/platform_test"
    target = resolve_database(settings(database_url=local), local)
    assert target.ssl_mode is None and not target.remote and not target.pooled


def test_production_rejects_remote_database_without_ssl():
    remote = "postgresql+asyncpg://u:p@db.example.com/platform"
    production = {
        "app_env": "production",
        "cors_origins": ["https://app.example.com"],
        "integrations_enabled": False,
        "database_url": remote,
    }
    with pytest.raises(ValidationError):
        settings(**production)
    assert settings(**production, database_ssl="require").database_ssl == "require"
    # Neon strings carry sslmode=require and are accepted in production.
    assert settings(**{**production, "database_url": POOLED}).app_env == "production"


def test_invalid_database_urls_are_rejected():
    for bad in ("sqlite:///data", "mysql://u:p@h/db", "postgresql://u:p@/db"):
        with pytest.raises(ValidationError):
            settings(database_url=bad)
    with pytest.raises(ValidationError):
        settings(database_url=POOLED.replace("sslmode=require", "sslmode=bogus"))


def test_generic_pgbouncer_disables_prepared_statements(monkeypatch: pytest.MonkeyPatch):
    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.core.database.create_async_engine",
        lambda url, **kwargs: captured.append(kwargs["connect_args"]) or object(),
    )
    url = "postgresql+asyncpg://u:p@pgbouncer.internal.example.com/platform"
    create_engine(settings(database_url=url, database_pooled=True, database_ssl="require"))
    create_engine(settings(database_pooler_prepared_statements=False))  # Neon, forced off
    for args in captured:
        assert args["statement_cache_size"] == 0
        assert args["prepared_statement_cache_size"] == 0
        assert "server_settings" not in args


def test_ipv4_option_filters_only_the_database_host(monkeypatch: pytest.MonkeyPatch):
    import socket

    from app.core import database

    calls: list[tuple[str, int]] = []

    def fake(host, port, family=0, *args, **kwargs):
        calls.append((host, family))
        return []

    monkeypatch.setattr(database, "_ORIGINAL_GETADDRINFO", fake)
    monkeypatch.setattr(database, "_IPV4_ONLY_HOSTS", set())
    monkeypatch.setattr(socket, "getaddrinfo", socket.getaddrinfo)
    monkeypatch.setattr("app.core.database.create_async_engine", lambda url, **kw: object())
    create_engine(settings(database_ip_family="ipv4"))
    host = "ep-cool-name-a1b2c3-pooler.eu-central-1.aws.neon.tech"
    socket.getaddrinfo(host, 5432)
    socket.getaddrinfo("example.com", 443)
    assert calls == [(host, socket.AF_INET), ("example.com", 0)]
