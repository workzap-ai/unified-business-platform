import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings():
    # Never read apps/api/.env: it may hold real provider keys for local development.
    return Settings(
        _env_file=None,
        openai_api_key=None,
        gemini_api_key=None,
        groq_api_key=None,
        app_env="test",
        database_url="postgresql+asyncpg://test:test@127.0.0.1:1/test",
        redis_url="redis://127.0.0.1:1/0",
        allowed_hosts=["testserver"],
        dependency_timeout_seconds=0.2,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        yield client
