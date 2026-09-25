"""PI management API: product gating, RBAC, handoffs, replies, agents, knowledge, memory."""

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from test_pi_pipeline import pi_workspace
from test_service_lifecycle import create, register

from app.modules.audit.models import AuditEvent
from app.modules.pi.models import PiMessage
from app.modules.pi.runtime import send_pi_message
from app.modules.products.models import EnvironmentProductInstallation

pytestmark = pytest.mark.integration


def code(response: httpx.Response) -> str:
    return str(response.json()["error"]["code"])


async def audit_count(db: Any, tenant_id: str, action: str) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.tenant_id == UUID(tenant_id), AuditEvent.action == action)
        )
        or 0
    )


async def test_pi_requires_installation_enablement_and_features(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    identity = await register(api)
    for path in ("overview", "conversations", "handoffs", "agents", "settings"):
        response = await api.get(f"/api/v1/pi/{path}")
        assert (response.status_code, code(response)) == (403, "PI_NOT_ENABLED"), path
    await create(api, "products/pi/install", {})
    await api.put("/api/v1/products/pi/environment", json={"enabled": True})
    assert (await api.get("/api/v1/pi/overview")).status_code == 200
    await api.put("/api/v1/products/pi/environment", json={"enabled": False})
    assert code(await api.get("/api/v1/pi/overview")) == "PI_NOT_ENABLED"
    await api.put("/api/v1/products/pi/environment", json={"enabled": True})
    await business_db.execute(
        update(EnvironmentProductInstallation)
        .where(EnvironmentProductInstallation.tenant_id == UUID(identity["tenant"]["id"]))
        .values(disabled_features=["knowledge", "handoff"])
    )
    for path in ("knowledge/sources", "knowledge/documents", "handoffs"):
        response = await api.get(f"/api/v1/pi/{path}")
        assert (response.status_code, code(response)) == (403, "PI_FEATURE_DISABLED"), path
    assert (await api.get("/api/v1/pi/conversations")).status_code == 200


async def member_client(api: httpx.AsyncClient, role: str) -> httpx.AsyncClient:
    roles = {r["key"]: r["id"] for r in (await api.get("/api/v1/roles")).json()}
    email = f"{role}-{uuid4().hex[:8]}@example.com"
    await create(
        api,
        "members",
        {
            "email": email,
            "display_name": role.title(),
            "initial_password": "ServiceFlow!Secure234",
            "role_ids": [roles[role]],
        },
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"origin": "http://localhost:3000"},
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "ServiceFlow!Secure234"}
    )
    assert response.status_code == 200, response.text
    client.headers["x-csrf-token"] = client.cookies["platform_csrf"]
    return client


async def test_rbac_denies_without_pi_permissions(api: httpx.AsyncClient, business_db: Any) -> None:
    pi = await pi_workspace(api, business_db)
    await pi.process("hello", "wamid.rbac-1")
    conversation = await pi.conversation()
    handoff = await create(api, f"pi/conversations/{conversation.id}/handoff", {"summary": "x"})
    sales = await member_client(api, "sales")
    viewer = await member_client(api, "viewer")
    try:
        assert code(await sales.get("/api/v1/pi/conversations")) == "FORBIDDEN"
        assert (await viewer.get("/api/v1/pi/conversations")).status_code == 200
        forbidden = (
            ("POST", f"pi/conversations/{conversation.id}/actions/takeover", None),
            ("POST", f"pi/conversations/{conversation.id}/messages", {"body": "hi"}),
            ("POST", f"pi/handoffs/{handoff['id']}/actions", {"action": "assign"}),
            ("GET", f"pi/customers/{conversation.customer_id}/memory", None),
            ("GET", "pi/settings", None),
            ("GET", "pi/agents", None),
            ("GET", "pi/knowledge/sources", None),
            ("GET", "pi/whatsapp", None),
            ("PATCH", "pi/settings/timezone", {"value": "Asia/Karachi"}),
        )
        for method, path, body in forbidden:
            response = await viewer.request(method, f"/api/v1/{path}", json=body)
            assert (response.status_code, code(response)) == (403, "FORBIDDEN"), path
    finally:
        await sales.aclose()
        await viewer.aclose()
        await pi.close()


async def test_handoff_state_machine_and_explicit_return_to_ai(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    await pi.process("hello", "wamid.ho-1")
    conversation = await pi.conversation()
    handoff = await create(
        api, f"pi/conversations/{conversation.id}/handoff", {"reason": "manual", "summary": "Help"}
    )
    assert handoff["status"] == "open"
    await business_db.refresh(conversation)
    assert conversation.mode == "human"

    async def act(action: str, **extra: Any) -> httpx.Response:
        return await api.post(
            f"/api/v1/pi/handoffs/{handoff['id']}/actions", json={"action": action, **extra}
        )

    def rejected(response: httpx.Response) -> bool:
        return response.status_code == 422 and code(response) == "INVALID_TRANSITION"

    assert rejected(await act("resolve", note="skip ahead"))
    assert (await act("assign")).json()["status"] == "assigned"
    assert rejected(await act("resolve", note="skip"))
    started = await act("start")
    assert started.json()["status"] == "in_progress"
    assert rejected(await act("close"))
    missing = await act("resolve")
    assert code(missing) == "RESOLUTION_REQUIRED"
    resolved = (await act("resolve", note="Customer helped")).json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    assert rejected(await act("assign"))
    # Returning control to AI is explicit and audited, never automatic on resolve.
    await business_db.refresh(conversation)
    assert conversation.mode == "human"
    assert (await act("close")).json()["status"] == "closed"
    assert rejected(await act("close"))
    back = await api.post(f"/api/v1/pi/conversations/{conversation.id}/actions/return-to-ai")
    assert back.status_code == 200 and back.json()["mode"] == "ai"
    assert await audit_count(business_db, pi.tenant_id, "pi.return-to-ai") == 1
    assert await audit_count(business_db, pi.tenant_id, "pi.handoff_resolve") == 1
    # A new active handoff blocks return-to-AI until handled.
    second = await create(api, f"pi/conversations/{conversation.id}/handoff", {"summary": "Again"})
    blocked = await api.post(f"/api/v1/pi/conversations/{conversation.id}/actions/return-to-ai")
    assert code(blocked) == "HANDOFF_OPEN"
    reopened = await api.post(
        f"/api/v1/pi/handoffs/{handoff['id']}/actions", json={"action": "reopen"}
    )
    assert code(reopened) == "HANDOFF_OPEN"
    # Other tenants cannot act on it.
    api.cookies.clear()
    other = await pi_workspace(api, business_db, number="987654321")
    response = await api.post(
        f"/api/v1/pi/handoffs/{second['id']}/actions", json={"action": "assign"}
    )
    assert response.status_code == 404
    assert (await api.get("/api/v1/pi/handoffs")).json() == []
    await pi.close()
    await other.close()


async def test_takeover_and_human_reply_report_delivery_honestly(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    await pi.process("hello", "wamid.reply-1")
    conversation = await pi.conversation()
    early = await api.post(
        f"/api/v1/pi/conversations/{conversation.id}/messages", json={"body": "Hi there"}
    )
    assert code(early) == "TAKEOVER_REQUIRED"
    taken = await api.post(f"/api/v1/pi/conversations/{conversation.id}/actions/takeover")
    assert taken.json()["mode"] == "human"
    assert await audit_count(business_db, pi.tenant_id, "pi.takeover") == 1
    reply = await api.post(
        f"/api/v1/pi/conversations/{conversation.id}/messages", json={"body": "Hi there"}
    )
    assert reply.status_code == 200
    assert (reply.json()["status"], reply.json()["error_code"]) == ("queued", None)
    await send_pi_message(pi.ctx, reply.json()["id"])
    sent = await business_db.get(PiMessage, UUID(reply.json()["id"]))
    assert sent.status == "sent" and sent.provider_message_id
    # Without an active number: stays honest (queued -> skipped, never "sent").
    assert (
        await api.put("/api/v1/pi/whatsapp/status", json={"status": "disabled"})
    ).status_code == 200
    offline = await api.post(
        f"/api/v1/pi/conversations/{conversation.id}/messages", json={"body": "Are you there?"}
    )
    assert offline.json()["status"] == "queued"
    assert offline.json()["error_code"] == "WHATSAPP_NOT_CONNECTED"
    await send_pi_message(pi.ctx, offline.json()["id"])
    row = await business_db.get(PiMessage, UUID(offline.json()["id"]))
    assert (row.status, row.error_code) == ("skipped", "WHATSAPP_NOT_CONNECTED")
    messages = (await api.get(f"/api/v1/pi/conversations/{conversation.id}/messages")).json()
    assert {m["status"] for m in messages if m["sender_type"] == "human"} == {"sent", "skipped"}
    limited = await api.get(f"/api/v1/pi/conversations/{conversation.id}/messages?limit=1")
    assert len(limited.json()) == 1
    await pi.close()


async def test_agent_versions_are_immutable_and_rollback_republishes(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    agents = (await api.get("/api/v1/pi/agents")).json()
    assert {a["key"] for a in agents} == {
        "router",
        "customer_memory",
        "support",
        "requirement",
        "sales_order",
        "handoff",
    }
    support = next(a for a in agents if a["key"] == "support")
    v2 = await create(
        api,
        f"pi/agents/{support['id']}/versions",
        {"instructions": "Prefer short answers.", "model_alias": "balanced", "temperature": "0.30"},
    )
    assert v2["version"] == 2 and v2["status"] == "active"
    versions = (await api.get(f"/api/v1/pi/agents/{support['id']}/versions")).json()
    v1 = next(v for v in versions if v["version"] == 1)
    v3 = await create(api, f"pi/agents/{support['id']}/versions/{v1['id']}/rollback", {})
    assert (v3["version"], v3["instructions"], v3["model_alias"]) == (3, "", "fast")
    assert v3["note"] == "Rollback to version 1"
    versions = (await api.get(f"/api/v1/pi/agents/{support['id']}/versions")).json()
    assert [(v["version"], v["status"]) for v in versions] == [
        (3, "active"),
        (2, "archived"),
        (1, "archived"),
    ]
    assert next(v for v in versions if v["version"] == 2)["instructions"] == "Prefer short answers."
    router = next(a for a in agents if a["key"] == "router")
    mismatch = await api.post(f"/api/v1/pi/agents/{router['id']}/versions/{v1['id']}/rollback")
    assert mismatch.status_code == 404
    invalid = await api.post(
        f"/api/v1/pi/agents/{support['id']}/versions",
        json={"instructions": "x", "model_alias": "gpt-9", "temperature": "3"},
    )
    assert invalid.status_code == 422
    tools = (await api.get("/api/v1/pi/tools")).json()
    assert len(tools) == 18
    assert [t["key"] for t in tools if t["requires_confirmation"]] == ["create_order"]
    catalog = (await api.get("/api/v1/pi/tools/catalog")).json()
    assert all("input_schema" in t and "output_schema" in t for t in catalog)
    api.cookies.clear()
    other = await pi_workspace(api, business_db, number="987654321")
    assert (await api.get(f"/api/v1/pi/agents/{support['id']}")).status_code == 404
    assert (await api.get(f"/api/v1/pi/agents/{support['id']}/versions")).status_code == 404
    await pi.close()
    await other.close()


async def test_knowledge_upload_validation_and_search_scoping(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    pi = await pi_workspace(api, business_db)
    source = await create(api, "pi/knowledge/sources", {"name": "Policies", "kind": "faq"})
    doc = await create(
        api,
        "pi/knowledge/documents",
        {"source_id": source["id"], "title": "Revisions", "body": "Two rounds of revisions."},
    )
    assert doc["status"] == "ready" and doc["chunk_count"] == 1
    faq = await create(
        api,
        "pi/knowledge/faq",
        {
            "source_id": source["id"],
            "title": "Refund FAQ",
            "entries": [{"question": "Can I get a refund?", "answer": "Within 14 days."}],
        },
    )
    assert faq["mime_type"] == "text/markdown" and faq["status"] == "ready"
    found = (await api.get("/api/v1/pi/knowledge/search", params={"q": "refund"})).json()
    assert found and found[0]["title"] == "Refund FAQ"
    for body, mime in (
        ("Some text", "application/pdf"),
        ("binary\x00junk", "text/plain"),
        ("\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0e\x0f\x10\x11", "text/plain"),
    ):
        response = await api.post(
            "/api/v1/pi/knowledge/documents",
            json={"source_id": source["id"], "title": "Bad", "body": body, "mime_type": mime},
        )
        assert (response.status_code, code(response)) == (415, "UNSUPPORTED_DOCUMENT_TYPE")
    pdf = await api.post(
        "/api/v1/pi/knowledge/documents/upload",
        data={"source_id": source["id"]},
        files={"file": ("notes.txt", b"%PDF-1.7\n binary", "text/plain")},
    )
    assert (pdf.status_code, code(pdf)) == (415, "UNSUPPORTED_DOCUMENT_TYPE")
    markdown = await api.post(
        "/api/v1/pi/knowledge/documents/upload",
        data={"source_id": source["id"]},
        files={"file": ("hours.md", b"# Hours\nOpen 9 to 5 on weekdays.", "application/pdf")},
    )
    assert markdown.status_code == 200, markdown.text
    assert (markdown.json()["mime_type"], markdown.json()["status"]) == ("text/markdown", "ready")
    settings = api._transport.app.state.settings  # type: ignore[attr-defined]
    settings.knowledge_upload_max_bytes = 2048
    too_big = await api.post(
        "/api/v1/pi/knowledge/documents/upload",
        data={"source_id": source["id"]},
        files={"file": ("big.txt", b"a" * 3000, "text/plain")},
    )
    assert (too_big.status_code, code(too_big)) == (413, "DOCUMENT_TOO_LARGE")
    settings.knowledge_upload_max_bytes = 1024 * 1024
    large = await create(
        api,
        "pi/knowledge/documents",
        {"source_id": source["id"], "title": "Manual", "body": "word " * 60000},
    )
    assert (large["status"], large["chunk_count"]) == ("pending", 0)
    assert (await api.delete(f"/api/v1/pi/knowledge/documents/{faq['id']}")).status_code == 204
    assert (await api.get("/api/v1/pi/knowledge/search", params={"q": "refund"})).json() == []
    api.cookies.clear()
    other = await pi_workspace(api, business_db, number="987654321")
    assert (await api.get("/api/v1/pi/knowledge/search", params={"q": "revisions"})).json() == []
    assert (await api.get(f"/api/v1/pi/knowledge/documents/{doc['id']}")).status_code == 404
    assert (await api.delete(f"/api/v1/pi/knowledge/documents/{doc['id']}")).status_code == 404
    foreign = await api.post(
        "/api/v1/pi/knowledge/documents",
        json={"source_id": source["id"], "title": "x", "body": "Injected"},
    )
    assert foreign.status_code == 404
    await pi.close()
    await other.close()


async def test_memory_read_delete_and_scoping(api: httpx.AsyncClient, business_db: Any) -> None:
    pi = await pi_workspace(api, business_db)
    await pi.process("Mujhe ek naya website chahiye jaldi", "wamid.mem-1")
    conversation = await pi.conversation()
    memory = (await api.get(f"/api/v1/pi/customers/{conversation.customer_id}/memory")).json()
    assert len(memory) == 1 and memory[0]["kind"] == "requirement"
    context = (await api.get(f"/api/v1/pi/conversations/{conversation.id}/context")).json()
    assert [m["id"] for m in context["memory"]] == [memory[0]["id"]]
    assert context["runs"][0]["tools"], "tool activity is reported from real tool calls"
    api.cookies.clear()
    other = await pi_workspace(api, business_db, number="987654321")
    assert (
        await api.get(f"/api/v1/pi/customers/{conversation.customer_id}/memory")
    ).status_code == 404
    assert (await api.delete(f"/api/v1/pi/memory/{memory[0]['id']}")).status_code == 404
    await other.close()
    api.cookies.clear()
    login = await api.post(
        "/api/v1/auth/login",
        json={"email": pi.identity["user"]["email"], "password": "ServiceFlow!Secure234"},
    )
    assert login.status_code == 200, login.text
    api.headers["x-csrf-token"] = api.cookies["platform_csrf"]
    assert (await api.delete(f"/api/v1/pi/memory/{memory[0]['id']}")).status_code == 204
    assert (await api.get(f"/api/v1/pi/customers/{conversation.customer_id}/memory")).json() == []
    assert await audit_count(business_db, pi.tenant_id, "pi.memory_deleted") == 1
    await pi.close()


async def test_whatsapp_status_is_reported_honestly(
    api: httpx.AsyncClient, business_db: Any
) -> None:
    await register(api)
    await create(api, "products/pi/install", {})
    await api.put("/api/v1/products/pi/environment", json={"enabled": True})
    assert (await api.get("/api/v1/pi/whatsapp")).json() is None
    assert (await api.get("/api/v1/pi/overview")).json()["whatsapp"] is None
    activate = await api.put("/api/v1/pi/whatsapp/status", json={"status": "active"})
    assert code(activate) == "CONNECTION_NOT_CONFIGURED"
    assert (await api.get("/api/v1/pi/whatsapp/events")).json()["total"] == 0
