"""Super admin and admin in the operator console: create a workspace for someone and
manage its members. Only super admins touch owners, a workspace keeps one owner, nobody
edits their own membership here, and other roles can't manage at all."""

from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, update
from test_service_lifecycle import register

from app.modules.audit.models import AuditEvent
from app.modules.auth.models import AuthSession
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration


def _client(api) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": "http://localhost:3000"},
    )


def _members(api, tenant_id):
    return api.get(f"/api/v1/operator/workspaces/{tenant_id}/members")


async def test_tiers_are_named_super_admin_admin_operator(api, business_db):
    me = await register(api)
    member = PiOperatorMember(user_id=UUID(me["user"]["id"]), role="owner")
    business_db.add(member)
    await business_db.flush()
    view = (await api.get("/api/v1/operator/pi/me")).json()
    assert (view["role_name"], view["tier"], view["tier_name"]) == (
        "Super admin",
        "super_admin",
        "Super admin",
    )
    roles = (await api.get("/api/v1/operator/pi/team")).json()["roles"]
    assert roles["operations_admin"]["name"] == "Admin"
    assert roles["operations_admin"]["tier"] == "admin"
    assert {roles[k]["tier"] for k in ("support", "billing", "analyst")} == {"operator"}


async def test_super_admin_creates_a_workspace_and_manages_owners(api, business_db):
    me = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(me["user"]["id"]), role="owner"))
    await business_db.flush()
    created = await api.post(
        "/api/v1/operator/workspaces",
        json={"name": "Crescent Traders", "owner_email": "Founder@Crescent.example"},
    )
    assert created.status_code == 201, created.text
    tenant_id = created.json()["id"]
    assert created.json()["invite_link"].startswith("http")  # a new person is invited
    listed = (await _members(api, tenant_id)).json()
    [owner] = listed["members"]
    assert owner["email"] == "founder@crescent.example" and owner["roles"] == ["owner"]
    assert listed["can_manage_owners"] is True
    assert {"owner", "admin", "viewer"} <= {r["key"] for r in listed["roles"]}

    last = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members/{owner['id']}/role",
        json={"role": "admin"},
    )
    assert last.status_code == 422 and last.json()["error"]["code"] == "LAST_OWNER"
    second = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members",
        json={"email": "partner@crescent.example", "role": "owner"},
    )
    assert second.status_code == 201
    demoted = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members/{owner['id']}/role",
        json={"role": "admin"},
    )
    assert demoted.status_code == 200 and demoted.json()["role"] == "admin"
    removed = await api.delete(
        f"/api/v1/operator/workspaces/{tenant_id}/members/{second.json()['id']}"
    )
    assert removed.status_code == 422  # the only owner left
    unknown = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members",
        json={"email": "x@crescent.example", "role": "emperor"},
    )
    assert unknown.status_code == 422
    audited = await business_db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.tenant_id == UUID(tenant_id),
            AuditEvent.action.in_(
                [
                    "pi_operator.workspace_created",
                    "pi_operator.workspace_member_added",
                    "pi_operator.workspace_member_role_changed",
                ]
            ),
        )
    )
    assert audited == 3


async def test_admin_manages_members_but_not_owners(api, business_db):
    other = _client(api)
    business = await register(other)  # someone else's workspace
    tenant_id = business["tenant"]["id"]
    staff = _client(api)
    colleague = await register(staff)
    me = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(me["user"]["id"]), role="operations_admin"))
    await business_db.flush()

    listed = (await _members(api, tenant_id)).json()
    [owner] = listed["members"]
    assert listed["can_manage"] is True and listed["can_manage_owners"] is False
    added = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members",
        json={"email": colleague["user"]["email"], "role": "manager"},
    )
    assert added.status_code == 201 and added.json()["invite_link"] is None  # existing account
    again = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members",
        json={"email": colleague["user"]["email"], "role": "viewer"},
    )
    assert again.status_code == 409
    membership = added.json()["id"]
    changed = await api.post(
        f"/api/v1/operator/workspaces/{tenant_id}/members/{membership}/role",
        json={"role": "viewer"},
    )
    assert changed.json()["role"] == "viewer"
    for refused in (
        await api.post(
            f"/api/v1/operator/workspaces/{tenant_id}/members/{membership}/role",
            json={"role": "owner"},
        ),
        await api.post(
            f"/api/v1/operator/workspaces/{tenant_id}/members/{owner['id']}/role",
            json={"role": "viewer"},
        ),
        await api.delete(f"/api/v1/operator/workspaces/{tenant_id}/members/{owner['id']}"),
        await api.post(
            "/api/v1/operator/workspaces/" + tenant_id + "/members",
            json={"email": "boss@example.com", "role": "owner"},
        ),
    ):
        assert refused.status_code == 403, refused.text

    # The colleague is working in the workspace, then loses it when removed.
    await business_db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == UUID(colleague["user"]["id"]))
        .values(active_tenant_id=UUID(tenant_id))
    )
    removed = await api.delete(f"/api/v1/operator/workspaces/{tenant_id}/members/{membership}")
    assert removed.status_code == 204
    after = (await _members(api, tenant_id)).json()["members"]
    assert next(m for m in after if m["id"] == membership)["status"] == "revoked"
    still_pointing = await business_db.scalar(
        select(func.count())
        .select_from(AuthSession)
        .where(
            AuthSession.user_id == UUID(colleague["user"]["id"]),
            AuthSession.active_tenant_id == UUID(tenant_id),
        )
    )
    assert still_pointing == 0
    await other.aclose()
    await staff.aclose()


async def test_own_membership_and_other_roles_are_refused(api, business_db):
    me = await register(api)
    own = me["tenant"]["id"]
    member = PiOperatorMember(user_id=UUID(me["user"]["id"]), role="owner")
    business_db.add(member)
    await business_db.flush()
    [mine] = (await _members(api, own)).json()["members"]
    assert mine["is_you"] is True
    refused = await api.delete(f"/api/v1/operator/workspaces/{own}/members/{mine['id']}")
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "OWN_MEMBERSHIP"

    member.role = "analyst"  # can read workspaces, can't manage them
    await business_db.flush()
    assert (await _members(api, own)).status_code == 200
    assert (
        await api.post(
            "/api/v1/operator/workspaces", json={"name": "Nope", "owner_email": "n@example.com"}
        )
    ).status_code == 403
    member.role = "support"
    await business_db.flush()
    assert (await _members(api, own)).status_code == 403
