from uuid import uuid4

import pytest
from test_service_lifecycle import create, register

pytestmark = pytest.mark.integration


async def act(api, key, record_id):
    run = await create(
        api,
        "workflows",
        {"tool": key, "arguments": {"id": record_id}, "idempotency_key": str(uuid4())},
    )
    assert run["status"] == "pending_approval"
    result = await create(api, f"workflows/{run['id']}/approve", {})
    assert result["status"] == "completed", result
    return result["result"]


async def test_workflow_quote_to_order_delivery_history_and_rejection(api):
    await register(api)
    customer = await create(api, "customers", {"name": "Workflow lifecycle", "tags": []})
    offering = await create(
        api,
        "catalog/products",
        {
            "name": "Website",
            "variants": [
                {"sku": "FLOW-WEB", "name": "Standard", "price": "100.00", "currency": "USD"}
            ],
        },
    )
    quote = await create(
        api,
        "quotes",
        {
            "customer_id": customer["id"],
            "lines": [{"variant_id": offering["variants"][0]["id"], "quantity": 1}],
        },
    )
    for action in ("submit", "send", "accept"):
        quote = await act(api, f"quotes.{action}", quote["id"])
    order = await act(api, "quotes.convert", quote["id"])
    for action in ("confirm", "start_processing", "complete"):
        order = await act(api, f"orders.{action}", order["id"])
    assert order["status"] == "delivered" and order["invoice_id"]
    history = (await api.get("/api/v1/workflows?status=completed&page_size=2")).json()
    assert history["total"] == 7 and len(history["items"]) == 2

    invoice = await create(
        api,
        "billing/invoices",
        {
            "customer_id": customer["id"],
            "lines": [{"description": "Maintenance", "quantity": 1, "unit_price": "10.00"}],
        },
    )
    proposal = await create(
        api,
        "workflows",
        {
            "tool": "billing.issue",
            "arguments": {"id": invoice["id"]},
            "idempotency_key": str(uuid4()),
        },
    )
    rejected = await create(api, f"workflows/{proposal['id']}/reject", {})
    assert rejected["status"] == "rejected"
    assert (
        await api.post(f"/api/v1/workflows/{proposal['id']}/approve", json={})
    ).status_code == 422
    assert (await api.get(f"/api/v1/billing/invoices/{invoice['id']}")).json()["status"] == "draft"
    await act(api, "billing.issue", invoice["id"])
    await act(api, "billing.void", invoice["id"])
    # Switching tenant cannot reveal, approve, or reject the old tenant's workflow.
    api.cookies.clear()
    await register(api)
    assert (await api.get("/api/v1/workflows")).json()["total"] == 0
    for path in (f"workflows/{proposal['id']}/approve", f"workflows/{proposal['id']}/reject"):
        assert (await api.post(f"/api/v1/{path}", json={})).status_code == 404


async def test_workflow_approval_rejects_changed_record(api):
    await register(api)
    customer = await create(api, "customers", {"name": "Changed quote", "tags": []})
    quote = await create(
        api,
        "quotes",
        {
            "customer_id": customer["id"],
            "lines": [{"description": "Consulting", "quantity": 1, "unit_price": "10.00"}],
        },
    )
    proposal = await create(
        api,
        "workflows",
        {
            "tool": "quotes.submit",
            "arguments": {"id": quote["id"]},
            "idempotency_key": str(uuid4()),
        },
    )
    assert (
        await api.patch(f"/api/v1/quotes/{quote['id']}", json={"notes": "Changed scope"})
    ).status_code == 200
    response = await api.post(f"/api/v1/workflows/{proposal['id']}/approve", json={})
    assert response.status_code == 409 and response.json()["error"]["code"] == "PROPOSAL_CHANGED"
    assert (await api.get(f"/api/v1/quotes/{quote['id']}")).json()["status"] == "draft"


async def test_approval_is_durable_idempotent_and_cannot_be_bypassed(api):
    await register(api)
    customer = await create(api, "customers", {"name": "Workflow customer", "tags": []})
    offering = await create(
        api,
        "catalog/products",
        {
            "name": "Consulting",
            "variants": [
                {"sku": "CONSULT", "name": "Session", "price": "50.00", "currency": "USD"}
            ],
        },
    )
    order = await create(
        api,
        "orders",
        {
            "customer_id": customer["id"],
            "lines": [{"variant_id": offering["variants"][0]["id"], "quantity": 1}],
        },
    )
    request = {
        "tool": "orders.confirm",
        "arguments": {"id": order["id"]},
        "idempotency_key": "confirm-order-test",
    }
    run = await create(api, "workflows", request)
    assert run["status"] == "pending_approval"
    assert (await api.get(f"/api/v1/orders/{order['id']}")).json()["status"] == "draft"
    assert (await create(api, "workflows", request))["id"] == run["id"]
    assert (
        await api.post("/api/v1/workflows", json={**request, "approved": True})
    ).status_code == 422
    approved = await create(api, f"workflows/{run['id']}/approve", {})
    assert approved["status"] == "completed"
    assert approved["result"]["status"] == "confirmed"
    assert (await create(api, f"workflows/{run['id']}/approve", {}))["result"] == approved["result"]
    assert (
        await api.post(
            "/api/v1/workflows", json={**request, "tool": "overview.summary", "arguments": {}}
        )
    ).status_code == 409
    assert (
        await api.post("/api/v1/workflows", json={**request, "tool": "sql.execute"})
    ).status_code == 422
