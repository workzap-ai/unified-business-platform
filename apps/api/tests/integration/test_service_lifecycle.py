from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


async def register(api):
    result = await api.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner-{uuid4().hex}@example.com",
            "password": "ServiceFlow!Secure234",
            "display_name": "Service Owner",
            "organization_name": "Service Agency",
        },
    )
    assert result.status_code == 201, result.text
    api.headers["x-csrf-token"] = api.cookies["platform_csrf"]
    return result.json()


async def create(api, path, data):
    response = await api.post(f"/api/v1/{path}", json=data)
    assert response.status_code in (200, 201), response.text
    return response.json()


async def test_service_lifecycle_without_inventory(api):
    identity = await register(api)
    assert "inventory.read" not in identity["permissions"]
    settings = (await api.get("/api/v1/settings/business")).json()
    assert settings["business_type"] == "service_business"
    assert (await api.get("/api/v1/inventory/locations")).status_code == 403
    customer = await create(api, "customers", {"name": "Website Client", "tags": []})
    offering = await create(
        api,
        "catalog/products",
        {
            "name": "Website development",
            "offering_type": "service",
            "variants": [
                {"sku": "WEB-BASE", "name": "Implementation", "price": "1250.25", "currency": "USD"}
            ],
        },
    )
    assert offering["offering_type"] == "service"
    assert offering["variants"][0]["track_inventory"] is False
    lead = await create(
        api,
        "sales/leads",
        {
            "title": "Website and chatbot requirement",
            "customer_id": customer["id"],
            "notes": "Needs bilingual support",
        },
    )
    response = await api.patch(
        "/api/v1/settings/business", json={"quote_approval_threshold": "100.00"}
    )
    assert response.status_code == 200, response.text
    quote = await create(
        api,
        "quotes",
        {
            "customer_id": customer["id"],
            "lead_id": lead["id"],
            "lines": [{"variant_id": offering["variants"][0]["id"], "quantity": "1"}],
        },
    )
    assert quote["total"] == "1250.25"
    for action in ("submit", "approve", "send", "accept"):
        quote = await create(api, f"quotes/{quote['id']}/actions", {"action": action})
    order = await create(api, f"quotes/{quote['id']}/order", {})
    assert order["fulfillment_type"] == "service"
    again = await create(api, f"quotes/{quote['id']}/order", {})
    assert again["id"] == order["id"]
    for action in ("confirm", "start_processing"):
        order = await create(api, f"orders/{order['id']}/actions", {"action": action})
    assert "complete" in order["next_actions"] and "ship" not in order["next_actions"]
    assert (
        await api.post(f"/api/v1/orders/{order['id']}/actions", json={"action": "ship"})
    ).status_code == 422
    order = await create(api, f"orders/{order['id']}/actions", {"action": "complete"})
    assert order["status"] == "delivered"
    invoice_id = order["invoice_id"]
    assert invoice_id
    invoice = (await api.get(f"/api/v1/billing/invoices/{invoice_id}")).json()
    assert invoice["status"] == "issued"
    assert invoice["total"] == "1250.25"
    payment = await create(
        api,
        f"billing/invoices/{invoice_id}/payments",
        {"amount": "1250.25", "method": "bank_transfer", "reference": "TEST-PAID"},
    )
    assert payment
    invoice = (await api.get(f"/api/v1/billing/invoices/{invoice_id}")).json()
    assert invoice["balance_due"] == "0.00"
    assert (await api.get("/api/v1/overview")).status_code == 200


async def test_service_stock_and_cross_tenant_access_denied(api):
    await register(api)
    customer = await create(api, "customers", {"name": "Private client", "tags": []})
    response = await api.post(
        "/api/v1/catalog/products",
        json={
            "name": "Invalid service",
            "offering_type": "service",
            "variants": [
                {
                    "sku": "BAD",
                    "name": "Bad",
                    "price": "10.00",
                    "currency": "USD",
                    "track_inventory": True,
                }
            ],
        },
    )
    assert response.status_code == 422
    api.cookies.clear()
    await register(api)
    assert (await api.get(f"/api/v1/customers/{customer['id']}")).status_code == 404
    assert (
        await api.patch(f"/api/v1/customers/{customer['id']}", json={"name": "Hijack"})
    ).status_code == 404
    api.headers.pop("x-csrf-token")
    assert (
        await api.post("/api/v1/customers", json={"name": "No CSRF", "tags": []})
    ).status_code == 403
