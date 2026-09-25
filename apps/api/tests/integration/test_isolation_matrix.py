"""Tenant AND environment isolation for every business table, through the HTTP API.

Tenant A / production creates one of everything. Then tenant B, and tenant A's own staging
environment, try to list, read, update, delete and reference those rows by ID. Every
attempt must look exactly like a missing record (404), and no list or total may move.
"""

from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.support.workspace import (
    Actor,
    accepted_quote,
    error_code,
    on_hand,
    product,
    receive,
    set_business,
)

pytestmark = pytest.mark.integration


async def build_tenant_a(owner: Actor) -> dict[str, Any]:
    await set_business(owner, business_type="product_business", low_stock_threshold=100)
    ids: dict[str, Any] = {"environment": owner.environment_id}
    customer = await owner.create(
        "customers", {"name": "Alpha Secret Customer", "phone": "+15550001"}
    )
    ids["customer"] = customer["id"]
    ids["note"] = (await owner.create(f"customers/{customer['id']}/notes", {"body": "secret"}))[
        "id"
    ]
    ids["lead"] = (
        await owner.create(
            "sales/leads",
            {"title": "Alpha lead", "customer_id": customer["id"], "estimated_value": "900.00"},
        )
    )["id"]
    category = await owner.create("catalog/categories", {"name": "Alpha", "slug": "alpha"})
    ids["category"] = category["id"]
    item = await product(owner, price="25.00", tracked=True, category_id=category["id"])
    ids["product"], ids["variant"] = item["id"], item["variants"][0]["id"]
    ids["location"] = (
        await owner.create("inventory/locations", {"name": "Alpha WH", "code": "alpha-wh"})
    )["id"]
    ids["movement"] = (await receive(owner, ids["variant"], 20))["id"]
    lines = [{"variant_id": ids["variant"], "quantity": "2"}]
    ids["draft_quote"] = (
        await owner.create("quotes", {"customer_id": customer["id"], "lines": lines})
    )["id"]
    quote = await accepted_quote(owner, customer["id"], lines)
    ids["accepted_quote"] = quote["id"]
    order = await owner.create(f"quotes/{quote['id']}/order", {})
    order = await owner.create(f"orders/{order['id']}/actions", {"action": "confirm"})
    ids["order"], ids["invoice"] = order["id"], order["invoice_id"]
    ids["payment"] = (
        await owner.create(
            f"billing/invoices/{order['invoice_id']}/payments",
            {"amount": "10.00", "method": "cash"},
        )
    )["id"]
    ids["draft_invoice"] = (
        await owner.create(
            "billing/invoices",
            {
                "customer_id": customer["id"],
                "lines": [{"description": "Fee", "quantity": "1", "unit_price": "5.00"}],
            },
        )
    )["id"]
    ids["expense"] = (
        await owner.create(
            "finance/expenses",
            {
                "category": "rent",
                "description": "Alpha rent",
                "amount": "300.00",
                "incurred_on": str(date.today()),
            },
        )
    )["id"]
    branch = await owner.create("organization/branches", {"name": "Alpha HQ", "code": "alpha-hq"})
    ids["branch"] = branch["id"]
    ids["department"] = (
        await owner.create(
            "organization/departments",
            {"name": "Alpha Ops", "code": "alpha-ops", "branch_id": branch["id"]},
        )
    )["id"]
    boss = await owner.create(
        "hr/employees",
        {
            "full_name": "Alpha Boss",
            "job_title": "CEO",
            "employment_type": "full_time",
            "hire_date": "2025-01-01",
            "salary": "9999.00",
            "salary_currency": "USD",
        },
    )
    ids["employee"] = boss["id"]
    ids["role"] = (
        await owner.create(
            "roles", {"key": "alpha-role", "name": "Alpha role", "permissions": ["customers.read"]}
        )
    )["id"]
    ids["membership"] = (await owner.get("members")).json()["items"][0]["membership_id"]
    notifications = (await owner.get("notifications")).json()
    assert notifications["total"] >= 1  # low-stock alert from the sale
    ids["notification"] = notifications["items"][0]["id"]
    ids["on_hand"] = await on_hand(owner, ids["variant"])
    assert ids["on_hand"] == 18
    return ids


async def build_own_records(actor: Actor) -> dict[str, str]:
    own: dict[str, str] = {}
    own["customer"] = (await actor.create("customers", {"name": "Own customer"}))["id"]
    item = await product(actor, price="7.00", tracked=True)
    own["product"], own["variant"] = item["id"], item["variants"][0]["id"]
    own["lead"] = (await actor.create("sales/leads", {"title": "Own lead"}))["id"]
    return own


def list_endpoints(a: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    return [
        ("customers", {}),
        ("catalog/products", {}),
        ("catalog/products", {"category_id": a["category"]}),
        ("inventory/levels", {}),
        ("inventory/levels", {"location_id": a["location"]}),
        ("inventory/movements", {}),
        ("inventory/movements", {"variant_id": a["variant"]}),
        ("sales/leads", {}),
        ("quotes", {}),
        ("quotes", {"customer_id": a["customer"]}),
        ("orders", {}),
        ("orders", {"customer_id": a["customer"]}),
        ("billing/invoices", {}),
        ("billing/invoices", {"customer_id": a["customer"]}),
        ("billing/payments", {}),
        ("finance/expenses", {}),
        ("hr/employees", {}),
        ("notifications", {}),
    ]


def foreign_reads(a: dict[str, Any]) -> list[str]:
    return [
        f"customers/{a['customer']}",
        f"customers/{a['customer']}/notes",
        f"customers/{a['customer']}/activities",
        f"catalog/products/{a['product']}",
        f"sales/leads/{a['lead']}",
        f"quotes/{a['draft_quote']}",
        f"quotes/{a['accepted_quote']}",
        f"orders/{a['order']}",
        f"billing/invoices/{a['invoice']}",
        f"billing/invoices/{a['draft_invoice']}",
        f"hr/employees/{a['employee']}",
    ]


def foreign_writes(a: dict[str, Any]) -> list[tuple[str, str, Any]]:
    return [
        ("PATCH", f"customers/{a['customer']}", {"name": "Hijacked"}),
        ("PUT", f"customers/{a['customer']}/status", {"status": "archived"}),
        ("POST", f"customers/{a['customer']}/notes", {"body": "injected"}),
        ("PATCH", f"catalog/products/{a['product']}", {"name": "Hijacked"}),
        (
            "POST",
            f"catalog/products/{a['product']}/variants",
            {"sku": "INJECT", "name": "x", "price": "1.00", "currency": "USD"},
        ),
        ("PATCH", f"catalog/variants/{a['variant']}", {"price": "0.01"}),
        ("PATCH", f"sales/leads/{a['lead']}", {"title": "Hijacked"}),
        ("PUT", f"sales/leads/{a['lead']}/stage", {"stage": "lost"}),
        ("PATCH", f"quotes/{a['draft_quote']}", {"notes": "Hijacked"}),
        ("POST", f"quotes/{a['draft_quote']}/actions", {"action": "cancel"}),
        ("POST", f"quotes/{a['accepted_quote']}/order", None),
        (
            "PUT",
            f"orders/{a['order']}/lines",
            {"lines": [{"variant_id": a["variant"], "quantity": 1}]},
        ),
        ("POST", f"orders/{a['order']}/actions", {"action": "cancel"}),
        ("POST", f"billing/invoices/{a['draft_invoice']}/actions", {"action": "void"}),
        ("POST", f"billing/invoices/{a['invoice']}/payments", {"amount": "1.00", "method": "cash"}),
        ("POST", f"finance/expenses/{a['expense']}/void", None),
        ("PATCH", f"hr/employees/{a['employee']}", {"status": "terminated"}),
    ]


def foreign_references(a: dict[str, Any], own: dict[str, str]) -> list[tuple[str, str, Any]]:
    today = str(date.today())
    return [
        (
            "POST",
            "orders",
            {
                "customer_id": a["customer"],
                "lines": [{"variant_id": own["variant"], "quantity": 1}],
            },
        ),
        (
            "POST",
            "orders",
            {
                "customer_id": own["customer"],
                "lines": [{"variant_id": a["variant"], "quantity": 1}],
            },
        ),
        (
            "POST",
            "quotes",
            {
                "customer_id": a["customer"],
                "lines": [{"variant_id": own["variant"], "quantity": "1"}],
            },
        ),
        (
            "POST",
            "quotes",
            {
                "customer_id": own["customer"],
                "lines": [{"variant_id": a["variant"], "quantity": "1"}],
            },
        ),
        (
            "POST",
            "quotes",
            {
                "customer_id": own["customer"],
                "lead_id": a["lead"],
                "lines": [{"variant_id": own["variant"], "quantity": "1"}],
            },
        ),
        (
            "POST",
            "billing/invoices",
            {
                "customer_id": a["customer"],
                "lines": [{"description": "x", "quantity": "1", "unit_price": "1.00"}],
            },
        ),
        (
            "POST",
            "inventory/adjustments",
            {"variant_id": a["variant"], "quantity": 5, "kind": "receipt", "reason": "inject"},
        ),
        (
            "POST",
            "inventory/adjustments",
            {
                "variant_id": own["variant"],
                "location_id": a["location"],
                "quantity": 5,
                "kind": "receipt",
                "reason": "inject",
            },
        ),
        ("POST", "sales/leads", {"title": "x", "customer_id": a["customer"]}),
        ("PATCH", f"sales/leads/{own['lead']}", {"customer_id": a["customer"]}),
        (
            "POST",
            "catalog/products",
            {
                "name": "x",
                "category_id": a["category"],
                "variants": [{"sku": "REF-X", "name": "x", "price": "1.00", "currency": "USD"}],
            },
        ),
        ("PATCH", f"catalog/products/{own['product']}", {"category_id": a["category"]}),
        (
            "POST",
            "hr/employees",
            {
                "full_name": "x",
                "job_title": "x",
                "employment_type": "intern",
                "hire_date": today,
                "manager_id": a["employee"],
            },
        ),
    ]


async def assert_isolated(observer: Actor, a: dict[str, Any], own: dict[str, str]) -> None:
    problems: list[Any] = []
    foreign_ids = {str(v) for v in a.values()}
    own_totals = {"customers": 1, "catalog/products": 1, "sales/leads": 1}
    for path, params in list_endpoints(a):
        response = await observer.get(path, params=params)
        body = response.json()
        expected_total = 0 if params else own_totals.get(path, 0)
        ids = {item.get("id") for item in body.get("items", [])}
        if response.status_code != 200 or body["total"] != expected_total or ids & foreign_ids:
            problems.append(("list leak", path, params, response.status_code, body.get("total")))
    categories = (await observer.get("catalog/categories")).json()
    if any(c["id"] == a["category"] for c in categories):
        problems.append(("category leak",))
    locations = (await observer.get("inventory/locations")).json()
    if any(loc["id"] == a["location"] for loc in locations):
        problems.append(("location leak",))
    for path in foreign_reads(a):
        response = await observer.get(path)
        if response.status_code != 404 or error_code(response) != "RESOURCE_NOT_FOUND":
            problems.append(("read", path, response.status_code))
    for method, path, body in foreign_writes(a) + foreign_references(a, own):
        response = await observer.client.request(method, f"/api/v1/{path}", json=body)
        if response.status_code != 404:
            problems.append(
                ("write/reference", method, path, response.status_code, response.text[:120])
            )
    events = (await observer.get("audit/events", params={"page_size": 100})).json()["items"]
    leaked = {e["entity_id"] for e in events} & {
        a["customer"],
        a["order"],
        a["invoice"],
        a["variant"],
    }
    if leaked:
        problems.append(("audit leak", leaked))
    # Aggregates and reports are scoped too.
    billing = (await observer.get("billing/summary")).json()
    finance = (await observer.get("finance/summary")).json()
    revenue = (await observer.get("reports/revenue")).json()
    pipeline = (await observer.get("sales/pipeline")).json()
    quotes = (await observer.get("reports/quotes")).json()
    headcount = (await observer.get("hr/headcount")).json()
    overview = (await observer.get("overview")).json()
    customers_report = (await observer.get("reports/customers")).json()
    totals = {
        "outstanding": billing["outstanding"],
        "cash_in": finance["cash_in"],
        "cash_out": finance["cash_out"],
        "receivables": finance["receivables"],
        "invoiced": revenue["total_invoiced"],
        "collected": revenue["total_collected"],
        # Only the observer's own (valueless) lead may appear.
        "pipeline": [(p["stage"], p["count"], float(p["value"]) == 0) for p in pipeline],
        "quotes": quotes["by_status"],
        "headcount": headcount["total"],
        "overview_orders": overview["orders"]["value"],
        "top_customers": customers_report["top"],
    }
    expected = {
        "outstanding": "0.00",
        "cash_in": "0.00",
        "cash_out": "0.00",
        "receivables": "0.00",
        "invoiced": "0.00",
        "collected": "0.00",
        "pipeline": [
            ("new", 1, True),
            ("qualified", 0, True),
            ("proposal", 0, True),
            ("won", 0, True),
            ("lost", 0, True),
        ],
        "quotes": [],
        "headcount": 0,
        "overview_orders": 0,
        "top_customers": [],
    }
    if totals != expected:
        problems.append(("aggregate leak", totals))
    # Marking a foreign notification read is a silent no-op.
    await observer.post("notifications/read", {"ids": [a["notification"]]})
    assert problems == []


async def assert_tenant_a_untouched(owner: Actor, a: dict[str, Any]) -> None:
    customer = (await owner.get(f"customers/{a['customer']}")).json()
    assert customer["name"] == "Alpha Secret Customer" and customer["status"] == "active"
    assert (await owner.get(f"customers/{a['customer']}/notes")).json()["total"] == 1
    assert (await owner.get(f"quotes/{a['draft_quote']}")).json()["status"] == "draft"
    order = (await owner.get(f"orders/{a['order']}")).json()
    assert order["status"] == "confirmed" and order["lines"][0]["quantity"] == 2
    invoice = (await owner.get(f"billing/invoices/{a['invoice']}")).json()
    assert invoice["amount_paid"] == "10.00" and len(invoice["payments"]) == 1
    assert (await owner.get(f"billing/invoices/{a['draft_invoice']}")).json()["status"] == "draft"
    detail = (await owner.get(f"catalog/products/{a['product']}")).json()
    assert len(detail["variants"]) == 1 and detail["variants"][0]["price"] == "25.00"
    assert detail["name"] != "Hijacked"
    lead = (await owner.get(f"sales/leads/{a['lead']}")).json()
    assert lead["title"] == "Alpha lead" and lead["stage"] == "new"
    assert (await owner.get(f"hr/employees/{a['employee']}")).json()["status"] == "active"
    expenses = (await owner.get("finance/expenses")).json()["items"]
    assert [e["status"] for e in expenses] == ["recorded"]
    assert await on_hand(owner, a["variant"]) == a["on_hand"]
    movements = (await owner.get("inventory/movements")).json()
    assert movements["total"] == 2  # the receipt and the sale; nothing injected
    unread = (await owner.get("notifications", params={"unread_only": True})).json()
    assert a["notification"] in {n["id"] for n in unread["items"]}


async def test_other_tenant_cannot_see_touch_or_reference_anything(stack):
    async with stack.browser() as a_browser, stack.browser() as b_browser:
        alice = await stack.register(a_browser)
        a = await build_tenant_a(alice)
        bob = await stack.register(b_browser)
        await set_business(bob, business_type="product_business")
        own = await build_own_records(bob)
        await assert_isolated(bob, a, own)

        # Tenant-wide organization data of A is invisible to B as well.
        tenant_level = [
            ("PATCH", f"organization/branches/{a['branch']}", {"name": "Hijacked"}),
            ("DELETE", f"organization/branches/{a['branch']}", None),
            ("PATCH", f"organization/departments/{a['department']}", {"name": "Hijacked"}),
            ("PUT", f"roles/{a['role']}", {"name": "Hijacked", "permissions": []}),
            ("DELETE", f"roles/{a['role']}", None),
            ("PUT", f"members/{a['membership']}/roles", {"role_ids": [a["role"]]}),
            ("DELETE", f"members/{a['membership']}", None),
            ("PATCH", f"environments/{a['environment']}", {"name": "x", "status": "archived"}),
            ("GET", f"tenants/{alice.tenant_id}/branches", None),
            (
                "POST",
                "organization/departments",
                {"name": "x", "code": "x-ref", "branch_id": a["branch"]},
            ),
            (
                "POST",
                "inventory/locations",
                {"name": "x", "code": "x-ref", "branch_id": a["branch"]},
            ),
            (
                "POST",
                "hr/employees",
                {
                    "full_name": "x",
                    "job_title": "x",
                    "employment_type": "intern",
                    "hire_date": str(date.today()),
                    "department_id": a["department"],
                },
            ),
        ]
        for method, path, body in tenant_level:
            response = await bob.client.request(method, f"/api/v1/{path}", json=body)
            assert response.status_code == 404, (method, path, response.status_code, response.text)
        for path in ("organization/branches", "organization/departments", "members"):
            assert (await bob.get(path)).json()["total"] == (1 if path == "members" else 0)
        assert a["role"] not in {r["id"] for r in (await bob.get("roles")).json()}
        assert alice.tenant_id not in {t["id"] for t in (await bob.get("tenants")).json()["items"]}
        await assert_tenant_a_untouched(alice, a)
        branches = (await alice.get("organization/branches")).json()["items"]
        assert [b["name"] for b in branches] == ["Alpha HQ"]


async def test_staging_environment_of_the_same_tenant_is_isolated_from_production(stack):
    async with stack.browser() as browser:
        alice = await stack.register(browser)
        a = await build_tenant_a(alice)
        production_tenant = alice.tenant_id
        staging = await alice.create(
            "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
        )
        await alice.switch(production_tenant, staging["id"])
        await set_business(alice, business_type="product_business")
        own = await build_own_records(alice)
        await assert_isolated(alice, a, own)
        # Organization data is tenant-wide by design (ADR 0005): staging may use A's department.
        employee = await alice.create(
            "hr/employees",
            {
                "full_name": "Staging hire",
                "job_title": "Tester",
                "employment_type": "contract",
                "hire_date": str(date.today()),
                "department_id": a["department"],
            },
        )
        assert employee["department_name"] == "Alpha Ops"
        # Document numbering restarts per environment; numbers never collide across them.
        order = await alice.create(
            "orders",
            {
                "customer_id": own["customer"],
                "lines": [{"variant_id": own["variant"], "quantity": 1}],
            },
        )
        assert order["number"] == "ORD-000001"
        await alice.switch(production_tenant)
        await assert_tenant_a_untouched(alice, a)
        assert (await alice.get("hr/employees")).json()["total"] == 1


async def test_database_rejects_cross_environment_references_even_if_services_were_bypassed(stack):
    async with stack.browser() as browser:
        alice = await stack.register(browser)
        await set_business(alice, business_type="product_business")
        customer = await alice.create("customers", {"name": "Prod"})
        item = await product(alice, tracked=True)
        await receive(alice, item["variants"][0]["id"], 1)
        invoice = await alice.create(
            "billing/invoices",
            {
                "customer_id": customer["id"],
                "lines": [{"description": "Fee", "quantity": "1", "unit_price": "5.00"}],
            },
        )
        staging = await alice.create(
            "environments", {"key": "staging", "name": "Staging", "kind": "staging"}
        )
    connection = stack.app.state.test_connection
    params = {
        "t": alice.tenant_id,
        "e": staging["id"],
        "c": customer["id"],
        "v": item["variants"][0]["id"],
        "i": invoice["id"],
    }
    statements = [
        "INSERT INTO customer_notes (tenant_id, environment_id, customer_id, author_label, body)"
        " VALUES (:t, :e, :c, 'x', 'x')",
        "INSERT INTO sales_leads (tenant_id, environment_id, customer_id, title, currency)"
        " VALUES (:t, :e, :c, 'x', 'USD')",
        "INSERT INTO orders (tenant_id, environment_id, number, customer_id, currency,"
        " created_by_label, subtotal, discount_total, tax_rate, tax_total, total)"
        " VALUES (:t, :e, 'ORD-X', :c, 'USD', 'x', 0, 0, 0, 0, 0)",
        "INSERT INTO payments (tenant_id, environment_id, invoice_id, number, amount, currency,"
        " method, received_on, recorded_by_label)"
        " VALUES (:t, :e, :i, 'PAY-X', 1, 'USD', 'cash', CURRENT_DATE, 'x')",
        "INSERT INTO stock_movements (tenant_id, environment_id, variant_id, location_id,"
        " quantity, kind, balance_after, actor_label)"
        " SELECT :t, :e, :v, l.id, 1, 'receipt', 1, 'x' FROM inventory_locations l"
        " WHERE l.tenant_id = :t LIMIT 1",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError) as caught:
            async with connection.begin_nested():
                await connection.execute(text(statement), params)
        assert "foreign key" in str(caught.value).lower(), statement
