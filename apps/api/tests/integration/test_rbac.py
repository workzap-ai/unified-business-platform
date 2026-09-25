"""RBAC: every system role against a representative route set per module, custom-role
escalation, and owner protection. The required permission of each route is written out
here (the contract), and role grants come from the catalog in access.permissions."""

from uuid import uuid4

import pytest

from app.modules.access.permissions import SYSTEM_ROLES
from tests.support.workspace import (
    Actor,
    add_member,
    error_code,
    product,
    set_business,
    unique,
)

pytestmark = pytest.mark.integration

RANDOM = str(uuid4())

# (method, path, body, permissions required). {customer}/{quote}/{order} are real records;
# quote and order are cancelled, so a permitted call fails later with 422 and has no effect.
ROUTES: list[tuple[str, str, dict[str, object] | None, frozenset[str]]] = [
    ("GET", "customers", None, frozenset({"customers.read"})),
    ("GET", "customers/{customer}", None, frozenset({"customers.read"})),
    ("GET", "customers/{customer}/notes", None, frozenset({"customers.read"})),
    ("POST", "customers", {}, frozenset({"customers.write"})),
    ("PUT", "customers/{customer}/status", {}, frozenset({"customers.write"})),
    ("POST", "customers/{customer}/notes", {}, frozenset({"customers.write"})),
    ("GET", "catalog/products", None, frozenset({"catalog.read"})),
    ("GET", "catalog/categories", None, frozenset({"catalog.read"})),
    ("POST", "catalog/products", {}, frozenset({"catalog.write"})),
    ("POST", "catalog/categories", {}, frozenset({"catalog.write"})),
    ("PATCH", f"catalog/variants/{RANDOM}", {"price": "-1"}, frozenset({"catalog.write"})),
    ("GET", "inventory/levels", None, frozenset({"inventory.read"})),
    ("GET", "inventory/movements", None, frozenset({"inventory.read"})),
    ("POST", "inventory/adjustments", {}, frozenset({"inventory.adjust"})),
    ("POST", "inventory/locations", {}, frozenset({"inventory.adjust"})),
    ("GET", "sales/leads", None, frozenset({"sales.read"})),
    ("GET", "sales/pipeline", None, frozenset({"sales.read"})),
    ("POST", "sales/leads", {}, frozenset({"sales.write"})),
    ("PUT", f"sales/leads/{RANDOM}/stage", {}, frozenset({"sales.write"})),
    ("GET", "quotes", None, frozenset({"quotes.read"})),
    ("GET", "quotes/{quote}", None, frozenset({"quotes.read"})),
    ("POST", "quotes", {}, frozenset({"quotes.write"})),
    ("PATCH", "quotes/{quote}", {}, frozenset({"quotes.write"})),
    (
        "POST",
        "quotes/{quote}/actions",
        {"action": "cancel"},
        frozenset({"quotes.read", "quotes.write"}),
    ),
    (
        "POST",
        "quotes/{quote}/actions",
        {"action": "approve"},
        frozenset({"quotes.read", "quotes.approve"}),
    ),
    ("POST", "quotes/{quote}/order", None, frozenset({"quotes.write", "orders.write"})),
    ("GET", "orders", None, frozenset({"orders.read"})),
    ("GET", "orders/{order}", None, frozenset({"orders.read"})),
    ("POST", "orders", {}, frozenset({"orders.write"})),
    ("PUT", "orders/{order}/lines", {}, frozenset({"orders.write"})),
    (
        "POST",
        "orders/{order}/actions",
        {"action": "confirm"},
        frozenset({"orders.read", "orders.write"}),
    ),
    (
        "POST",
        "orders/{order}/actions",
        {"action": "cancel"},
        frozenset({"orders.read", "orders.cancel"}),
    ),
    ("GET", "billing/invoices", None, frozenset({"billing.read"})),
    ("GET", "billing/payments", None, frozenset({"billing.read"})),
    ("GET", "billing/summary", None, frozenset({"billing.read"})),
    ("POST", "billing/invoices", {}, frozenset({"billing.write"})),
    ("POST", f"billing/invoices/{RANDOM}/payments", {}, frozenset({"billing.write"})),
    ("POST", f"billing/invoices/{RANDOM}/actions", {}, frozenset({"billing.write"})),
    ("GET", "finance/summary", None, frozenset({"finance.read"})),
    ("GET", "finance/expenses", None, frozenset({"finance.read"})),
    ("POST", "finance/expenses", {}, frozenset({"finance.write"})),
    ("POST", f"finance/expenses/{RANDOM}/void", None, frozenset({"finance.write"})),
    ("GET", "hr/employees", None, frozenset({"hr.read"})),
    ("GET", "hr/headcount", None, frozenset({"hr.read"})),
    ("POST", "hr/employees", {}, frozenset({"hr.write"})),
    ("PATCH", f"hr/employees/{RANDOM}", {}, frozenset({"hr.write"})),
    ("GET", "overview", None, frozenset({"overview.read"})),
    ("GET", "reports/revenue", None, frozenset({"reports.read", "billing.read"})),
    ("GET", "reports/orders", None, frozenset({"reports.read", "orders.read"})),
    ("GET", "reports/customers", None, frozenset({"reports.read", "customers.read"})),
    ("GET", "reports/quotes", None, frozenset({"reports.read", "quotes.read"})),
    ("GET", "reports/inventory", None, frozenset({"reports.read", "inventory.read"})),
    ("GET", "reports/employees", None, frozenset({"reports.read", "hr.read"})),
    ("GET", "members", None, frozenset({"admin.members.read"})),
    ("GET", "roles", None, frozenset({"admin.members.read"})),
    ("GET", "permissions", None, frozenset({"admin.members.read"})),
    ("POST", "members", {}, frozenset({"admin.members.manage"})),
    ("PUT", f"members/{RANDOM}/roles", {}, frozenset({"admin.members.manage"})),
    ("DELETE", f"members/{RANDOM}", None, frozenset({"admin.members.manage"})),
    ("POST", "roles", {}, frozenset({"admin.roles.manage"})),
    ("DELETE", f"roles/{RANDOM}", None, frozenset({"admin.roles.manage"})),
    ("POST", "organization/branches", {}, frozenset({"admin.organization.manage"})),
    ("POST", "organization/departments", {}, frozenset({"admin.organization.manage"})),
    ("POST", "environments", {}, frozenset({"admin.environments.manage"})),
    ("PATCH", f"environments/{RANDOM}", {}, frozenset({"admin.environments.manage"})),
    ("PATCH", "settings/business", {"tax_rate": "7"}, frozenset({"settings.manage"})),
    ("PATCH", "organization", {}, frozenset({"settings.manage"})),
    ("POST", "products/not-a-product/install", None, frozenset({"admin.products.manage"})),
    ("GET", "audit/events", None, frozenset({"audit.read"})),
    ("GET", "notifications", None, frozenset({"notifications.read"})),
    # Workspace-level reads that any active member may use.
    ("GET", "organization", None, frozenset()),
    ("GET", "environments", None, frozenset()),
    ("GET", "settings/business", None, frozenset()),
    ("GET", "navigation", None, frozenset()),
]


async def seeded_owner(stack, browser) -> tuple[Actor, dict[str, str]]:
    owner = await stack.register(browser)
    # Hybrid business so inventory permissions are not removed by the capability layer.
    await set_business(owner, business_type="hybrid_business")
    customer = await owner.create("customers", {"name": "RBAC customer"})
    item = await product(owner)
    lines = [{"variant_id": item["variants"][0]["id"], "quantity": "1"}]
    quote = await owner.create("quotes", {"customer_id": customer["id"], "lines": lines})
    await owner.create(f"quotes/{quote['id']}/actions", {"action": "cancel"})
    order = await owner.create(
        "orders",
        {
            "customer_id": customer["id"],
            "lines": [{"variant_id": lines[0]["variant_id"], "quantity": 1}],
        },
    )
    await owner.create(f"orders/{order['id']}/actions", {"action": "cancel"})
    return owner, {"customer": customer["id"], "quote": quote["id"], "order": order["id"]}


@pytest.mark.parametrize("role", [r for r in SYSTEM_ROLES if r != "owner"])
async def test_system_role_route_matrix(stack, role):
    granted = SYSTEM_ROLES[role][2]
    async with stack.browser() as owner_browser, stack.browser() as member_browser:
        owner, ids = await seeded_owner(stack, owner_browser)
        email = await add_member(owner, [role])
        member = await stack.login(member_browser, email)
        assert set(member.session["permissions"]) == set(granted)

        mismatches = []
        for method, template, body, required in ROUTES:
            path = template.format(**ids)
            response = await member.client.request(method, f"/api/v1/{path}", json=body)
            allowed = required <= granted
            if allowed and response.status_code in (401, 403):
                mismatches.append(("unexpected deny", method, path, response.status_code))
            if not allowed and not (
                response.status_code == 403 and error_code(response) == "FORBIDDEN"
            ):
                mismatches.append(("not denied", method, path, response.status_code))
            if allowed and response.status_code >= 500:
                mismatches.append(("server error", method, path, response.status_code))
        assert mismatches == []

        # Denied mutations had no effect on the owner's data.
        quote = (await owner.get(f"quotes/{ids['quote']}")).json()
        order = (await owner.get(f"orders/{ids['order']}")).json()
        assert quote["status"] == "cancelled" and order["status"] == "cancelled"
        assert (await owner.get("customers")).json()["total"] == 1


async def test_service_business_removes_inventory_permissions_even_for_owners(stack):
    async with stack.browser() as browser:
        owner = await stack.register(browser)
        assert not any(p.startswith("inventory.") for p in owner.session["permissions"])
        for path in ("inventory/levels", "inventory/movements", "reports/inventory"):
            assert (await owner.get(path)).status_code == 403
        denied = await owner.post(
            "inventory/adjustments",
            {"variant_id": RANDOM, "quantity": 1, "kind": "receipt", "reason": "nope"},
        )
        assert denied.status_code == 403
        await set_business(owner, business_type="product_business")
        assert (await owner.get("inventory/levels")).status_code == 200


async def test_sensitive_hr_fields_and_balances_follow_permissions(stack):
    async with stack.browser() as ob, stack.browser() as mb, stack.browser() as sb:
        owner = await stack.register(ob)
        employee = await owner.create(
            "hr/employees",
            {
                "full_name": "Paid Person",
                "job_title": "Engineer",
                "employment_type": "full_time",
                "hire_date": "2026-01-05",
                "salary": "4200.00",
                "salary_currency": "USD",
            },
        )
        customer = await owner.create("customers", {"name": "Balance customer"})
        manager = await stack.login(mb, await add_member(owner, ["manager"]))
        seen = (await manager.get(f"hr/employees/{employee['id']}")).json()
        assert seen["salary"] is None and seen["salary_currency"] is None
        assert seen["sensitive_visible"] is False
        listed = (await manager.get("hr/employees")).json()["items"][0]
        assert listed["salary"] is None
        support = await stack.login(sb, await add_member(owner, ["support"]))
        detail = (await support.get(f"customers/{customer['id']}")).json()
        assert detail["summary"]["outstanding_balance"] is None
        owner_detail = (await owner.get(f"customers/{customer['id']}")).json()
        assert owner_detail["summary"]["outstanding_balance"] == "0.00"
        overview = (await support.get("overview")).json()
        assert overview["revenue"] is None and overview["pending_payments"] is None
        assert overview["recent_activity"] == []


async def test_hr_writer_without_sensitive_access_cannot_set_salary(stack):
    async with stack.browser() as ob, stack.browser() as mb:
        owner = await stack.register(ob)
        role = await owner.create(
            "roles",
            {"key": "hr-clerk", "name": "HR clerk", "permissions": ["hr.read", "hr.write"]},
        )
        roles = {r["key"]: r["id"] for r in (await owner.get("roles")).json()}
        assert roles["hr-clerk"] == role["id"]
        email = f"{unique('clerk')}@example.com"
        await owner.create(
            "members",
            {
                "email": email,
                "display_name": "Clerk",
                "initial_password": "Clerk-Password-123",
                "role_ids": [role["id"]],
            },
        )
        clerk = await stack.login(mb, email, "Clerk-Password-123")
        body = {
            "full_name": "Someone",
            "job_title": "Analyst",
            "employment_type": "contract",
            "hire_date": "2026-02-01",
        }
        denied = await clerk.post("hr/employees", {**body, "salary": "99.00"})
        assert denied.status_code == 422 and error_code(denied) == "SENSITIVE_FIELD"
        created = await clerk.create("hr/employees", body)
        denied = await clerk.patch(f"hr/employees/{created['id']}", {"salary": "1.00"})
        assert error_code(denied) == "SENSITIVE_FIELD"


async def test_custom_roles_cannot_escalate_beyond_their_creator(stack):
    async with stack.browser() as ob, stack.browser() as db, stack.browser() as vb:
        owner = await stack.register(ob)
        delegated = await owner.create(
            "roles",
            {
                "key": "people-admin",
                "name": "People admin",
                "permissions": [
                    "admin.roles.manage",
                    "admin.members.read",
                    "admin.members.manage",
                    "customers.read",
                ],
            },
        )
        email = f"{unique('delegate')}@example.com"
        await owner.create(
            "members",
            {
                "email": email,
                "display_name": "Delegate",
                "initial_password": "Delegate-Pass-123",
                "role_ids": [delegated["id"]],
            },
        )
        delegate = await stack.login(db, email, "Delegate-Pass-123")
        roles = {r["key"]: r for r in (await delegate.get("roles")).json()}

        escalate = await delegate.post(
            "roles",
            {"key": "sneaky", "name": "Sneaky", "permissions": ["customers.read", "billing.write"]},
        )
        assert escalate.status_code == 422 and error_code(escalate) == "PERMISSION_ESCALATION"
        unknown = await delegate.post(
            "roles", {"key": "odd", "name": "Odd", "permissions": ["root.everything"]}
        )
        assert error_code(unknown) == "UNKNOWN_PERMISSION"
        reader = await delegate.create(
            "roles", {"key": "reader", "name": "Reader", "permissions": ["customers.read"]}
        )
        widened = await delegate.put(
            f"roles/{reader['id']}",
            {"name": "Reader", "permissions": ["customers.read", "orders.read"]},
        )
        assert error_code(widened) == "PERMISSION_ESCALATION"
        # Delegate may not rewrite the role that grants their own power either.
        widened = await delegate.put(
            f"roles/{delegated['id']}",
            {"name": "People admin", "permissions": ["admin.roles.manage", "billing.write"]},
        )
        assert error_code(widened) == "PERMISSION_ESCALATION"
        for key in ("admin", "viewer"):
            system = await delegate.put(
                f"roles/{roles[key]['id']}", {"name": "Hacked", "permissions": []}
            )
            assert error_code(system) == "SYSTEM_ROLE"
            assert error_code(await delegate.delete(f"roles/{roles[key]['id']}")) == "SYSTEM_ROLE"

        new_member = {
            "email": f"{unique('victim')}@example.com",
            "display_name": "New",
            "initial_password": "Victim-Password-1",
        }
        for key, code in (("admin", "PERMISSION_ESCALATION"), ("owner", "OWNER_REQUIRED")):
            response = await delegate.post(
                "members", {**new_member, "role_ids": [roles[key]["id"]]}
            )
            assert response.status_code == 422 and error_code(response) == code, key
        own = next(
            m for m in (await delegate.get("members")).json()["items"] if m["email"] == email
        )
        self_promote = await delegate.put(
            f"members/{own['membership_id']}/roles", {"role_ids": [roles["admin"]["id"]]}
        )
        assert error_code(self_promote) == "PERMISSION_ESCALATION"
        viewer = await delegate.create("members", {**new_member, "role_ids": [reader["id"]]})
        assert viewer["roles"] == ["reader"]
        # A role still assigned to someone cannot be deleted.
        assert (await delegate.delete(f"roles/{reader['id']}")).status_code == 409

        session = (await stack.login(vb, new_member["email"], "Victim-Password-1")).session
        assert session["permissions"] == ["customers.read"]
        assert set((await delegate.get("auth/session")).json()["permissions"]) == {
            "admin.roles.manage",
            "admin.members.read",
            "admin.members.manage",
            "customers.read",
        }


async def test_owner_protection_last_owner_and_admin_limits(stack):
    async with stack.browser() as ob, stack.browser() as ab, stack.browser() as sb:
        owner = await stack.register(ob)
        roles = {r["key"]: r["id"] for r in (await owner.get("roles")).json()}
        members = (await owner.get("members")).json()["items"]
        owner_membership = members[0]["membership_id"]

        demote = await owner.put(
            f"members/{owner_membership}/roles", {"role_ids": [roles["admin"]]}
        )
        assert demote.status_code == 422 and error_code(demote) == "LAST_OWNER"
        assert error_code(await owner.delete(f"members/{owner_membership}")) == "SELF_REVOKE"

        admin_email = await add_member(owner, ["admin"])
        admin = await stack.login(ab, admin_email)
        second_email = await add_member(owner, ["owner"])
        second = await stack.login(sb, second_email)
        by_email = {m["email"]: m for m in (await owner.get("members")).json()["items"]}

        # Administrators hold every permission but cannot touch owners.
        demote = await admin.put(
            f"members/{owner_membership}/roles", {"role_ids": [roles["viewer"]]}
        )
        assert demote.status_code == 422 and error_code(demote) == "OWNER_REQUIRED"
        revoke = await admin.delete(f"members/{by_email[second_email]['membership_id']}")
        assert revoke.status_code == 422 and error_code(revoke) == "OWNER_REQUIRED"
        grant = await admin.put(
            f"members/{by_email[admin_email]['membership_id']}/roles",
            {"role_ids": [roles["owner"]]},
        )
        assert error_code(grant) == "OWNER_REQUIRED"
        members_now = {m["email"]: m["roles"] for m in (await owner.get("members")).json()["items"]}
        assert members_now[owner.email] == ["owner"] and members_now[second_email] == ["owner"]

        # With two owners, one owner may step down, but not the remaining one.
        stepped = await second.put(
            f"members/{by_email[second_email]['membership_id']}/roles",
            {"role_ids": [roles["admin"]]},
        )
        assert stepped.status_code == 200 and stepped.json()["roles"] == ["admin"]
        last = await owner.put(f"members/{owner_membership}/roles", {"role_ids": [roles["admin"]]})
        assert error_code(last) == "LAST_OWNER"
        # An owner may manage administrators.
        assert (
            await owner.delete(f"members/{by_email[admin_email]['membership_id']}")
        ).status_code == 204
        assert (await admin.get("customers")).status_code == 409
