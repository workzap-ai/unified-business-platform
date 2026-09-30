"""Operator control plane: platform users (disable signs out everywhere), the
cross-workspace audit log and platform status. Capabilities are enforced."""

from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from test_service_lifecycle import register

from app.modules.auth.models import AuthSession
from app.modules.pi_saas.models import PiOperatorMember

pytestmark = pytest.mark.integration


def _client(api) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": "http://localhost:3000"},
    )


async def test_operator_manages_platform_users_audit_and_system(api, business_db):
    other = _client(api)
    victim = await register(other)
    assert (await other.get("/api/v1/auth/session")).status_code == 200
    me = await register(api)
    assert (await api.get("/api/v1/operator/users")).status_code == 403
    member = PiOperatorMember(user_id=UUID(me["user"]["id"]), role="support")
    business_db.add(member)
    await business_db.flush()
    assert (await api.get("/api/v1/operator/users")).status_code == 403  # support: no users.read
    member.role = "owner"
    await business_db.flush()

    listed = (
        await api.get("/api/v1/operator/users", params={"search": victim["user"]["email"]})
    ).json()
    [row] = listed["items"]
    assert row["email"] == victim["user"]["email"] and row["status"] == "active"
    assert row["workspaces"] and row["last_seen_at"] is not None
    mine = (await api.get("/api/v1/operator/users", params={"search": me["user"]["email"]})).json()
    assert mine["items"][0]["is_you"] and mine["items"][0]["operator_role"] == "owner"
    self_disable = await api.post(
        f"/api/v1/operator/users/{me['user']['id']}/status",
        json={"status": "inactive", "reason": "testing"},
    )
    assert self_disable.status_code == 422

    disabled = await api.post(
        f"/api/v1/operator/users/{victim['user']['id']}/status",
        json={"status": "inactive", "reason": "Reported spam"},
    )
    assert disabled.status_code == 200 and disabled.json()["sessions_revoked"] >= 1
    assert (await other.get("/api/v1/auth/session")).status_code == 401  # signed out everywhere
    sessions = list(
        await business_db.scalars(
            select(AuthSession).where(AuthSession.user_id == UUID(victim["user"]["id"]))
        )
    )
    assert all(s.revoked_at is not None for s in sessions)
    enabled = await api.post(
        f"/api/v1/operator/users/{victim['user']['id']}/status",
        json={"status": "active", "reason": "Cleared"},
    )
    assert enabled.json()["status"] == "active"

    audit = (await api.get("/api/v1/operator/audit", params={"action": "pi_operator.user_"})).json()
    actions = [e["action"] for e in audit["items"]]
    assert "pi_operator.user_disabled" in actions and "pi_operator.user_enabled" in actions
    everything = (await api.get("/api/v1/operator/audit")).json()
    assert any(e["workspace"] for e in everything["items"])  # other workspaces are visible

    system = (await api.get("/api/v1/operator/system")).json()
    assert system["users"].get("active", 0) >= 2 and system["operators"] >= 1
    assert system["runtime"]["database_revision"]
    assert set(system["messages_24h"]) == {"received", "sent", "failed"}
    await other.aclose()


async def test_only_owners_act_on_other_owners(api, business_db):
    other = _client(api)
    boss = await register(other)
    business_db.add(PiOperatorMember(user_id=UUID(boss["user"]["id"]), role="owner"))
    me = await register(api)
    business_db.add(PiOperatorMember(user_id=UUID(me["user"]["id"]), role="operations_admin"))
    await business_db.flush()
    refused = await api.post(
        f"/api/v1/operator/users/{boss['user']['id']}/sign-out",
    )
    assert refused.status_code == 403
    await other.aclose()
