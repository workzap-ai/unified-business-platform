from datetime import date

import pytest
from test_service_lifecycle import create, register

pytestmark = pytest.mark.integration


async def test_business_reads_reports_admin_finance_hr_and_inventory(api):
    await register(api)
    assert (
        await api.patch("/api/v1/settings/business", json={"business_type": "hybrid_business"})
    ).status_code == 200
    branch = await create(api, "organization/branches", {"name": "Head Office", "code": "hq"})
    department = await create(
        api,
        "organization/departments",
        {"name": "Engineering", "code": "eng", "branch_id": branch["id"]},
    )
    employee = await create(
        api,
        "hr/employees",
        {
            "full_name": "Engineer",
            "job_title": "Consultant",
            "employment_type": "full_time",
            "hire_date": str(date.today()),
            "department_id": department["id"],
            "salary": "2500.00",
            "salary_currency": "USD",
        },
    )
    assert employee["salary"] == "2500.00" and employee["sensitive_visible"]
    assert (
        await api.patch(f"/api/v1/hr/employees/{employee['id']}", json={"status": "on_leave"})
    ).status_code == 200
    expense = await create(
        api,
        "finance/expenses",
        {
            "category": "software",
            "description": "Business subscription",
            "amount": "25.50",
            "incurred_on": str(date.today()),
        },
    )
    summary = (await api.get("/api/v1/finance/summary")).json()
    assert summary["cash_out"] == "25.50"
    await create(api, f"finance/expenses/{expense['id']}/void", {})
    assert (await api.get("/api/v1/finance/summary")).json()["cash_out"] == "0.00"
    product = await create(
        api,
        "catalog/products",
        {
            "name": "Router",
            "offering_type": "product",
            "variants": [
                {
                    "sku": "ROUTER",
                    "name": "Standard",
                    "price": "50.00",
                    "currency": "USD",
                    "track_inventory": True,
                }
            ],
        },
    )
    vid = product["variants"][0]["id"]
    await create(
        api,
        "inventory/adjustments",
        {"variant_id": vid, "quantity": 5, "kind": "receipt", "reason": "Initial stock"},
    )
    customer = await create(api, "customers", {"name": "Hybrid client"})
    order = await create(
        api,
        "orders",
        {"customer_id": customer["id"], "lines": [{"variant_id": vid, "quantity": 2}]},
    )
    assert order["fulfillment_type"] == "product"
    await create(api, f"orders/{order['id']}/actions", {"action": "confirm"})
    assert (await api.get("/api/v1/inventory/levels")).json()["items"][0]["on_hand"] == 3
    await create(api, f"orders/{order['id']}/actions", {"action": "cancel"})
    assert (await api.get("/api/v1/inventory/levels")).json()["items"][0]["on_hand"] == 5
    paths = [
        "overview",
        "organization",
        "organization/branches",
        "organization/departments",
        "environments",
        "tenants",
        "members",
        "roles",
        "permissions",
        "settings/business",
        "catalog/products",
        "catalog/categories",
        "customers",
        "sales/leads",
        "sales/pipeline",
        "quotes",
        "orders",
        "billing/summary",
        "billing/invoices",
        "billing/payments",
        "finance/summary",
        "finance/expenses",
        "hr/headcount",
        "hr/employees",
        "inventory/levels",
        "inventory/movements",
        "inventory/locations",
        "reports/revenue",
        "reports/orders",
        "reports/customers",
        "reports/quotes",
        "reports/inventory",
        "reports/employees",
        "notifications",
        "notifications/unread-count",
        "audit/events",
        "products",
        "navigation",
    ]
    for path in paths:
        response = await api.get(f"/api/v1/{path}")
        assert response.status_code == 200, (path, response.text)
    for tool in [
        "overview.summary",
        "sales.pipeline",
        "quotes.pending",
        "reports.revenue",
        "finance.summary",
        "hr.headcount",
        "inventory.low_stock",
        "administration.settings",
    ]:
        run = await create(
            api, "workflows", {"tool": tool, "idempotency_key": f"test:{tool}", "arguments": {}}
        )
        assert run["status"] == "completed", (tool, run)
