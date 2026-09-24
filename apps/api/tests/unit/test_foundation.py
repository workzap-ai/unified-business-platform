import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.core.pagination import Pagination
from app.main import create_app


def test_liveness_and_request_ids(client):
    response = client.get("/api/v1/health/live", headers={"x-correlation-id": "flow_123"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    UUID(response.headers["x-request-id"])
    assert response.headers["x-correlation-id"] == "flow_123"
    other = client.get("/api/v1/health/live", headers={"x-correlation-id": "bad value"})
    assert other.headers["x-correlation-id"] == other.headers["x-request-id"]
    assert other.headers["x-request-id"] != response.headers["x-request-id"]


def test_readiness_failure_does_not_leak_connection_details(client):
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert "postgresql" not in response.text
    assert "127.0.0.1" not in response.text


def test_readiness_success(settings):
    with TestClient(create_app(settings)) as client:
        connection = AsyncMock()
        client.app.state.engine = SimpleNamespace(connect=lambda: connection)
        client.app.state.redis.ping = AsyncMock(return_value=True)
        assert client.get("/api/v1/health/ready").json() == {"status": "ok"}


def test_safe_errors_and_validation(settings):
    app = create_app(settings)

    @app.get("/explode")
    async def explode():
        raise RuntimeError("password=DO_NOT_LEAK")

    @app.get("/validate")
    async def validate(value: int = Query()):
        return {"value": value}

    with TestClient(app, raise_server_exceptions=False) as client:
        for path, status, code in [
            ("/missing", 404, "RESOURCE_NOT_FOUND"),
            ("/explode", 500, "INTERNAL_ERROR"),
            ("/validate?value=DO_NOT_LEAK", 422, "VALIDATION_ERROR"),
        ]:
            response = client.get(path)
            assert response.status_code == status
            assert response.json()["error"]["code"] == code
            assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
            assert "DO_NOT_LEAK" not in response.text


def test_hosts_and_cors(client):
    assert client.get("/api/v1/health/live", headers={"host": "evil.example"}).status_code == 400
    permitted = client.get("/api/v1/health/live", headers={"origin": "http://localhost:3000"})
    assert permitted.headers["access-control-allow-origin"] == "http://localhost:3000"
    rejected = client.get("/api/v1/health/live", headers={"origin": "https://evil.example"})
    assert "access-control-allow-origin" not in rejected.headers


def test_configuration_fails_closed():
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///data", redis_url="redis://localhost/0")
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            database_url="postgresql+asyncpg://localhost/test",
            redis_url="redis://localhost/0",
            cors_origins=["http://example.com"],
        )


def test_pagination_limits():
    assert Pagination(page=2, page_size=25).offset == 25
    for values in ({"page": 0}, {"page_size": 101}, {"page_size": -1}, {"page": 10001}):
        with pytest.raises(ValidationError):
            Pagination(**values)


def test_log_allowlist_drops_sensitive_extra_and_exception():
    record = logging.LogRecord("platform", logging.INFO, "", 1, "request_completed", (), None)
    record.password = "DO_NOT_LEAK"
    record.request_id = "safe-id"
    output = JsonFormatter().format(record)
    assert "DO_NOT_LEAK" not in output
    assert json.loads(output)["request_id"] == "safe-id"
