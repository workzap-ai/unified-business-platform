"""Every static workspace GET route must work through the real application stack."""

import pytest
from test_service_lifecycle import create, register

pytestmark = pytest.mark.integration


async def test_all_static_workspace_read_endpoints(api):
    await register(api)
    assert (
        await api.patch("/api/v1/settings/business", json={"business_type": "hybrid_business"})
    ).status_code == 200
    await create(api, "products/pi/install", {})
    assert (
        await api.put("/api/v1/products/pi/environment", json={"enabled": True})
    ).status_code == 200
    schema = (await api.get("/openapi.json")).json()
    checked = []
    for path, methods in schema["paths"].items():
        if (
            "get" not in methods
            or "{" in path
            or path.startswith(("/api/v1/health/", "/api/v1/webhooks/"))
        ):
            continue
        # Knowledge search is the only static read requiring a query value.
        params = {"q": "service policy"} if path.endswith("/knowledge/search") else {}
        response = await api.get(path, params=params)
        if path.startswith("/api/v1/external/"):
            # External integrations use API keys, never the workspace session cookie.
            assert response.status_code == 401, path
            continue
        if path.startswith("/api/v1/external/"):
            # Bearer-only APIs must reject a browser session; scoped-key use is
            # exercised in test_integration_workflows.
            assert response.status_code == 401, path
            continue
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text[:300]}"
        checked.append(path)
    assert len(checked) >= 60
