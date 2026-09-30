"""Operator workspace console: role gating, suspension blocks access, audit."""

from uuid import UUID

import pytest
from pi_saas_support import FakeProvider, configure, pi_client, pi_register
from sqlalchemy import func, select
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration


async def test_operator_lists_and_suspends_workspaces(api, business_db):
    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    pi_view = await pi_register(client, "Pi Business")
    identity = await register(api)  # the operator's own Owner OS workspace
    assert (await api.get("/api/v1/operator/workspaces")).status_code == 403
    member = PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="support")
    business_db.add(member)
    await business_db.flush()
    assert (await api.get("/api/v1/operator/workspaces")).status_code == 403  # no capability
    member.role = "operations_admin"
    await business_db.flush()
    listed = (await api.get("/api/v1/operator/workspaces", params={"kind": "pi"})).json()
    target = next(i for i in listed["items"] if i["id"] == pi_view["business"]["id"])
    assert target["kind"] == "pi" and "pi" in target["products"] and target["members"] == 1
    assert target["is_member"] is False
    own = identity["tenant"]["id"]
    everyone = (await api.get("/api/v1/operator/workspaces")).json()["items"]
    assert next(i for i in everyone if i["id"] == own)["is_member"] is True
    refused = await api.post(
        f"/api/v1/operator/workspaces/{own}/status", json={"status": "inactive", "reason": "test"}
    )
    assert refused.status_code == 422
    assert (await client.get("/api/v1/pi-app/account")).status_code == 200
    suspended = await api.post(
        f"/api/v1/operator/workspaces/{target['id']}/status",
        json={"status": "inactive", "reason": "Reported abuse"},
    )
    assert suspended.status_code == 200 and suspended.json()["status"] == "inactive"
    assert (await client.get("/api/v1/pi-app/account")).status_code in (401, 403)
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.action == "pi_operator.workspace_suspended",
            AuditEvent.tenant_id == UUID(target["id"]),
        )
    )
    assert audited == 1
    await api.post(
        f"/api/v1/operator/workspaces/{target['id']}/status",
        json={"status": "active", "reason": "Resolved"},
    )
    assert (await client.get("/api/v1/pi-app/account")).status_code == 200
    detail = (await api.get(f"/api/v1/operator/pi/accounts/{target['id']}")).json()
    assert detail["customer_payment_methods"] == []
    await client.aclose()


async def test_workspace_reactivation_keeps_a_separate_business_suspension(api, business_db):
    app = api._transport.app  # type: ignore[attr-defined]
    configure(app, FakeProvider())
    client = pi_client(app)
    pi_view = await pi_register(client, "Pi Business")
    target = pi_view["business"]["id"]
    identity = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(identity["user"]["id"]), role="owner"))
    await business_db.flush()

    async def account_status() -> str:
        return (await api.get(f"/api/v1/operator/pi/accounts/{target}")).json()["status"]

    async def workspace(status: str) -> None:
        response = await api.post(
            f"/api/v1/operator/workspaces/{target}/status",
            json={"status": status, "reason": "Operator check"},
        )
        assert response.status_code == 200, response.text

    # Business suspended for abuse, then the workspace suspended and reactivated:
    # the abuse suspension stays.
    abuse = await api.post(
        f"/api/v1/operator/pi/accounts/{target}/status",
        json={"status": "suspended", "reason": "Abuse report"},
    )
    assert abuse.status_code == 200
    await workspace("inactive")
    await workspace("active")
    assert await account_status() == "suspended"
    # A suspension caused only by the workspace action is undone by reactivation.
    await api.post(
        f"/api/v1/operator/pi/accounts/{target}/status",
        json={"status": "active", "reason": "Resolved"},
    )
    await workspace("inactive")
    assert await account_status() == "suspended"
    await workspace("active")
    assert await account_status() == "active"
    await client.aclose()


async def test_operator_team_cannot_escalate_or_edit_owners(api, business_db):
    from app.modules.users.models import PlatformUser

    identity = await register(api)
    me = PiOperatorMember(
        user_id=UUID(identity["user"]["id"]),
        role="support",
        overrides=["operator.team.manage"],
    )
    owner_user = PlatformUser(email="owner-op@example.com", display_name="Owner Op")
    new_user = PlatformUser(email="new-op@example.com", display_name="New Op")
    business_db.add_all([me, owner_user, new_user])
    await business_db.flush()
    business_db.add(PiOperatorMember(user_id=owner_user.id, role="owner"))
    await business_db.flush()

    async def add(email: str, role: str, overrides: list[str] | None = None) -> int:
        body = {"email": email, "role": role, "overrides": overrides or []}
        return (await api.post("/api/v1/operator/pi/team", json=body)).status_code

    assert await add("new-op@example.com", "operations_admin") == 403  # more than I hold
    assert await add("new-op@example.com", "support", ["operator.billing.manage"]) == 403
    assert await add("new-op@example.com", "support") == 201
    assert await add("owner-op@example.com", "analyst") == 403  # can't demote an owner
    assert await add(identity["user"]["email"], "support", ["operator.accounts.all"]) == 422
    owner_row = await business_db.scalar(
        select(PiOperatorMember).where(PiOperatorMember.user_id == owner_user.id)
    )
    revoke = await api.delete(f"/api/v1/operator/pi/team/{owner_row.id}")
    assert revoke.status_code == 403 and owner_row.status == "active"
