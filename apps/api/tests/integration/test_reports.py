"""Reports and overview are bounded, permission-shaped and computed from scoped data."""

from datetime import date

import pytest

from tests.support.workspace import product, set_business

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "path",
    [
        "reports/revenue?months=0",
        "reports/revenue?months=25",
        "reports/orders?days=0",
        "reports/orders?days=367",
        "customers?page_size=101",
        "customers?page=0",
        "orders?page=10001",
        "audit/events?page_size=500",
        "customers?search=" + "x" * 101,
        "audit/events?outcome=anything",
    ],
)
async def test_report_and_list_parameters_are_bounded(stack, path):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        response = await owner.get(path)
        assert response.status_code == 422, (path, response.text)


async def test_report_figures_come_from_own_workspace_data(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        await set_business(owner, business_type="product_business")
        item = await product(owner, price="30.00", offering_type="product")
        customer = await owner.create("customers", {"name": "Reported"})
        order = await owner.create(
            "orders",
            {
                "customer_id": customer["id"],
                "lines": [{"variant_id": item["variants"][0]["id"], "quantity": 2}],
            },
        )
        confirmed = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
        await owner.create(
            f"billing/invoices/{confirmed['invoice_id']}/payments",
            {"amount": "25.00", "method": "cash"},
        )
        await owner.create(
            "finance/expenses",
            {
                "category": "rent",
                "description": "Rent",
                "amount": "10.00",
                "incurred_on": str(date.today()),
            },
        )
        revenue = (await owner.get("reports/revenue", params={"months": 3})).json()
        assert len(revenue["months"]) == 3
        assert revenue["total_invoiced"] == "60.00" and revenue["total_collected"] == "25.00"
        assert revenue["months"][-1]["month"] == date.today().strftime("%Y-%m")
        orders = (await owner.get("reports/orders")).json()
        assert orders["average_order_value"] == "60.00"
        assert {s["status"]: s["count"] for s in orders["by_status"]} == {"confirmed": 1}
        top = (await owner.get("reports/customers")).json()["top"]
        assert [(t["name"], t["invoiced"], t["orders"]) for t in top] == [("Reported", "60.00", 1)]
        finance = (await owner.get("finance/summary")).json()
        assert (finance["cash_in"], finance["cash_out"], finance["net_cash"]) == (
            "25.00",
            "10.00",
            "15.00",
        )
        assert finance["receivables"] == "35.00"
        overview = (await owner.get("overview")).json()
        assert overview["revenue"]["value"] == "25.00"
        assert overview["pending_payments"]["value"] == "35.00"
        assert overview["orders"]["value"] == 1 and overview["customers"]["value"] == 1
        assert len(overview["recent_activity"]) <= 12
        inventory = (await owner.get("reports/inventory")).json()
        assert inventory["stock_value"] == "0.00"
