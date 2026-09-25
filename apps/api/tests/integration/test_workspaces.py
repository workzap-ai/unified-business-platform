from uuid import uuid4

import httpx
import pytest
from test_service_lifecycle import create, register

pytestmark = pytest.mark.integration


async def switch(api, tenant, environment=None):
    response = await api.put(
        "/api/v1/auth/session/workspace", json={"tenant_id": tenant, "environment_id": environment}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_create_switch_environments_and_isolation(api):
    first = await register(api)
    customer = await create(api, "customers", {"name": "First workspace client"})
    second = await create(
        api, "auth/workspaces", {"name": "Second Agency", "business_type": "hybrid_business"}
    )
    assert second["user"]["id"] == first["user"]["id"]
    assert second["tenant"]["id"] != first["tenant"]["id"] and second["roles"] == ["owner"]
    assert "inventory.read" in second["permissions"]
    assert len((await api.get("/api/v1/tenants")).json()["items"]) == 2
    assert (await api.get("/api/v1/customers")).json()["total"] == 0
    assert (await api.get(f"/api/v1/customers/{customer['id']}")).status_code == 404
    assert (
        await api.get("/api/v1/customers", headers={"x-workspace-tenant": first["tenant"]["id"]})
    ).status_code == 409
    env = await create(
        api, "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
    )
    production_customer = await create(api, "customers", {"name": "Second production client"})
    await switch(api, second["tenant"]["id"], env["id"])
    assert (await api.get("/api/v1/customers")).json()["total"] == 0
    assert (await api.get(f"/api/v1/customers/{production_customer['id']}")).status_code == 404
    assert (
        await api.patch(
            f"/api/v1/environments/{env['id']}", json={"name": "Staging", "status": "archived"}
        )
    ).status_code == 422
    await switch(api, second["tenant"]["id"])
    assert (
        await api.patch(
            f"/api/v1/environments/{env['id']}", json={"name": "Staging", "status": "archived"}
        )
    ).status_code == 200
    assert (
        await api.put(
            "/api/v1/auth/session/workspace",
            json={"tenant_id": second["tenant"]["id"], "environment_id": env["id"]},
        )
    ).status_code == 404
    assert (
        await api.put(
            "/api/v1/auth/session/workspace",
            json={
                "tenant_id": first["tenant"]["id"],
                "environment_id": second["environment"]["id"],
            },
        )
    ).status_code == 404
    await switch(api, first["tenant"]["id"])
    assert (await api.get("/api/v1/customers")).json()["items"][0]["id"] == customer["id"]
    owner = (await api.get("/api/v1/members")).json()["items"][0]
    assert (await api.delete(f"/api/v1/members/{owner['membership_id']}")).status_code == 422
    api.headers.pop("x-csrf-token")
    assert (await api.post("/api/v1/auth/workspaces", json={"name": "Blocked"})).status_code == 403


async def test_member_permissions_revocation_and_foreign_roles(api):
    first = await register(api)
    role = await create(
        api,
        "roles",
        {"key": "client-viewer", "name": "Client viewer", "permissions": ["customers.read"]},
    )
    email = f"member-{uuid4().hex}@example.com"
    member = await create(
        api,
        "members",
        {
            "email": email,
            "display_name": "Reader",
            "initial_password": "MemberSecure123!",
            "role_ids": [role["id"]],
        },
    )
    async with httpx.AsyncClient(
        transport=api._transport,
        base_url="http://testserver",
        headers={"origin": "http://localhost:3000"},
    ) as reader:
        response = await reader.post(
            "/api/v1/auth/login", json={"email": email, "password": "MemberSecure123!"}
        )
        assert response.status_code == 200, response.text
        reader.headers["x-csrf-token"] = reader.cookies["platform_csrf"]
        assert (await reader.get("/api/v1/customers")).status_code == 200
        assert (await reader.post("/api/v1/customers", json={"name": "Denied"})).status_code == 403
        assert (await reader.get("/api/v1/members")).status_code == 403
        assert (await api.delete(f"/api/v1/members/{member['membership_id']}")).status_code == 204
        denied = await reader.get("/api/v1/customers")
        assert (
            denied.status_code == 409 and denied.json()["error"]["code"] == "WORKSPACE_NOT_SELECTED"
        )
    await create(api, "auth/workspaces", {"name": "Different Workspace"})
    assert (
        await api.post(
            "/api/v1/members",
            json={"email": email, "display_name": "Reader", "role_ids": [role["id"]]},
        )
    ).status_code == 404
    await switch(api, first["tenant"]["id"])
